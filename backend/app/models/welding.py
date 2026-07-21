"""焊接记录结构化表（单一数据源）。

大屏 / 统计接口全部从本表读取；腾讯文档同步时解析入库，Excel 历史数据也迁入本表。
字段对齐 keshi 的「尿素信华安装焊接数据库.xlsx」33 列。
"""
from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base

# 表头顺序（与 Excel / 腾讯文档首行一致），解析时按此映射。
HEADER_ORDER = [
    "序号", "装置区代号", "管道介质", "管道级别", "管线号", "焊口号", "焊口备注",
    "管道等级", "探伤比例", "母材材质", "管道规格（外径*壁厚）", "公称直径(寸)", "公称壁厚",
    "焊接日期", "焊工号", "寸口", "班组", "委托日期", "委托单编号", "探伤日期",
    "实际探伤日期", "探伤方式", "一次探伤结果", "二次探伤结果", "三次探伤结果",
    "一次拍片张数", "不合格张数", "总片子张数", "检测单位", "扩探1", "扩探2", "底片",
    "不合格通知单", "审核问题", "是否需要热处理", "热处理日期",
]

# (属性名, 表头, 类型)
COLUMN_DEFS = [
    ("seq", "序号", "int"),
    ("zone_code", "装置区代号", "str"),
    ("medium", "管道介质", "str"),
    ("pipe_level", "管道级别", "str"),
    ("pipeline_no", "管线号", "str"),
    ("joint_no", "焊口号", "str"),
    ("joint_remark", "焊口备注", "str"),
    ("pipe_grade", "管道等级", "str"),
    ("ndt_ratio", "探伤比例", "float"),
    ("material", "母材材质", "str"),
    ("spec", "管道规格（外径*壁厚）", "str"),
    ("nominal_diameter", "公称直径(寸)", "float"),
    ("nominal_thickness", "公称壁厚", "str"),
    ("weld_date", "焊接日期", "date"),
    ("welder", "焊工号", "str"),
    ("inch_port", "寸口", "float"),
    ("team", "班组", "str"),
    ("entrust_date", "委托日期", "date"),
    ("entrust_no", "委托单编号", "str"),
    ("ndt_date", "探伤日期", "str"),
    ("actual_ndt_date", "实际探伤日期", "date"),
    ("ndt_method", "探伤方式", "str"),
    ("ndt_result_1", "一次探伤结果", "str"),
    ("ndt_result_2", "二次探伤结果", "str"),
    ("ndt_result_3", "三次探伤结果", "str"),
    ("film_count_1", "一次拍片张数", "int"),
    ("ng_count", "不合格张数", "int"),
    ("film_total", "总片子张数", "int"),
    ("test_unit", "检测单位", "str"),
    ("expand1", "扩探1", "str"),
    ("expand2", "扩探2", "str"),
    ("film_status", "底片", "str"),
    ("ng_notice", "不合格通知单", "str"),
    ("audit_issue", "审核问题", "str"),
    ("heat_treatment_required", "是否需要热处理", "str"),
    ("heat_treatment_date", "热处理日期", "date"),
    ("heat_treatment_am", "热处理AM", "str"),
    ("heat_treatment_an", "热处理AN", "str"),
    ("heat_treatment_ao", "热处理AO", "str"),
    ("heat_treatment_ap", "热处理AP", "str"),
]

# 用于从 headers 反查属性名
HEADER_TO_ATTR = {h: a for (a, h, _t) in COLUMN_DEFS}


class WeldingRecord(Base):
    __tablename__ = "welding_records"

    id = Column(Integer, primary_key=True, index=True)

    # —— 业务字段（33 列）——
    seq = Column(Integer, nullable=True)
    zone_code = Column(String(50), nullable=True)
    medium = Column(String(50), nullable=True)
    pipe_level = Column(String(50), nullable=True)
    pipeline_no = Column(String(100), nullable=False, index=True)
    joint_no = Column(String(100), nullable=False, index=True)
    joint_remark = Column(String(200), nullable=True)
    pipe_grade = Column(String(50), nullable=True)
    ndt_ratio = Column(Float, nullable=True)
    material = Column(String(100), nullable=True)
    spec = Column(String(100), nullable=True)
    nominal_diameter = Column(Float, nullable=True)
    nominal_thickness = Column(String(50), nullable=True)
    weld_date = Column(Date, nullable=True)
    welder = Column(String(100), nullable=True)
    inch_port = Column(Float, nullable=True)
    team = Column(String(100), nullable=True)
    entrust_date = Column(Date, nullable=True)
    entrust_no = Column(String(100), nullable=True)
    ndt_date = Column(String(50), nullable=True)        # 原始字符串（格式混杂）
    actual_ndt_date = Column(Date, nullable=True)
    ndt_method = Column(String(50), nullable=True)
    ndt_result_1 = Column(String(100), nullable=True)
    ndt_result_2 = Column(String(100), nullable=True)
    ndt_result_3 = Column(String(100), nullable=True)
    film_count_1 = Column(Integer, nullable=True)
    ng_count = Column(Integer, nullable=True)
    film_total = Column(Integer, nullable=True)
    test_unit = Column(String(100), nullable=True)
    expand1 = Column(String(100), nullable=True)
    expand2 = Column(String(100), nullable=True)
    film_status = Column(String(100), nullable=True)
    ng_notice = Column(String(200), nullable=True)
    audit_issue = Column(Text, nullable=True)
    # 腾讯表 AK / AL：仅 AK 为“是”的管线进入热处理统计；AL 的有效日期表示已完成。
    heat_treatment_required = Column(String(20), nullable=True)
    heat_treatment_date = Column(Date, nullable=True)
    # 腾讯表 AM–AP：热处理台账补充字段，按原单元格文本保留展示。
    heat_treatment_am = Column(Text, nullable=True)
    heat_treatment_an = Column(Text, nullable=True)
    heat_treatment_ao = Column(Text, nullable=True)
    heat_treatment_ap = Column(Text, nullable=True)

    # —— 元数据（行权限 / 溯源）——
    document_id = Column(
        Integer, ForeignKey("documents.id"), nullable=False, index=True
    )
    project_id = Column(String(50), nullable=True, index=True)
    department_id = Column(Integer, nullable=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    row_index = Column(Integer, nullable=True)   # 在原表中的行序
    # Tencent rows must be keyed by their physical worksheet row because
    # pipeline and joint values are valid business duplicates.
    source_row = Column(Integer, nullable=True, index=True)
    source = Column(String(20), nullable=True, default="sheet")  # excel | sheet
    version = Column(Integer, default=1, nullable=False)  # 乐观锁：每次更新 +1，用于多人协同冲突检测
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    document = relationship("Document")
