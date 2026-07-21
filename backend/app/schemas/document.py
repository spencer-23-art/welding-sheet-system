"""Document request and response schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DocumentCreate(BaseModel):
    name: str
    is_folder: bool = False
    doc_type: str = "sheet"
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
    has_data: bool
