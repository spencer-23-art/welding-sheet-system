"""文档 / 表格 数据模型。

一个用户拥有多个文档；文档可为文件夹(is_folder=True)或表格(is_folder=False)。
表格的 Univer workbookData 存于 workbook_data（PostgreSQL -> JSONB，SQLite -> TEXT）。
软删除进入回收站(is_deleted=True)；project_id / department_id 用于第三阶段数据隔离。
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    # 文档类型：folder（文件夹）/ sheet（普通表格）/ welding_db（结构化焊接数据库）
    doc_type = Column(String(20), default="sheet", nullable=False, index=True)
    is_folder = Column(Boolean, default=False, nullable=False)

    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("documents.id"), nullable=True, index=True)

    # 业务隔离字段（第三阶段行权限使用）
    department_id = Column(Integer, nullable=True, index=True)
    project_id = Column(String(50), nullable=True, index=True)

    # 回收站
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)

    # Univer 工作簿数据（仅表格有值）
    workbook_data = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    owner = relationship("User")
