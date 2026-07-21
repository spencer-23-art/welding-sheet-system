"""表格数据 API（腾讯文档 → 本地缓存 架构）。

读取：大屏 / 统计全部从 welding_records（本地缓存）取，不经过腾讯文档 API。
同步：POST /{doc_id}/sync 把腾讯文档表格（拉取或手动粘贴）解析入库并推送大屏。
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies import require_permissions
from app.models.document import Document
from app.models.rbac import User
from app.models.welding import WeldingRecord
from app.services import tencent_config as tcfg, tencent_docs as td
from app.services.row_permission import get_data_scope

router = APIRouter(prefix="/api/sheets", tags=["sheets"])


class SyncRequest(BaseModel):
    tencent_url: Optional[str] = None
    rows: Optional[list[list]] = None  # 手动粘贴的二维数据（首行为表头）


def _get_sheet_or_404(db: Session, doc_id: int) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None or doc.is_folder:
        raise HTTPException(status_code=404, detail="表格不存在")
    if doc.is_deleted:
        raise HTTPException(status_code=410, detail="表格已在回收站，请先恢复")
    return doc


def _assert_owner_or_perms(user: User, doc: Document, codenames: list[str]) -> None:
    if doc.owner_id == user.id:
        return
    owned = {p.name for r in user.roles for p in r.permissions}
    if not set(codenames) & owned:
        raise HTTPException(status_code=403, detail="无权操作该表格")


@router.get("/public")
def list_public_sheets(db: Session = Depends(get_db)):
    """公开列出所有表格文件（仅元信息），供大屏无登录选表。"""
    docs = (
        db.query(Document)
        .filter(Document.is_folder.is_(False))
        .filter(Document.is_deleted.is_(False))
        .order_by(Document.id)
        .all()
    )
    return [{"id": d.id, "name": d.name, "doc_type": d.doc_type} for d in docs]


@router.get("/{doc_id}")
def sheet_meta(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("sheet:read")),
):
    """返回表格元信息（含本地缓存记录数），不返回单元格数据。"""
    doc = _get_sheet_or_404(db, doc_id)
    count = 0
    if doc.doc_type == "welding_db":
        count = db.query(WeldingRecord).filter(WeldingRecord.document_id == doc.id).count()
    return {
        "id": doc.id,
        "name": doc.name,
        "doc_type": doc.doc_type,
        "record_count": count,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }


@router.post("/{doc_id}/sync")
def sync_sheet(
    doc_id: int,
    payload: SyncRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("sheet:update")),
):
    """把腾讯文档表格同步进本地缓存（welding_records）。

    - 提供 rows（二维数组，首行表头）→ 直接解析入库。
    - 提供 tencent_url → 走腾讯文档 API 拉取（fetch_sheet_values 待确认 API 类型后实现）。
    """
    doc = _get_sheet_or_404(db, doc_id)
    _assert_owner_or_perms(user, doc, ["sheet:update"])
    if doc.doc_type != "welding_db":
        raise HTTPException(status_code=400, detail="仅结构化焊接库支持同步")

    scope = get_data_scope(user)
    if not scope.can_access_project(doc.project_id):
        raise HTTPException(status_code=403, detail="无权同步该项目的数据")

    values: Optional[list[list]] = None
    if payload.rows:
        values = payload.rows
    elif payload.tencent_url:
        try:
            config = tcfg.get_cfg(db)
            if not config.get("access_token"):
                raise HTTPException(
                    status_code=400,
                    detail="尚未配置腾讯文档开发者凭证，请先由管理员在腾讯文档设置页保存凭证。",
                )
            values = td.TencentDocsClient(config).fetch_sheet_values(payload.tencent_url)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"腾讯文档拉取失败: {e}")

    if not values:
        raise HTTPException(status_code=400, detail="请提供 rows（手动粘贴）或有效的 tencent_url")

    result = td.sync_document(db, doc, values)
    result["updated_at"] = datetime.utcnow().isoformat()
    return result
