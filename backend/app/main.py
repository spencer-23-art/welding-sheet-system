"""FastAPI 应用入口。"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import auth, documents, roles, sheets, users, dashboard, meta, tencent
from app.seed import init_db, seed
from app.services import tencent_config, tencent_poller

logger = logging.getLogger("app.security")


def _warn_insecure_defaults() -> None:
    if settings.JWT_SECRET.startswith("dev-secret-") or settings.JWT_SECRET.startswith("change-me-"):
        logger.warning("JWT_SECRET is using a development default; rotate it before public exposure")
    if settings.SUPERADMIN_PASSWORD == "Admin@123456":
        logger.warning("SUPERADMIN_PASSWORD is using the development default")
    if "*" in settings.CORS_ORIGINS:
        logger.warning("CORS_ORIGINS allows every origin; configure explicit production origins")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时确保表存在并完成种子（幂等）
    from app.core.database import SessionLocal

    _warn_insecure_defaults()
    init_db()
    with SessionLocal() as db:
        seed(db)
        tencent_config.migrate_access_token_encryption(db)
    # 启动腾讯文档定时轮询兜底（webhook 不可用时自动拉取，开关可在设置页热配）
    tencent_poller.start()
    yield
    tencent_poller.stop()


app = FastAPI(title=settings.PROJECT_NAME, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    # Wildcard origins and credentialed CORS must not be combined. The app
    # authenticates with Bearer tokens, so cookies are not required here.
    allow_credentials="*" not in settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(roles.router)
app.include_router(documents.router)
app.include_router(sheets.router)
app.include_router(dashboard.router)
app.include_router(meta.router)
app.include_router(tencent.router)

# 大屏实时推送 WebSocket（路径 /ws/dashboard，与大屏契约一致）
app.websocket("/ws/dashboard")(dashboard.ws_dashboard_handler)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "project": settings.PROJECT_NAME}


@app.get("/", tags=["health"])
def root():
    return {"message": f"{settings.PROJECT_NAME} API", "docs": "/docs"}
