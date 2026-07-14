"""角色与权限路由。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies import require_permissions
from app.models.rbac import Permission, Role
from app.schemas.user import PermissionOut, RoleOut

router = APIRouter(prefix="/api", tags=["roles"])


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    permission_names: List[str] = []


@router.get("/roles", response_model=List[RoleOut])
def list_roles(
    _: Optional[object] = Depends(require_permissions("role:read")),
    db: Session = Depends(get_db),
):
    return db.query(Role).all()


@router.get("/permissions", response_model=List[PermissionOut])
def list_permissions(
    _: Optional[object] = Depends(require_permissions("role:read")),
    db: Session = Depends(get_db),
):
    return db.query(Permission).all()


@router.post(
    "/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED
)
def create_role(
    payload: RoleCreate,
    _: Optional[object] = Depends(require_permissions("role:manage")),
    db: Session = Depends(get_db),
):
    if db.query(Role).filter(Role.name == payload.name).first():
        raise HTTPException(status_code=409, detail="角色名已存在")

    perms = []
    if payload.permission_names:
        perms = (
            db.query(Permission)
            .filter(Permission.name.in_(payload.permission_names))
            .all()
        )
        if len(perms) != len(payload.permission_names):
            raise HTTPException(status_code=400, detail="存在未知权限编码")

    role = Role(name=payload.name, description=payload.description)
    role.permissions.extend(perms)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role
