"""认证路由：注册 / 登录 / 刷新 / 当前用户。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.dependencies import get_current_user, user_permission_names
from app.models.rbac import User
from app.schemas.user import (
    LoginRequest,
    RegisterRequest,
    Token,
    TokenRefresh,
    UserOut,
)

router = APIRouter(prefix="/api", tags=["auth"])


def _find_user_by_account(db: Session, account: str) -> User | None:
    return (
        db.query(User)
        .filter(or_(User.username == account, User.email == account, User.phone == account))
        .first()
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """开放注册：默认仅分配 employee 角色（由 seed 保证存在）。"""
    conds = [User.username == payload.username]
    if payload.email:
        conds.append(User.email == payload.email)
    if payload.phone:
        conds.append(User.phone == payload.phone)
    exists = db.query(User).filter(or_(*conds)).first()
    if exists:
        raise HTTPException(status_code=409, detail="用户名 / 邮箱 / 手机号 已存在")

    from app.models.rbac import Role

    employee = db.query(Role).filter(Role.name == "employee").first()

    user = User(
        username=payload.username,
        email=payload.email,
        phone=payload.phone,
        hashed_password=hash_password(payload.password),
        is_active=True,
    )
    if employee:
        user.roles.append(employee)
    db.add(user)
    db.commit()
    db.refresh(user)
    out = UserOut.model_validate(user)
    out.permissions = sorted(user_permission_names(user))
    return out


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = _find_user_by_account(db, payload.account)
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用")

    perms = [p.name for r in user.roles for p in r.permissions]
    access = create_access_token(user.id, extra={"roles": [r.name for r in user.roles], "perms": perms})
    refresh = create_refresh_token(user.id)
    return Token(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=Token)
def refresh(payload: TokenRefresh, db: Session = Depends(get_db)):
    try:
        data = decode_token(payload.refresh_token)
        if data.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="令牌类型错误")
        user_id = int(data["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="刷新令牌无效或已过期")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")

    perms = [p.name for r in user.roles for p in r.permissions]
    access = create_access_token(user.id, extra={"roles": [r.name for r in user.roles], "perms": perms})
    new_refresh = create_refresh_token(user.id)
    return Token(access_token=access, refresh_token=new_refresh)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    out = UserOut.model_validate(user)
    out.permissions = sorted(user_permission_names(user))
    return out
