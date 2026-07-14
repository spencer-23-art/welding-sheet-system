"""Univer 0.25 workbook_data 与 welding_records 的互操作。

- build_workbook_from_records: 从结构化记录生成可加载的 Univer 工作簿 JSON。
- parse_workbook_to_records: 解析 Univer 工作簿 cellData 为结构化字段字典列表。

Univer cell 结构: { "v": 值, "t": 1(STRING)|2(NUMBER) }。
cellData 为稀疏矩阵: { "行": { "列": cell } }（键均为字符串）。
日期统一以 'YYYY-MM-DD' 文本存储，避免 Univer 日期序列号歧义。
"""
from typing import Any, Iterable, Optional

from app.models.welding import COLUMN_DEFS, HEADER_ORDER, HEADER_TO_ATTR
from app.services.converters import clean_str, parse_date, to_float, to_int

# Univer CellValueType
_CVT_STRING = 1
_CVT_NUMBER = 2

_SHEET_ID = "welding_sheet"

# 属性名 -> 类型（int/float/date/str）
_TYPE_MAP = {c[0]: c[2] for c in COLUMN_DEFS}


def _cell_for(attr: str, value: Any) -> Optional[dict]:
    """根据字段类型生成 Univer 单元格；空值返回 None。"""
    typ = _TYPE_MAP.get(attr, "str")
    if value is None:
        return None
    if typ == "float":
        f = to_float(value)
        return {"v": f, "t": _CVT_NUMBER} if f is not None else None
    if typ == "int":
        i = to_int(value)
        return {"v": i, "t": _CVT_NUMBER} if i is not None else None
    if typ == "date":
        d = parse_date(value)
        return {"v": d.isoformat(), "t": _CVT_STRING} if d is not None else None
    s = clean_str(value)
    return {"v": s, "t": _CVT_STRING} if s != "" else None


def build_workbook_from_records(
    records: Iterable[Any],
    doc_id: int,
    sheet_name: str = "焊接记录",
    limit: Optional[int] = 1000,
) -> dict:
    """从 welding_records（ORM 对象或任意带属性的对象）生成 Univer workbook_data。"""
    cell_data: dict[str, dict[str, dict]] = {}

    # 表头行
    header_row: dict[str, dict] = {}
    for col_idx, (_attr, header, _typ) in enumerate(COLUMN_DEFS):
        header_row[str(col_idx)] = {"v": header, "t": _CVT_STRING}
    cell_data["0"] = header_row

    rows = list(records)
    if limit is not None:
        rows = rows[:limit]

    for r_idx, rec in enumerate(rows, start=1):
        row_cells: dict[str, dict] = {}
        for col_idx, (attr, _header, _typ) in enumerate(COLUMN_DEFS):
            cell = _cell_for(attr, getattr(rec, attr, None))
            if cell is not None:
                row_cells[str(col_idx)] = cell
        if row_cells:
            cell_data[str(r_idx)] = row_cells

    row_count = max(len(rows) + 1, 50)
    return {
        "id": f"welding-db-{doc_id}",
        "name": sheet_name,
        "appVersion": "0.25.1",
        "locale": "zh-CN",
        "styles": {},
        "sheetOrder": [_SHEET_ID],
        "sheets": {
            _SHEET_ID: {
                "id": _SHEET_ID,
                "name": sheet_name,
                "tabColor": "",
                "hidden": 0,
                "freeze": {"xSplit": 0, "ySplit": 1, "startRow": 1, "startColumn": 0},
                "rowCount": row_count,
                "columnCount": len(COLUMN_DEFS),
                "zoomRatio": 1,
                "scrollTop": 0,
                "scrollLeft": 0,
                "defaultColumnWidth": 110,
                "defaultRowHeight": 24,
                "mergeData": [],
                "cellData": cell_data,
                "rowData": {},
                "columnData": {},
                "rowHeader": {"width": 46},
                "columnHeader": {"height": 20},
                "showGridlines": 1,
            }
        },
    }


def parse_workbook_to_records(workbook_data: dict) -> list[dict]:
    """解析 Univer workbook_data → 结构化记录字典列表（已按类型转换）。

    返回列表每项形如 {attr: value, ...}，仅含非空管线号/焊口号的行。
    """
    sheets = workbook_data.get("sheets", {})
    if not sheets:
        return []
    # 取第一个工作表
    sheet = next(iter(sheets.values()))
    cell_data = sheet.get("cellData", {})
    if not cell_data:
        return []

    def _cell_value(row_dict: dict, col: int) -> Any:
        cell = row_dict.get(str(col))
        if not isinstance(cell, dict):
            return None
        # 优先用原始值 v；公式 f 暂不计算
        return cell.get("v")

    # 建立 列 -> 属性 映射（读取表头行，按中文表头反查）
    header_row = cell_data.get("0", {})
    col_to_attr: dict[int, str] = {}
    for col_str, cell in header_row.items():
        try:
            col = int(col_str)
        except (TypeError, ValueError):
            continue
        header_text = clean_str(cell.get("v") if isinstance(cell, dict) else cell)
        attr = HEADER_TO_ATTR.get(header_text)
        if attr:
            col_to_attr[col] = attr

    # 若表头未识别，退化为按 HEADER_ORDER 位置映射
    if not col_to_attr:
        col_to_attr = {i: attr for i, (attr, _h, _t) in enumerate(COLUMN_DEFS)}

    results: list[dict] = []
    for row_key, row_dict in cell_data.items():
        if row_key == "0":
            continue
        record: dict[str, Any] = {}
        for col, attr in col_to_attr.items():
            typ = _TYPE_MAP.get(attr, "str")
            raw = _cell_value(row_dict, col)
            if typ == "date":
                record[attr] = parse_date(raw)
            elif typ == "float":
                record[attr] = to_float(raw)
            elif typ == "int":
                record[attr] = to_int(raw)
            else:
                record[attr] = clean_str(raw)
        # 跳过空行
        pipeline = (record.get("pipeline_no") or "").strip()
        joint = (record.get("joint_no") or "").strip()
        if pipeline == "" and joint == "":
            continue
        results.append(record)
    return results
