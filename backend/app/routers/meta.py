"""元数据接口：供前端「用户分配项目/装置区」使用。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies import require_permissions
from app.models.welding import WeldingRecord
from app.models.document import Document

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/projects")
def meta_projects(
    _: object = Depends(require_permissions("project:read")),
    db: Session = Depends(get_db),
):
    """系统中存在的项目编码（来自文档的 project_id）。"""
    rows = (
        db.query(Document.project_id)
        .filter(Document.project_id.isnot(None))
        .distinct()
        .all()
    )
    return [r[0] for r in rows if r[0]]


@router.get("/zones")
def meta_zones(
    _: object = Depends(require_permissions("project:read")),
    db: Session = Depends(get_db),
):
    """系统中存在的装置区代号（来自焊接记录的 zone_code，去重排序）。"""
    rows = (
        db.query(WeldingRecord.zone_code)
        .filter(WeldingRecord.zone_code.isnot(None))
        .distinct()
        .all()
    )
    return sorted({r[0] for r in rows if r[0]})
