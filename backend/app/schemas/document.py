"""文档 / 表格 相关的 Pydantic 模型。"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class DocumentCreate(BaseModel):
    name: str
    is_folder: bool = False
    doc_type: str = "sheet"  # folder | sheet | welding_db
    parent_id: Optional[int] = None
    department_id: Optional[int] = None
    project_id: Optional[str] = None


class DocumentRename(BaseModel):
    name: str


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_folder: bool
    doc_type: str = "sheet"
    owner_id: int
    parent_id: Optional[int] = None
    department_id: Optional[int] = None
    project_id: Optional[str] = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    has_data: bool  # 表格是否已保存过数据


class SheetSaveRequest(BaseModel):
    workbook_data: dict[str, Any]


class RowSaveRequest(BaseModel):
    """增量保存：仅提交发生变化的行，含各行客户端加载时的版本用于冲突检测。"""
    rows: list[dict[str, Any]]


class SheetLoadResponse(BaseModel):
    id: int
    name: str
    doc_type: str = "sheet"
    workbook_data: Optional[dict[str, Any]] = None
    # 行版本映射：键 "管线号|焊口号" -> version，用于增量保存冲突检测
    row_versions: dict[str, int] = {}
