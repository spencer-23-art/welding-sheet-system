"""大屏统计接口响应模型（与 keshi/backend 大屏契约保持一致）。"""
from typing import List, Optional

from pydantic import BaseModel, Field


class DashboardKpi(BaseModel):
    total_pipelines: int
    total_joints: int
    completed_welds: int
    weld_completion_rate: float
    completed_ndt: int
    film_approved: int
    today_welds: int
    today_ndt: int
    daily_welding_trend: List[dict]
    daily_ndt_trend: List[dict]
    once_ndt_pass_rate: float
    full_ndt_joints: int
    full_ndt_result_joints: int
    full_ndt_completion_rate: float


class PipelineStats(BaseModel):
    pipeline_no: str
    total_joints: int
    completed_welds: int
    weld_completion_rate: float
    ndt_ratio: float
    required_ndt: int
    completed_ndt: int
    ndt_completion_rate: float
    ndt_failed: int


class PipelineDetail(BaseModel):
    pipeline_no: str
    total_joints: int
    completed_welds: int
    uncompleted_welds: int
    weld_completion_rate: float
    ndt_ratio: float
    required_ndt: int
    completed_ndt: int
    ndt_completion_rate: float
    ndt_failed: int
    film_total: int
    film_approved: int
    audit_issue: str = ""
    audit_issues: List[dict] = Field(default_factory=list)
    last_welding_date: Optional[str] = None
    last_ndt_date: Optional[str] = None


class NdtFailedJoint(BaseModel):
    pipeline_no: str
    joint_no: str
    ndt_result: str
    repair_status: str
    test_date: Optional[str] = None
    audit_status: str


class LatestWeldingRecord(BaseModel):
    date: Optional[str] = None
    pipeline_no: str
    joint_no: str
    welder: str
    status: str


class LatestNdtRecord(BaseModel):
    date: Optional[str] = None
    pipeline_no: str
    joint_no: str
    ndt_result: str
    test_date: Optional[str] = None
    audit_status: str
