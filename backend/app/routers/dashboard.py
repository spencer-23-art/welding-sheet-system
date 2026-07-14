"""大屏统计 API + WebSocket 实时推送（公开，无需鉴权）。

端点与大屏（keshi/frontend）契约一致：
  GET /api/dashboard          首页 KPI
  GET /api/pipelines          管线排行
  GET /api/pipeline/{no}      单条管线详情
  GET /api/ndt/ng             探伤不合格清单
  GET /api/latest/welding     最新焊接记录
  GET /api/latest/ndt         最新探伤记录
  WS  /ws/dashboard           数据变动时推送 {type:'data_updated', data:{...}}
"""
import asyncio
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.schemas.dashboard import (
    DashboardKpi,
    LatestNdtRecord,
    LatestWeldingRecord,
    NdtFailedJoint,
    PipelineDetail,
    PipelineStats,
)
from app.services import dashboard_service as ds

router = APIRouter(prefix="/api", tags=["dashboard"])

# ---- WebSocket 连接管理 ----
_active: Set[WebSocket] = set()
_loop = None


class ConnectionManager:
    def __init__(self) -> None:
        self.active: Set[WebSocket] = _active

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)

    async def broadcast(self, payload: dict) -> None:
        dead = []
        for ws in list(self.active):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.discard(ws)


manager = ConnectionManager()


def _broadcast_snapshot() -> None:
    """由数据变动回调触发：在事件循环中向所有连接推送最新数据。"""
    if not _active:
        return
    with SessionLocal() as db:
        payload = ds.get_dashboard_payload(db)
    msg = {"type": "data_updated", "data": payload}
    coro = manager.broadcast(msg)
    if _loop is not None:
        asyncio.run_coroutine_threadsafe(coro, _loop)


# 注册到 DashboardService：写入焊接数据后自动广播
ds.register_change_callback(_broadcast_snapshot)


@router.get("/dashboard", response_model=DashboardKpi)
def get_dashboard():
    with SessionLocal() as db:
        return ds.get_kpi(db)


@router.get("/pipelines", response_model=list[PipelineStats])
def get_pipelines():
    with SessionLocal() as db:
        return ds.get_pipelines(db)


@router.get("/pipeline/{pipeline_no}", response_model=PipelineDetail)
def get_pipeline_detail(pipeline_no: str):
    with SessionLocal() as db:
        detail = ds.get_pipeline_detail(db, pipeline_no)
    if detail is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"管线 {pipeline_no} 不存在")
    return detail


@router.get("/ndt/ng", response_model=list[NdtFailedJoint])
def get_ndt_ng():
    with SessionLocal() as db:
        return ds.get_ndt_ng(db)


@router.get("/latest/welding", response_model=list[LatestWeldingRecord])
def get_latest_welding():
    with SessionLocal() as db:
        return ds.get_latest_welding(db)


@router.get("/latest/ndt", response_model=list[LatestNdtRecord])
def get_latest_ndt():
    with SessionLocal() as db:
        return ds.get_latest_ndt(db)


async def ws_dashboard_handler(ws: WebSocket):
    """WebSocket 实时推送（挂载于 /ws/dashboard，与大屏契约一致）。"""
    global _loop
    await manager.connect(ws)
    _loop = asyncio.get_event_loop()
    try:
        # 连接即推送当前快照
        with SessionLocal() as db:
            payload = ds.get_dashboard_payload(db)
        await ws.send_json({"type": "data_updated", "data": payload})
        # 保持连接，等待客户端（通常不发送）；断开时退出
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)
