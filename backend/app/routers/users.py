"""用户管理路由（管理员）。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_password
from app.dependencies import require_permissions, user_permission_names
from app.models.rbac import Role, User
from app.schemas.user import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api", tags=["users"])


def _with_perms(user: User) -> UserOut:
    out = UserOut.model_validate(user)
    out.permissions = sorted(user_permission_names(user))
    return out


def _protected(user: User) -> None:
    """禁止对初始超级管理员账号做禁用/删除。"""
    if user.username == settings.SUPERADMIN_USERNAME:
        raise HTTPException(status_code=403, detail="初始超级管理员账号受保护")


@router.get("/users", response_model=list[UserOut])
def list_users(
    _: User = Depends(require_permissions("user:read")),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    return [_with_perms(u) for u in db.query(User).offset(skip).limit(limit).all()]


@router.post(
    "/users", response_model=UserOut, status_code=status.HTTP_201_CREATED
)
def create_user(
    payload: UserCreate,
    _: User = Depends(require_permissions("user:create")),
    db: Session = Depends(get_db),
):
    conds = [User.username == payload.username]
    if payload.email:
        conds.append(User.email == payload.email)
    if payload.phone:
        conds.append(User.phone == payload.phone)
    exists = db.query(User).filter(or_(*conds)).first()
    if exists:
        raise HTTPException(status_code=409, detail="用户名 / 邮箱 / 手机号 已存在")

    roles = []
    if payload.role_names:
        roles = db.query(Role).filter(Role.name.in_(payload.role_names)).all()
        if len(roles) != len(payload.role_names):
            raise HTTPException(status_code=400, detail="存在未知角色名")

    user = User(
        username=payload.username,
        email=payload.email,
        phone=payload.phone,
        department_id=payload.department_id,
        assigned_projects=payload.assigned_projects,
        assigned_zones=payload.assigned_zones,
        hashed_password=hash_password(payload.password),
        is_active=True,
    )
    user.roles.extend(roles)
    db.add(user)
    db.commit()
    db.refresh(user)
    return _with_perms(user)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    _: User = Depends(require_permissions("user:update")),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    _protected(user)

    data = payload.model_dump(exclude_unset=True)

    if "role_names" in data and data["role_names"] is not None:
        roles = db.query(Role).filter(Role.name.in_(data["role_names"])).all()
        if len(roles) != len(data["role_names"]):
            raise HTTPException(status_code=400, detail="存在未知角色名")
        user.roles.clear()
        user.roles.extend(roles)
        del data["role_names"]

    if "password" in data and data["password"]:
        user.hashed_password = hash_password(data["password"])
        del data["password"]

    for key, value in data.items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return _with_perms(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_200_OK)
def delete_user(
    user_id: int,
    _: User = Depends(require_permissions("user:delete")),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    _protected(user)
    db.delete(user)
    db.commit()
    return {"status": "success", "message": "用户已删除"}
