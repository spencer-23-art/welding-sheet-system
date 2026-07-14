"""FastAPI 依赖：当前用户解析 + 权限/角色校验。"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models.rbac import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="令牌类型错误")
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用")
    return user


def user_permission_names(user: User) -> set[str]:
    names: set[str] = set()
    for role in user.roles:
        for perm in role.permissions:
            names.add(perm.name)
    return names


def require_permissions(*codenames: str):
    """依赖工厂：要求当前用户拥有全部指定权限编码。"""

    def checker(user: User = Depends(get_current_user)) -> User:
        owned = user_permission_names(user)
        missing = [c for c in codenames if c not in owned]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少权限: {', '.join(missing)}",
            )
        return user

    return checker


def require_roles(*rolenames: str):
    """依赖工厂：要求当前用户拥有任一指定角色。"""

    def checker(user: User = Depends(get_current_user)) -> User:
        owned = {r.name for r in user.roles}
        if not set(rolenames) & owned:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="角色权限不足",
            )
        return user

    return checker
