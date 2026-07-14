"""表格 workbookData 保存 / 加载 API。

保存链路：Univer(frontend) --workbookData JSON--> FastAPI --> PostgreSQL(JSONB)。
加载链路：PostgreSQL --workbookData--> FastAPI --> Univer(frontend) 初始化。
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies import get_current_user, require_permissions
from app.models.document import Document
from app.models.rbac import User
from app.models.welding import COLUMN_DEFS, WeldingRecord
from app.schemas.document import RowSaveRequest, SheetLoadResponse, SheetSaveRequest
from app.services import dashboard_service as ds
from app.services.row_permission import get_data_scope
from app.services.univer_data import build_workbook_from_records, parse_workbook_to_records

router = APIRouter(prefix="/api/sheets", tags=["sheets"])


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


def _upsert_welding_records(db: Session, doc: Document, records: list[dict]) -> None:
    """将解析出的结构化记录 upsert 进 welding_records（DB 为单一数据源，不删除未出现行）。"""
    existing = {
        (r.pipeline_no, r.joint_no): r
        for r in db.query(WeldingRecord).filter(WeldingRecord.document_id == doc.id).all()
    }
    attr_names = [c[0] for c in COLUMN_DEFS]
    for idx, data in enumerate(records):
        key = (data.get("pipeline_no") or "", data.get("joint_no") or "")
        rec = existing.get(key)
        if rec is None:
            rec = WeldingRecord(
                document_id=doc.id,
                owner_id=doc.owner_id,
                project_id=doc.project_id,
                department_id=doc.department_id,
                source="sheet",
            )
            db.add(rec)
            existing[key] = rec
        for attr in attr_names:
            if attr in data:
                setattr(rec, attr, data[attr])
        rec.row_index = idx


@router.get("/{doc_id}", response_model=SheetLoadResponse)
def load_sheet(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("sheet:read")),
):
    doc = _get_sheet_or_404(db, doc_id)
    # 结构化焊接库：始终从 welding_records 重建工作簿（保证与大屏同源）
    if doc.doc_type == "welding_db":
        scope = get_data_scope(user)
        if not scope.can_access_project(doc.project_id):
            raise HTTPException(status_code=403, detail="无权访问该项目的数据")
        records = (
            db.query(WeldingRecord)
            .filter(WeldingRecord.document_id == doc.id)
            .order_by(WeldingRecord.row_index)
            .all()
        )
        # 装置区级行权限过滤
        if scope.has_zone_filter:
            records = [r for r in records if scope.allows_zone(r.zone_code)]
        # 加载全量焊接记录（WPS 式无限行：已用区域全部载入，非凭空造空行）
        wb = build_workbook_from_records(records, doc.id, sheet_name=doc.name, limit=None)
        row_versions = {
            f"{r.pipeline_no}|{r.joint_no}": r.version for r in records
        }
        return SheetLoadResponse(
            id=doc.id,
            name=doc.name,
            doc_type=doc.doc_type,
            workbook_data=wb,
            row_versions=row_versions,
        )
    return SheetLoadResponse(
        id=doc.id, name=doc.name, doc_type=doc.doc_type, workbook_data=doc.workbook_data
    )


@router.post("/{doc_id}/save")
def save_sheet(
    doc_id: int,
    payload: SheetSaveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("sheet:update")),
):
    doc = _get_sheet_or_404(db, doc_id)
    _assert_owner_or_perms(user, doc, ["sheet:update"])

    wd = payload.workbook_data
    if not isinstance(wd, dict) or "sheets" not in wd:
        raise HTTPException(status_code=400, detail="workbook_data 格式不合法（缺少 sheets）")

    # 结构化焊接库：解析 cellData -> welding_records（单一数据源）
    if doc.doc_type == "welding_db":
        records = parse_workbook_to_records(wd)
        _upsert_welding_records(db, doc, records)
        db.commit()
        ds.notify_changed()  # 触发大屏 WebSocket 推送
        return {
            "ok": True,
            "parsed_rows": len(records),
            "updated_at": datetime.utcnow().isoformat(),
        }

    doc.workbook_data = wd
    doc.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "updated_at": doc.updated_at.isoformat()}


@router.post("/{doc_id}/save_rows")
def save_rows(
    doc_id: int,
    payload: RowSaveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("sheet:update")),
):
    """增量保存：仅 upsert 发生变化的行。

    - 版本冲突检测：若某行服务端 version != 客户端提交的 version，则该行冲突，
      不入库并返回在 conflicts 中（由前端提示用户刷新后重试）。
    - 行权限：非 admin 且分配了装置区时，越权 zone 的行直接拒绝（conflicts reason=zone_denied）。
    """
    doc = _get_sheet_or_404(db, doc_id)
    _assert_owner_or_perms(user, doc, ["sheet:update"])
    if doc.doc_type != "welding_db":
        raise HTTPException(status_code=400, detail="仅结构化焊接库支持增量保存")

    scope = get_data_scope(user)
    if not scope.can_access_project(doc.project_id):
        raise HTTPException(status_code=403, detail="无权修改该项目的数据")

    attr_names = [c[0] for c in COLUMN_DEFS]
    existing = {
        (r.pipeline_no, r.joint_no): r
        for r in db.query(WeldingRecord).filter(WeldingRecord.document_id == doc.id).all()
    }
    max_row_index = max((r.row_index or 0) for r in existing.values()) if existing else 0

    conflicts: list[dict] = []
    updated = 0
    new_index = max_row_index
    versions_out: dict[str, int] = {}

    for data in payload.rows:
        pno = (data.get("pipeline_no") or "").strip()
        jno = (data.get("joint_no") or "").strip()
        if not pno and not jno:
            continue
        zone = (data.get("zone_code") or "").strip()
        if not scope.allows_zone(zone):
            conflicts.append(
                {"pipeline_no": pno, "joint_no": jno, "reason": "zone_denied"}
            )
            continue

        client_version = int(data.get("version", 0) or 0)
        rec = existing.get((pno, jno))
        if rec is None:
            new_index += 1
            rec = WeldingRecord(
                document_id=doc.id,
                owner_id=doc.owner_id,
                project_id=doc.project_id,
                department_id=doc.department_id,
                source="sheet",
                version=1,
                row_index=new_index,
            )
            db.add(rec)
            existing[(pno, jno)] = rec
        elif rec.version != client_version:
            conflicts.append(
                {
                    "pipeline_no": pno,
                    "joint_no": jno,
                    "reason": "version_conflict",
                    "current_version": rec.version,
                }
            )
            continue

        for attr in attr_names:
            if attr in data:
                setattr(rec, attr, data[attr])
        rec.version = (rec.version or 1) + 1
        versions_out[f"{pno}|{jno}"] = rec.version
        updated += 1

    db.commit()
    if updated:
        ds.notify_changed()  # 触发大屏 WebSocket 推送
    return {
        "ok": True,
        "updated": updated,
        "conflicts": conflicts,
        "versions": versions_out,
    }
