"""RBAC 数据模型。

用户(User) - 多对多 - 角色(Role) - 多对多 - 权限(Permission)

权限 codename 约定（resource_type 区分作用域）：
  - page:   页面可见性，如  page:admin
  - api:    接口调用，如    user:create
  - sheet:  表格级，如      sheet:update
  - row:    数据行级（第二阶段），如 row:project:A
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base

# 用户 <-> 角色
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
)

# 角色 <-> 权限
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=True)
    phone = Column(String(20), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 业务字段（数据隔离，第三阶段行权限使用）
    department_id = Column(Integer, nullable=True, index=True)
    # 行权限：该用户可访问的项目编码列表（如 ["A", "B"]）；NULL/空=按角色默认范围
    assigned_projects = Column(JSON, nullable=True)
    # 行权限：该用户可访问的装置区代号列表（如 ["LC", "HT"]）；NULL/空=不限制装置区
    assigned_zones = Column(JSON, nullable=True)

    roles = relationship(
        "Role", secondary=user_roles, back_populates="users", lazy="selectin"
    )


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, index=True, nullable=False)
    description = Column(String(255), nullable=True)

    users = relationship("User", secondary=user_roles, back_populates="roles")
    permissions = relationship(
        "Permission", secondary=role_permissions, back_populates="roles"
    )


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    # 权限编码，如 user:create / sheet:update / page:admin
    name = Column(String(100), unique=True, index=True, nullable=False)
    description = Column(String(255), nullable=True)
    # page | api | sheet | row
    resource_type = Column(String(20), default="api", nullable=False)

    roles = relationship(
        "Role", secondary=role_permissions, back_populates="permissions"
    )
