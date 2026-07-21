"""焊接数据字段类型转换工具（Excel / Univer / DB 三方共用）。

统一处理：空值清洗、数字/百分比解析、日期多格式解析。
"""
from datetime import date, datetime
from typing import Any, Optional


def clean_str(val: Any) -> str:
    """清洗为字符串，空值 / 占位符统一为 ''。"""
    if val is None:
        return ""
    s = str(val).strip()
    if s in ("", "/", "nan", "NaT", "None", "nan nan", "NaN"):
        return ""
    return s


def to_float(val: Any) -> Optional[float]:
    """解析浮点数，支持 '0.05' 与 '5%'。空值返回 None。"""
    s = clean_str(val)
    if s == "":
        return None
    try:
        if s.endswith("%"):
            return float(s[:-1]) / 100.0
        # 处理逗号千分位 / 全角
        s2 = s.replace(",", "").replace("％", "%")
        if s2.endswith("%"):
            return float(s2[:-1]) / 100.0
        return float(s2)
    except (ValueError, TypeError):
        return None


def to_int(val: Any) -> Optional[int]:
    """解析整数（先转浮点再取整，容忍 '12.0'）。空值返回 None。"""
    f = to_float(val)
    if f is None:
        return None
    return int(round(f))


def parse_date(val: Any) -> Optional[date]:
    """解析日期，支持 datetime / date / 'YYYY-MM-DD' / 'YYYY/MM/DD' / 'YYYY.MM.DD'。"""
    if val is None:
        return None
    if isinstance(val, datetime):
        parsed = val.date()
        return None if parsed == date(1899, 12, 30) else parsed
    if isinstance(val, date):
        return None if val == date(1899, 12, 30) else val
    s = clean_str(val)
    if s == "":
        return None
    for sep in ("-", "/", "."):
        parts = s.split(sep)
        if len(parts) == 3:
            try:
                y, m, d = (int(parts[0]), int(parts[1]), int(parts[2]))
                # 兼容 2026.3.4 之类
                if 1 <= m <= 12 and 1 <= d <= 31:
                    parsed = date(y, m, d)
                    return None if parsed == date(1899, 12, 30) else parsed
            except ValueError:
                continue
    # 末次尝试：交给 datetime 自动解析
    try:
        parsed = datetime.fromisoformat(s[:10]).date()
        return None if parsed == date(1899, 12, 30) else parsed
    except (ValueError, TypeError):
        return None


def parse_ndt_ratio(val: Any) -> float:
    """管线探伤比例：空值或解析失败时按 0% 处理。"""
    f = to_float(val)
    return f if f is not None else 0.0
