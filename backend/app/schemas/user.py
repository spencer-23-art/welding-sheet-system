"""请求/响应数据模型（Pydantic v2）。"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- 鉴权 ----------
class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)


class LoginRequest(BaseModel):
    # 支持用户名 / 手机号 / 邮箱 登录
    account: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    refresh_token: str


# ---------- 用户 ----------
class UserBase(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    department_id: Optional[int] = None
    # 行权限：可访问的项目编码列表（如 ["A"]）
    assigned_projects: Optional[List[str]] = None
    # 行权限：可访问的装置区代号列表（如 ["LC"]）
    assigned_zones: Optional[List[str]] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=128)
    role_names: List[str] = Field(default_factory=list)  # 管理员创建时指定角色


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    department_id: Optional[int] = None
    is_active: Optional[bool] = None
    role_names: Optional[List[str]] = None
    assigned_projects: Optional[List[str]] = None
    assigned_zones: Optional[List[str]] = None
    password: Optional[str] = Field(None, min_length=6, max_length=128)


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: Optional[str] = None


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: Optional[str] = None
    resource_type: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: Optional[str] = None
    phone: Optional[str] = None
    department_id: Optional[int] = None
    assigned_projects: Optional[List[str]] = None
    assigned_zones: Optional[List[str]] = None
    is_active: bool
    created_at: datetime
    roles: List[RoleOut] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)
