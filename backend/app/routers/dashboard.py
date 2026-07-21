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
from datetime import date
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
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

# ---- WebSocket 连接管理（按 sheet_id 分桶：ws -> 其订阅的表）----
_active: dict = {}  # WebSocket -> Optional[int] sheet_id
_loop = None


class ConnectionManager:
    def __init__(self) -> None:
        self.active: dict = _active
        self.revision = 0

    async def connect(self, ws: WebSocket, sheet_id: Optional[int]) -> None:
        await ws.accept()
        self.active[ws] = sheet_id

    def disconnect(self, ws: WebSocket) -> None:
        self.active.pop(ws, None)

    async def broadcast(self, change: Optional[dict] = None) -> None:
        """按每个连接订阅的 sheet_id 分别计算快照并推送（无 sheet_id 推送全量）。"""
        if not self.active:
            return
        self.revision += 1
        change = change or {}
        changed_document_id = change.get("document_id")
        changed_pipelines = change.get("changed_pipelines") or []
        with SessionLocal() as db:
            for ws, sid in list(self.active.items()):
                # A document-specific import cannot affect another document's
                # subscribed dashboard, so avoid an unnecessary render there.
                if sid is not None and changed_document_id is not None and sid != changed_document_id:
                    continue
                try:
                    payload = ds.get_dashboard_payload(db, sid)
                    await ws.send_json({
                        "type": "data_updated",
                        "revision": self.revision,
                        "changed_pipelines": changed_pipelines,
                        "pipelines_changed": bool(change.get("pipelines_changed", True)),
                        "data": payload,
                    })
                except Exception:
                    self.active.pop(ws, None)


manager = ConnectionManager()


def _broadcast_snapshot(change: Optional[dict] = None) -> None:
    """由数据变动回调触发：在事件循环中向所有连接推送最新数据。"""
    if not _active:
        return
    coro = manager.broadcast(change)
    if _loop is not None:
        asyncio.run_coroutine_threadsafe(coro, _loop)


# 注册到 DashboardService：写入焊接数据后自动广播
ds.register_change_callback(_broadcast_snapshot)


@router.get("/dashboard", response_model=DashboardKpi)
def get_dashboard(sheet_id: Optional[int] = Query(None, description="指定表格(document_id)则仅统计该表，缺省为全量汇总")):
    with SessionLocal() as db:
        return ds.get_kpi(db, sheet_id)


@router.get("/pipelines", response_model=list[PipelineStats])
def get_pipelines(sheet_id: Optional[int] = Query(None, description="指定表格(document_id)则仅统计该表，缺省为全量汇总")):
    with SessionLocal() as db:
        return ds.get_pipelines(db, sheet_id)


@router.get("/pipeline/{pipeline_no}", response_model=PipelineDetail)
def get_pipeline_detail(pipeline_no: str, sheet_id: Optional[int] = Query(None, description="指定表格(document_id)则在单表内查找管线")):
    with SessionLocal() as db:
        detail = ds.get_pipeline_detail(db, pipeline_no, sheet_id)
    if detail is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"管线 {pipeline_no} 不存在")
    return detail


@router.get("/ndt/ng", response_model=list[NdtFailedJoint])
def get_ndt_ng(sheet_id: Optional[int] = Query(None, description="指定表格(document_id)则仅统计该表，缺省为全量汇总")):
    with SessionLocal() as db:
        return ds.get_ndt_ng(db, sheet_id)


@router.get("/latest/welding", response_model=list[LatestWeldingRecord])
def get_latest_welding(sheet_id: Optional[int] = Query(None, description="指定表格(document_id)则仅统计该表，缺省为全量汇总")):
    with SessionLocal() as db:
        return ds.get_latest_welding(db, sheet_id)


@router.get("/latest/ndt", response_model=list[LatestNdtRecord])
def get_latest_ndt(sheet_id: Optional[int] = Query(None, description="指定表格(document_id)则仅统计该表，缺省为全量汇总")):
    with SessionLocal() as db:
        return ds.get_latest_ndt(db, sheet_id)


async def ws_dashboard_handler(ws: WebSocket, sheet_id: Optional[int] = Query(None, description="指定表格(document_id)则仅推送该表数据")):
    """WebSocket 实时推送（挂载于 /ws/dashboard，与大屏契约一致）。

    连接可带 ?sheet_id=N 仅订阅某张表；不带则订阅全量汇总。
    """
    global _loop
    await manager.connect(ws, sheet_id)
    _loop = asyncio.get_event_loop()
    try:
        # 连接即推送当前快照
        with SessionLocal() as db:
            payload = ds.get_dashboard_payload(db, sheet_id)
        await ws.send_json({
            "type": "data_updated",
            "revision": manager.revision,
            # A newly connected client must hydrate its selected pipeline.
            "changed_pipelines": ["*"],
            "pipelines_changed": True,
            "data": payload,
        })
        # 保持连接，等待客户端（通常不发送）；断开时退出
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)


@router.get("/quality-analysis")
def get_quality_analysis(sheet_id: Optional[int] = Query(None)):
    """First-pass welder, pipeline, repair and audit aggregates for the big screen."""
    with SessionLocal() as db:
        return ds.get_quality_analysis(db, sheet_id)


@router.get("/heat-treatment-analysis")
def get_heat_treatment_analysis(sheet_id: Optional[int] = Query(None)):
    """AK/AL heat-treatment status aggregated by pipeline number."""
    with SessionLocal() as db:
        return ds.get_heat_treatment_analysis(db, sheet_id)


@router.get("/pipeline-quality-daily")
def get_pipeline_quality_daily(
    weld_date: Optional[date] = Query(None, description="R 列焊接日期，YYYY-MM-DD"),
    ndt_date: Optional[date] = Query(None, description="V 列探伤日期，YYYY-MM-DD"),
    sheet_id: Optional[int] = Query(None),
):
    """Daily pipeline completion detail and a 14-day trend for the quality page."""
    with SessionLocal() as db:
        return ds.get_daily_pipeline_activity(db, weld_date, ndt_date, sheet_id)
