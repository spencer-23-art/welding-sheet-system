"""FastAPI 应用入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import auth, documents, roles, sheets, users, dashboard, meta, presence
from app.seed import init_db, seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时确保表存在并完成种子（幂等）
    from app.core.database import SessionLocal

    init_db()
    with SessionLocal() as db:
        seed(db)
    yield


app = FastAPI(title=settings.PROJECT_NAME, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
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

# 大屏实时推送 WebSocket（路径 /ws/dashboard，与大屏契约一致）
app.websocket("/ws/dashboard")(dashboard.ws_dashboard_handler)
# 编辑器多人在线状态 WebSocket
app.include_router(presence.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "project": settings.PROJECT_NAME}


@app.get("/", tags=["health"])
def root():
    return {"message": f"{settings.PROJECT_NAME} API", "docs": "/docs"}
