"""文档管理 API：列表 / 创建 / 重命名 / 软删除 / 恢复 / 搜索。

权限：基于 RBAC 的 sheet:* 权限 + owner 校验（创建者始终可管理自己的文档）。
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies import require_permissions
from app.models.document import Document
from app.models.rbac import User
from app.schemas.document import DocumentCreate, DocumentOut, DocumentRename

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _get_doc_or_404(db: Session, doc_id: int) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc


def _assert_not_deleted(doc: Document) -> None:
    if doc.is_deleted:
        raise HTTPException(status_code=410, detail="文档已在回收站，请先恢复")


def _assert_owner_or_perms(user: User, doc: Document, codenames: list[str]) -> None:
    """创建者或拥有任一指定权限编码即可操作。"""
    if doc.owner_id == user.id:
        return
    owned = {p.name for r in user.roles for p in r.permissions}
    if not set(codenames) & owned:
        raise HTTPException(status_code=403, detail="无权操作该文档")


def _serialize(doc: Document) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        name=doc.name,
        is_folder=doc.is_folder,
        doc_type=doc.doc_type,
        owner_id=doc.owner_id,
        parent_id=doc.parent_id,
        department_id=doc.department_id,
        project_id=doc.project_id,
        is_deleted=doc.is_deleted,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        has_data=doc.workbook_data is not None,
    )


@router.get("", response_model=list[DocumentOut])
def list_documents(
    parent_id: int | None = Query(default=None, description="父文件夹ID，根目录传 null"),
    include_deleted: bool = Query(default=False, description="是否包含回收站"),
    q: str | None = Query(default=None, description="按名称搜索（跨全目录）"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("sheet:read")),
):
    query = db.query(Document)
    if q:
        query = query.filter(Document.name.ilike(f"%{q}%"))
    else:
        query = query.filter(Document.parent_id == parent_id)
    if not include_deleted:
        query = query.filter(Document.is_deleted.is_(False))
    docs = query.order_by(Document.is_folder.desc(), Document.name).all()
    return [_serialize(d) for d in docs]


@router.post("", response_model=DocumentOut, status_code=201)
def create_document(
    payload: DocumentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("sheet:create")),
):
    if payload.parent_id is not None:
        parent = db.get(Document, payload.parent_id)
        if parent is None or not parent.is_folder:
            raise HTTPException(status_code=400, detail="父目录不存在或不是文件夹")
    doc = Document(
        name=payload.name,
        is_folder=payload.is_folder,
        doc_type=payload.doc_type,
        owner_id=user.id,
        parent_id=payload.parent_id,
        department_id=payload.department_id,
        project_id=payload.project_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _serialize(doc)


@router.patch("/{doc_id}", response_model=DocumentOut)
def rename_document(
    doc_id: int,
    payload: DocumentRename,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("sheet:update")),
):
    doc = _get_doc_or_404(db, doc_id)
    _assert_not_deleted(doc)
    _assert_owner_or_perms(user, doc, ["sheet:update"])
    doc.name = payload.name
    db.commit()
    db.refresh(doc)
    return _serialize(doc)


@router.delete("/{doc_id}", status_code=204)
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("sheet:delete")),
):
    doc = _get_doc_or_404(db, doc_id)
    if doc.is_deleted:
        return
    _assert_owner_or_perms(user, doc, ["sheet:delete"])
    doc.is_deleted = True
    doc.deleted_at = datetime.utcnow()
    db.commit()


@router.post("/{doc_id}/restore", response_model=DocumentOut)
def restore_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("sheet:delete")),
):
    doc = _get_doc_or_404(db, doc_id)
    if not doc.is_deleted:
        raise HTTPException(status_code=400, detail="文档未处于删除状态")
    _assert_owner_or_perms(user, doc, ["sheet:delete"])
    doc.is_deleted = False
    doc.deleted_at = None
    db.commit()
    db.refresh(doc)
    return _serialize(doc)
