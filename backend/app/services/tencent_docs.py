"""腾讯文档在线表格同步。

腾讯文档分享链接中的 ``D...`` 是 encoded ID，不能直接用于表格 API。
同步流程必须先把它转换为 ``300000000$...`` 的 file ID，再通过 V3
范围查询接口读取单元格数据。
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Optional
from urllib.parse import quote

import httpx

from app.services import tencent_config as tcfg

from app.models.welding import COLUMN_DEFS, HEADER_TO_ATTR
from app.services import converters


def _normalize(header: str) -> str:
    """归一化表头，兼容腾讯表格中常见的换行与空格。"""
    value = (header or "").replace("　", " ")
    return re.sub(r"\s+", "", value).lower()


_HEADER_ALIASES = {
    "管线号": "pipeline_no",
    "管线": "pipeline_no",
    "pipeno": "pipeline_no",
    "pipe_no": "pipeline_no",
    "焊口号": "joint_no",
    "焊口": "joint_no",
    "jointno": "joint_no",
    "装置区": "zone_code",
    "装置区代号": "zone_code",
    "zone": "zone_code",
    "焊工": "welder",
    "焊工号": "welder",
    "班组": "team",
    "施工班组": "team",
    "介质": "medium",
    "管道介质": "medium",
    "管道级别": "pipe_level",
    "管线级别": "pipe_level",
    # 当前腾讯文档使用的施工/检测台账表头。
    "压力管道级别": "pipe_level",
    "焊口规格外径*壁厚": "spec",
    "管道焊口材质": "material",
    "焊口变更备注": "joint_remark",
    "委托单编号": "entrust_no",
    "一次探伤结果": "ndt_result_1",
    "一次返修结果": "ndt_result_2",
    "复探1": "ndt_result_2",
    "二次返修结果": "ndt_result_3",
    "复探2": "ndt_result_3",
    "一次拍片合格数量": "film_count_1",
    "一次拍片数量": "film_total",
    "不合格数量": "ng_count",
    "检测单位": "test_unit",
    "底片审核状态": "film_status",
    "四方底片审核": "film_status",
    "审核问题": "audit_issue",
    "不合格通知单": "ng_notice",
    "是否需要热处理": "heat_treatment_required",
    "是否热处理": "heat_treatment_required",
    "是否已经热处理": "heat_treatment_required",
    "热处理日期": "heat_treatment_date",
    "已热处理日期": "heat_treatment_date",
    "序号": "seq",
    "seq": "seq",
}

# 部分腾讯表头会把说明文字与字段名写在同一个单元格；归一化后用前缀识别。
_HEADER_PREFIX_ALIASES = {
    "探伤方式": "ndt_method",
    "底片审核": "film_status",
    "审核问题": "audit_issue",
    "不合格通知单": "ng_notice",
    "热处理日期": "heat_treatment_date",
}

_ATTR_TYPE = {attr: value_type for (attr, _header, value_type) in COLUMN_DEFS}

# The current Tencent template reserves AK–AP for heat-treatment fields.
# Preserve these physical columns in addition to header matching: operators
# occasionally rename headers, but the dashboard's source-column agreement
# must remain stable.
_FIXED_HEAT_TREATMENT_COLUMNS = {
    37: "heat_treatment_required",  # AK, one-based
    38: "heat_treatment_date",      # AL, one-based
    39: "heat_treatment_am",        # AM, one-based
    40: "heat_treatment_an",        # AN, one-based
    41: "heat_treatment_ao",        # AO, one-based
    42: "heat_treatment_ap",        # AP, one-based
}


def _tracked_columns(column_map: dict[int, str]) -> list[int]:
    """Return imported columns plus AK–AP used by heat-treatment analysis."""
    return sorted(
        {column + 1 for column in column_map}
        | set(_FIXED_HEAT_TREATMENT_COLUMNS)
    )


def header_to_attr(header: str) -> Optional[str]:
    normalized = _normalize(header)
    if not normalized:
        return None
    if normalized in _HEADER_ALIASES:
        return _HEADER_ALIASES[normalized]
    for prefix, attr in _HEADER_PREFIX_ALIASES.items():
        if normalized.startswith(prefix):
            return attr
    # 腾讯表中同一业务字段的列位置会随模板调整；按表头语义匹配，不能依赖
    # R/X/AH 等固定列号。先识别这三个会影响大屏统计的字段。
    if "焊接日期" in normalized:
        return "weld_date"
    # 当前腾讯表 V 列表头为“备注实际探伤日期”；其中的实际探伤日期是
    # 大屏判断是否已经探伤的唯一日期字段。
    if "实际探伤日期" in normalized:
        return "actual_ndt_date"
    if "底片" in normalized and "审核" in normalized:
        return "film_status"
    if "探伤结果" in normalized:
        # Keep the first-pass X-column result separate from repair/retest
        # results.  Without this branch, “一次返修探伤结果” is later in the
        # row and overwrites the real first-pass result during record parsing.
        if "返修" in normalized:
            if "二次" in normalized or "第二" in normalized:
                return "ndt_result_3"
            return "ndt_result_2"
        if "三次" in normalized or "第三" in normalized:
            return "ndt_result_3"
        if "二次" in normalized or "第二" in normalized:
            return "ndt_result_2"
        return "ndt_result_1"
    for original, attr in HEADER_TO_ATTR.items():
        if _normalize(original) == normalized:
            return attr
    return normalized if normalized in _ATTR_TYPE else None


def _header_map(row: list[Any]) -> dict[int, str]:
    return {
        index: attr
        for index, value in enumerate(row)
        if (attr := header_to_attr("" if value is None else str(value)))
    }


def _find_header(values: list[list]) -> tuple[int, dict[int, str]]:
    """在表格前 50 行中定位真正的字段表头。

    实际工程表常在第一行放标题，第二行才是字段名；旧逻辑固定把第一行
    当表头，最终会解析出零条记录。
    """
    best_index = 0
    best_map: dict[int, str] = {}
    for row_index, row in enumerate(values[:50]):
        if not isinstance(row, list):
            continue
        mapping = _header_map(row)
        if len(mapping) > len(best_map):
            best_index, best_map = row_index, mapping
        if {"pipeline_no", "joint_no"}.issubset(mapping.values()):
            return row_index, mapping
    return best_index, best_map


def first_cell_text(values: list[list]) -> str:
    """Return the source sheet's A1 text for the dashboard subtitle."""
    if not values or not isinstance(values[0], list) or not values[0]:
        return ""
    return converters.clean_str(values[0][0])


def parse_range_to_records(
    values: list[list],
    *,
    include_source_rows: bool = False,
    source_row_numbers: Optional[list[int]] = None,
    source_row_start: int = 1,
) -> list[dict]:
    """将腾讯文档二维单元格数据映射为焊接记录。"""
    if not values or len(values) < 2:
        return []

    header_index, column_map = _find_header(values)
    if len(column_map) < 2:
        return []

    records: list[dict] = []
    data_rows = values[header_index + 1 :]
    if source_row_numbers is not None and len(source_row_numbers) != len(data_rows):
        raise RuntimeError("incremental source-row metadata does not match returned rows")

    for data_offset, row in enumerate(data_rows):
        if not isinstance(row, list):
            continue
        record: dict[str, Any] = {}
        for column_index, attr in column_map.items():
            if column_index >= len(row):
                continue
            raw = row[column_index]
            value_type = _ATTR_TYPE.get(attr, "str")
            if value_type == "int":
                record[attr] = converters.to_int(raw)
            elif value_type == "float":
                record[attr] = converters.to_float(raw)
            elif value_type == "date":
                record[attr] = converters.parse_date(raw)
            else:
                record[attr] = converters.clean_str(raw)
        for column_number, attr in _FIXED_HEAT_TREATMENT_COLUMNS.items():
            column_index = column_number - 1
            if column_index >= len(row):
                continue
            raw = row[column_index]
            if _ATTR_TYPE.get(attr) == "date":
                # parse_date intentionally normalizes the Tencent empty-date
                # sentinel 1899-12-30 to None.
                record[attr] = converters.parse_date(raw)
            else:
                record[attr] = converters.clean_str(raw)
        # A dashboard joint is defined by the pair of pipeline and joint
        # numbers.  Users often fill those cells one after another; an
        # intermediate, half-filled row must never become a real record.
        if (
            record.get("pipeline_no")
            and record.get("joint_no")
            and any(value not in (None, "") for value in record.values())
        ):
            if include_source_rows:
                source_row = (
                    source_row_numbers[data_offset]
                    if source_row_numbers is not None
                    else source_row_start + header_index + data_offset + 1
                )
                if not isinstance(source_row, int) or source_row < 1:
                    raise RuntimeError("Tencent source row must be a positive integer")
                record["_source_row"] = source_row
            records.append(record)
    return records


def sync_document(
    db,
    doc,
    values: list[list],
    *,
    full_snapshot: bool = False,
    source_row_numbers: Optional[list[int]] = None,
    source_row_start: int = 1,
) -> dict:
    """将腾讯表格记录 upsert 到本地缓存并通知数据大屏。"""
    from app.models.welding import WeldingRecord
    from app.services import dashboard_service as dashboard

    records = parse_range_to_records(
        values,
        include_source_rows=True,
        source_row_numbers=source_row_numbers,
        source_row_start=source_row_start,
    )
    existing_rows = (
        db.query(WeldingRecord)
        .filter(WeldingRecord.document_id == doc.id, WeldingRecord.source == "tencent_doc")
        .all()
    )
    previous_rows = len(existing_rows)
    existing = {
        record.source_row: record
        for record in existing_rows
        if record.source_row is not None
    }
    attribute_names = [attr for (attr, _header, _value_type) in COLUMN_DEFS]
    created = 0
    updated = 0
    unchanged = 0
    incoming_source_rows: set[int] = set()
    changed_pipelines: set[str] = set()

    try:
        for data in records:
            source_row = data.pop("_source_row")
            incoming_source_rows.add(source_row)
            record = existing.get(source_row)
            is_new = record is None
            if record is None:
                record = WeldingRecord(
                    document_id=doc.id,
                    owner_id=doc.owner_id,
                    project_id=doc.project_id,
                    department_id=doc.department_id,
                    source="tencent_doc",
                    source_row=source_row,
                    row_index=source_row,
                    version=0,
                    pipeline_no=data["pipeline_no"],
                    joint_no=data["joint_no"],
                )
                db.add(record)
                existing[source_row] = record
                created += 1
                record_changed = True
                previous_pipeline = ""
            else:
                record_changed = False
                previous_pipeline = record.pipeline_no or ""
            for attr in attribute_names:
                if attr in data and getattr(record, attr) != data[attr]:
                    setattr(record, attr, data[attr])
                    record_changed = True

            if record.source_row != source_row or record.row_index != source_row:
                record.source_row = source_row
                record.row_index = source_row
                record_changed = True

            if record_changed:
                record.version = (record.version or 0) + 1
                if not is_new:
                    updated += 1
                if previous_pipeline:
                    changed_pipelines.add(previous_pipeline)
                if record.pipeline_no:
                    changed_pipelines.add(record.pipeline_no)
            else:
                unchanged += 1

        stale_records = []
        if full_snapshot:
            stale_records = [
                record
                for record in existing_rows
                if record.source_row not in incoming_source_rows
            ]
            for record in stale_records:
                if record.pipeline_no:
                    changed_pipelines.add(record.pipeline_no)
                db.delete(record)

        # One commit makes the full snapshot visible atomically.  A failed
        # import cannot expose a half-updated cache to the dashboard.
        db.commit()
    except Exception:
        db.rollback()
        raise

    active_rows = len(records) if full_snapshot else previous_rows + created
    if created or updated or stale_records:
        # Keep the event bounded even when the first full import adds many
        # thousands of pipelines.  "*" tells clients to refresh a selected
        # detail panel once, without serialising an enormous metadata list.
        pipeline_list = sorted(changed_pipelines)
        if len(pipeline_list) > 200:
            pipeline_list = ["*"]
        dashboard.notify_changed({
            "document_id": doc.id,
            "changed_pipelines": pipeline_list,
            "pipelines_changed": True,
        })
    return {
        "parsed_rows": len(records),
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "removed_partial": 0,
        "stale_removed": len(stale_records),
        "active_rows": active_rows,
        "snapshot": full_snapshot,
    }


def extract_file_id(value: str) -> str:
    """从分享链接提取 encoded ID，或保留传入的原始 file ID。"""
    raw = (value or "").strip()
    match = re.search(
        r"(?:/sheet/|/d/|/file/|/spreadsheet/|/smart/|/smartsheet/)([A-Za-z0-9_$-]+)",
        raw,
    )
    if match:
        return match.group(1)
    return raw.split("?", 1)[0].strip()


def _column_name(index: int) -> str:
    """把从 1 开始的列序号转换为 A1 表示法列名。"""
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


class TencentDocsClient:
    """腾讯文档 Open API 客户端（开发者三元组鉴权）。"""

    BASE = "https://docs.qq.com"
    MAX_CELLS_PER_REQUEST = 10_000

    def __init__(self, config: dict):
        self.app_id = config.get("app_id")
        self.open_id = config.get("open_id")
        self.access_token = config.get("access_token")

    def _headers(self) -> dict[str, str]:
        return {
            "Client-Id": self.app_id or "",
            "Open-Id": self.open_id or "",
            "Access-Token": self.access_token or "",
        }

    @staticmethod
    def _check_ret(body: dict, action: str) -> None:
        ret = body.get("ret")
        if ret in (0, None):
            return
        message = body.get("msg") or "未知错误"
        hints = {
            10202: "请确认传入的是 file ID，而不是分享链接中的 D... ID。",
            10302: "Client-Id 与 Access-Token 不匹配。",
            10303: "Open-Id 与 Access-Token 不匹配。",
            10313: "Access-Token 为空。",
            37019: "Access-Token 无效或已过期。",
        }
        raise RuntimeError(f"{action}失败(ret={ret}, msg={message})。{hints.get(ret, '')}")

    def _get_json(self, url: str, action: str, *, params: Optional[dict] = None) -> dict:
        # Count every outbound request attempt, including Tencent errors and
        # network failures, to match the call volume that consumes API quota.
        tcfg.record_api_call()
        try:
            response = httpx.get(url, headers=self._headers(), params=params, timeout=20)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"{action}网络请求失败：{exc}") from exc
        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError(f"{action}返回非 JSON（HTTP {response.status_code}）") from exc
        if not isinstance(body, dict):
            raise RuntimeError(f"{action}返回格式异常（HTTP {response.status_code}）")
        self._check_ret(body, action)
        if response.is_error:
            message = body.get("message") or body.get("msg") or "未知错误"
            raise RuntimeError(f"{action}失败（HTTP {response.status_code}: {message}）")
        return body

    def resolve_file_id(self, book_id: str) -> str:
        """将分享链接/encoded ID 转换为 API 所需的 file ID。"""
        candidate = extract_file_id(book_id)
        if re.fullmatch(r"\d+\$[A-Za-z0-9_-]+", candidate):
            return candidate
        if not candidate:
            raise RuntimeError("未提供腾讯文档分享链接或 file ID")
        body = self._get_json(
            f"{self.BASE}/openapi/drive/v2/util/converter",
            "转换腾讯文档 ID",
            params={"type": 2, "value": candidate},
        )
        file_id = ((body.get("data") or {}).get("fileID"))
        if not file_id:
            raise RuntimeError("腾讯文档 ID 转换成功但未返回 fileID")
        return str(file_id)

    def _get_sheets(self, file_id: str) -> list[dict]:
        body = self._get_json(
            f"{self.BASE}/openapi/sheetbook/v2/{quote(file_id, safe='$')}/sheets-info",
            "查询工作表",
        )
        data = body.get("data") or {}
        sheets = data.get("sheetData") or data.get("getSheet") or data.get("sheets") or []
        if not isinstance(sheets, list) or not sheets:
            raise RuntimeError("该腾讯文档未返回任何工作表")
        return [sheet for sheet in sheets if isinstance(sheet, dict)]

    @staticmethod
    def _sheet_id(sheet: dict) -> str:
        value = sheet.get("sheetID") or sheet.get("sheetId") or sheet.get("sheet_id")
        if not value:
            raise RuntimeError("工作表数据缺少 sheetID")
        return str(value)

    def _select_sheet(self, file_id: str, requested_sheet_id: Optional[str]) -> dict:
        sheets = self._get_sheets(file_id)
        if requested_sheet_id:
            for sheet in sheets:
                if self._sheet_id(sheet) == requested_sheet_id:
                    return sheet
            raise RuntimeError(f"未找到子表 {requested_sheet_id}")
        return sheets[0]

    @staticmethod
    def _cell_value(cell: Any) -> Any:
        if not isinstance(cell, dict):
            return cell
        value = cell.get("cellValue")
        if value is None:
            return None
        if not isinstance(value, dict):
            return value
        # 腾讯 V3 的日期不是 text，而是 {time:{year,month,day,...}}。
        # 转为 ISO 日期后交由现有日期转换器写入 weld_date/actual_ndt_date。
        if isinstance(value.get("time"), dict):
            time = value["time"]
            year, month, day = time.get("year"), time.get("month"), time.get("day")
            # Tencent Docs date-picker cells use the Excel zero-date when a
            # previously selected date is cleared.  It is semantically blank,
            # not a real welding date.
            if (year, month, day) == (1899, 12, 30):
                return ""
            if year and month and day:
                return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
            return ""
        # 下拉单元格只返回已选 option ID；要用 options 反查实际中文文本。
        if isinstance(value.get("select"), dict):
            select = value["select"]
            selected = [str(item) for item in (select.get("value") or [])]
            option_text = {
                str(option.get("id")): str(option.get("text") or "")
                for option in (select.get("options") or [])
                if isinstance(option, dict) and option.get("id") is not None
            }
            return ",".join(option_text.get(item, item) for item in selected)
        for key in ("text", "number", "bool", "formula", "formulaValue"):
            if key in value:
                return value[key]
        return ""

    @classmethod
    def _extract_values(cls, body: dict) -> list[list]:
        """兼容 V3 gridData 以及旧版二维 values 响应。"""
        grid_data = body.get("gridData")
        if isinstance(grid_data, dict) and isinstance(grid_data.get("rows"), list):
            return [
                [cls._cell_value(cell) for cell in (row.get("values") or [])]
                for row in grid_data["rows"]
                if isinstance(row, dict)
            ]

        data = body.get("data") or body
        if isinstance(data, dict):
            if isinstance(data.get("values"), list):
                return data["values"]
            nested_grid = data.get("gridData")
            if isinstance(nested_grid, dict) and isinstance(nested_grid.get("rows"), list):
                return [
                    [cls._cell_value(cell) for cell in (row.get("values") or [])]
                    for row in nested_grid["rows"]
                    if isinstance(row, dict)
                ]
        return []

    def _fetch_range(self, file_id: str, sheet_id: str, cell_range: str) -> list[list]:
        if not re.fullmatch(r"\$?[A-Za-z]+\$?\d+:\$?[A-Za-z]+\$?\d+", cell_range):
            raise RuntimeError("单元格范围必须使用 A1 表示法，例如 A1:AT200")
        url = (
            f"{self.BASE}/openapi/spreadsheet/v3/files/{quote(file_id, safe='$')}/"
            f"{quote(sheet_id, safe='')}/{quote(cell_range, safe=':$')}"
        )
        body = self._get_json(url, "读取表格范围")
        return self._extract_values(body)

    @staticmethod
    def _cached_sheet_source(
        cursor: Optional[dict], requested_sheet_id: Optional[str]
    ) -> Optional[dict]:
        """Return the stable Tencent identifiers saved by a prior full sync.

        A Tencent sharing ID is convenient for operators but is not the ID
        required by the V3 range endpoint.  Once a successful full sync has
        resolved that ID and selected a worksheet, asking the converter and
        sheets-info endpoints again on every refresh is unnecessary.  The
        cursor is reset whenever the configured workbook changes, so it is a
        safe cache boundary for those stable identifiers.
        """
        if not isinstance(cursor, dict):
            return None
        file_id = str(cursor.get("file_id") or "").strip()
        sheet_id = str(cursor.get("sheet_id") or "").strip()
        if not file_id or not sheet_id:
            return None
        if requested_sheet_id and requested_sheet_id != sheet_id:
            # An explicitly supplied sheet always wins over cached metadata.
            return None

        try:
            tracked_columns = sorted(
                {int(column) for column in cursor.get("tracked_columns") or [] if int(column) > 0}
            )
            pipeline_column = int(cursor["pipeline_column"])
            joint_column = int(cursor["joint_column"])
            declared_column_count = int(cursor.get("column_count") or 0)
        except (KeyError, TypeError, ValueError):
            return None
        if not tracked_columns or pipeline_column < 1 or joint_column < 1:
            return None

        # Read only the populated business columns, not Tencent's often much
        # larger visual grid.  This maximises the number of rows that fit into
        # one 10,000-cell request while retaining every field imported here.
        # Older cursors may end before all AK–AP heat-treatment columns.  A
        # A cursor saved by a previous version may have stopped at AK/AL even
        # though the configured worksheet already contains AM–AP.  Keep the
        # proven file/sheet identifiers and extend its cached range directly:
        # reselecting a worksheet can fall back to Tencent's default tab and
        # read an unrelated sheet that has no business headers.
        fixed_columns = set(_FIXED_HEAT_TREATMENT_COLUMNS)
        heat_columns = [
            column
            for column in _FIXED_HEAT_TREATMENT_COLUMNS
            if declared_column_count >= min(fixed_columns)
        ]
        column_count = max(tracked_columns + [pipeline_column, joint_column, *heat_columns])
        return {
            "file_id": file_id,
            "sheet_id": sheet_id,
            "column_count": column_count,
            "pipeline_column": pipeline_column,
            "joint_column": joint_column,
        }

    def _fetch_cached_full_values(self, source: dict) -> list[list]:
        """Read a known worksheet without converter/sheet-metadata requests.

        The first range always contains at most 10,000 cells.  Normal small
        workbooks therefore make exactly one Tencent API call.  If a contiguous
        data block reaches that boundary, continue page by page so future large
        workbooks still obey Tencent's range limit.
        """
        column_count = max(1, min(int(source["column_count"]), 200))
        rows_per_request = max(1, self.MAX_CELLS_PER_REQUEST // column_count)
        end_column = _column_name(column_count)
        pipeline_column = int(source["pipeline_column"])
        joint_column = int(source["joint_column"])
        values: list[list] = []
        start_row = 1

        while True:
            end_row = start_row + rows_per_request - 1
            rows = self._fetch_range(
                str(source["file_id"]),
                str(source["sheet_id"]),
                f"A{start_row}:{end_column}{end_row}",
            )
            values.extend(rows)

            # Tencent omits trailing empty rows in normal V3 responses.  If a
            # provider returns a short page we also have a definitive end.
            if len(rows) < rows_per_request:
                break
            # Appended weld records are contiguous.  A blank key pair at a
            # page boundary means this is the last populated page; continuing
            # would burn an unnecessary API call on the empty visual grid.
            last_row = rows[-1] if rows else []
            if not self._row_has_record_key(last_row, pipeline_column, joint_column):
                break
            start_row = end_row + 1

        return values

    def fetch_sheet_values(
        self,
        book_id: str,
        sheet_id: Optional[str] = None,
        cell_range: Optional[str] = None,
        *,
        source_cursor: Optional[dict] = None,
    ) -> list[list]:
        """读取指定工作表；未给范围时按接口上限自动分段读取整张表。"""
        cached_source = None if cell_range else self._cached_sheet_source(source_cursor, sheet_id)
        if cached_source:
            return self._fetch_cached_full_values(cached_source)

        file_id = self.resolve_file_id(book_id)
        sheet = self._select_sheet(file_id, sheet_id)
        selected_sheet_id = self._sheet_id(sheet)
        if cell_range:
            return self._fetch_range(file_id, selected_sheet_id, cell_range)

        column_count = max(1, min(int(sheet.get("columnCount") or 26), 200))
        row_count = max(1, int(sheet.get("rowCount") or 1))
        rows_per_request = max(1, min(1000, self.MAX_CELLS_PER_REQUEST // column_count))
        end_column = _column_name(column_count)
        values: list[list] = []
        for start_row in range(1, row_count + 1, rows_per_request):
            end_row = min(row_count, start_row + rows_per_request - 1)
            values.extend(
                self._fetch_range(file_id, selected_sheet_id, f"A{start_row}:{end_column}{end_row}")
            )
        return values

    @staticmethod
    def _row_has_record_key(row: list[Any], pipeline_column: int, joint_column: int) -> bool:
        """Return whether a row has either of the two business key cells.

        Column numbers in a cursor are 1-based so they can be used directly in
        A1 ranges.  A partially filled key is still a meaningful row: it must
        advance the cursor so a later append is not repeatedly read.
        """
        for column in (pipeline_column, joint_column):
            index = column - 1
            if index < len(row) and str(row[index] if row[index] is not None else "").strip():
                return True
        return False

    @staticmethod
    def _row_fingerprint(row: list[Any], tracked_columns: list[int]) -> str:
        """Hash business columns only, using stable JSON for Tencent cell values."""
        values = [row[column - 1] if column - 1 < len(row) else None for column in tracked_columns]
        encoded = json.dumps(values, ensure_ascii=False, default=str, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _column_groups(columns: list[int]) -> list[tuple[int, int]]:
        """Combine adjacent business columns into the fewest A1 range reads."""
        if not columns:
            return []
        groups: list[tuple[int, int]] = []
        start = end = columns[0]
        for column in columns[1:]:
            if column == end + 1:
                end = column
            else:
                groups.append((start, end))
                start = end = column
        groups.append((start, end))
        return groups

    def build_incremental_cursor(
        self,
        book_id: str,
        values: list[list],
        sheet_id: Optional[str] = None,
        *,
        source_cursor: Optional[dict] = None,
    ) -> dict:
        """Create a stable append-only cursor after a full sheet read.

        The cursor records the header and key-column positions discovered from
        the actual sheet instead of relying on fixed Excel columns.  That keeps
        the later lightweight scan valid when users insert unrelated columns.
        """
        header_index, column_map = _find_header(values)
        attrs_to_columns = {attr: column + 1 for column, attr in column_map.items()}
        pipeline_column = attrs_to_columns.get("pipeline_no")
        joint_column = attrs_to_columns.get("joint_no")
        if not pipeline_column or not joint_column:
            raise RuntimeError("无法从腾讯文档表头识别管线号和焊口号，不能建立增量同步游标")

        cached_source = self._cached_sheet_source(source_cursor, sheet_id)
        if cached_source:
            file_id = str(cached_source["file_id"])
            selected_sheet_id = str(cached_source["sheet_id"])
            sheet_column_count = int(cached_source["column_count"])
        else:
            file_id = self.resolve_file_id(book_id)
            sheet = self._select_sheet(file_id, sheet_id)
            selected_sheet_id = self._sheet_id(sheet)
            sheet_column_count = max(1, min(int(sheet.get("columnCount") or 26), 200))
        header_row = header_index + 1
        # A few historical or test workbooks legitimately stop before AK–AP.
        # Do not issue a range request beyond the worksheet's declared width;
        # full-size Tencent templates still retain the fixed heat columns.
        tracked_columns = [
            column
            for column in _tracked_columns(column_map)
            if column <= sheet_column_count
        ]
        row_fingerprints: dict[str, str] = {}
        last_data_row = header_row
        for row_number, row in enumerate(values[header_index + 1 :], start=header_row + 1):
            if isinstance(row, list) and self._row_has_record_key(
                row, pipeline_column, joint_column
            ):
                last_data_row = row_number
                row_fingerprints[str(row_number)] = self._row_fingerprint(row, tracked_columns)

        return {
            "version": 2,
            "file_id": file_id,
            "sheet_id": selected_sheet_id,
            "header_row": header_row,
            "last_data_row": last_data_row,
            "pipeline_column": pipeline_column,
            "joint_column": joint_column,
            "column_count": sheet_column_count,
            "tracked_columns": tracked_columns,
            "row_fingerprints": row_fingerprints,
        }

    def fetch_incremental_values(
        self,
        book_id: str,
        cursor: dict,
        sheet_id: Optional[str] = None,
        *,
        check_existing_changes: bool = False,
    ) -> tuple[list[list], dict, dict]:
        """Read appended rows and, when requested, detect changed existing rows.

        Tencent's range API has no ``changed since`` cursor.  A modification
        scan therefore reads only the columns that this application imports,
        compares per-row hashes with the previous scan, and then fetches full
        cells only for rows whose hash changed.  New rows always use the much
        cheaper two-key-column scan.
        """
        if not isinstance(cursor, dict) or cursor.get("version") != 2:
            return [], cursor or {}, {"requires_full": True, "reason": "missing_cursor"}

        try:
            header_row = int(cursor["header_row"])
            last_data_row = int(cursor["last_data_row"])
            pipeline_column = int(cursor["pipeline_column"])
            joint_column = int(cursor["joint_column"])
            tracked_columns = [int(column) for column in cursor["tracked_columns"]]
        except (KeyError, TypeError, ValueError):
            return [], cursor, {"requires_full": True, "reason": "invalid_cursor"}
        if not tracked_columns or not isinstance(cursor.get("row_fingerprints"), dict):
            return [], cursor, {"requires_full": True, "reason": "missing_fingerprints"}

        # The canonical API file ID is persisted in the cursor.  This avoids a
        # converter API call on every poll.  A changed configured sheet is
        # explicitly reset by the configuration endpoints.
        file_id = str(cursor.get("file_id") or self.resolve_file_id(book_id))
        selected_sheet_id = sheet_id or cursor.get("sheet_id")
        try:
            sheet = self._select_sheet(file_id, selected_sheet_id)
        except RuntimeError:
            return [], cursor, {"requires_full": True, "reason": "sheet_changed"}

        actual_sheet_id = self._sheet_id(sheet)
        if cursor.get("sheet_id") and actual_sheet_id != cursor.get("sheet_id"):
            return [], cursor, {"requires_full": True, "reason": "sheet_changed"}

        column_count = max(1, min(int(sheet.get("columnCount") or 26), 200))
        row_count = max(1, int(sheet.get("rowCount") or 1))
        if column_count < max(pipeline_column, joint_column) or row_count < last_data_row:
            return [], cursor, {"requires_full": True, "reason": "sheet_structure_changed"}

        next_cursor = dict(cursor)
        next_cursor.update(
            {
                "file_id": file_id,
                "sheet_id": actual_sheet_id,
                "column_count": column_count,
                "row_fingerprints": dict(cursor["row_fingerprints"]),
            }
        )
        end_column = _column_name(column_count)
        header_values: list[list] = []
        changed_values: list[list] = []
        changed_source_rows: list[int] = []
        scanned_cells = 0
        fingerprint_cells = 0
        fetched_cells = 0
        changed_row_numbers: list[int] = []

        if check_existing_changes and last_data_row > header_row:
            # A tiny header read also catches a moved/renamed business column;
            # in that case a safe full reconciliation is preferable to using a
            # stale cursor position.
            header_values = self._fetch_range(
                file_id, actual_sheet_id, f"A{header_row}:{end_column}{header_row}"
            )
            fingerprint_cells += column_count
            current_map = _header_map(header_values[0] if header_values else [])
            current_tracked = [
                column
                for column in _tracked_columns(current_map)
                if column <= column_count
            ]
            current_pipeline = next(
                (column + 1 for column, attr in current_map.items() if attr == "pipeline_no"),
                None,
            )
            current_joint = next(
                (column + 1 for column, attr in current_map.items() if attr == "joint_no"),
                None,
            )
            if (
                current_tracked != tracked_columns
                or current_pipeline != pipeline_column
                or current_joint != joint_column
            ):
                return [], cursor, {"requires_full": True, "reason": "header_changed"}

            first_data_row = header_row + 1
            snapshot = {
                row_number: [None] * len(tracked_columns)
                for row_number in range(first_data_row, last_data_row + 1)
            }
            slot_by_column = {column: slot for slot, column in enumerate(tracked_columns)}
            for group_start, group_end in self._column_groups(tracked_columns):
                width = group_end - group_start + 1
                rows_per_request = max(1, self.MAX_CELLS_PER_REQUEST // width)
                for chunk_start in range(first_data_row, last_data_row + 1, rows_per_request):
                    chunk_end = min(last_data_row, chunk_start + rows_per_request - 1)
                    group_rows = self._fetch_range(
                        file_id,
                        actual_sheet_id,
                        f"{_column_name(group_start)}{chunk_start}:{_column_name(group_end)}{chunk_end}",
                    )
                    cells = (chunk_end - chunk_start + 1) * width
                    scanned_cells += cells
                    fingerprint_cells += cells
                    for row_offset in range(chunk_end - chunk_start + 1):
                        source_row = group_rows[row_offset] if row_offset < len(group_rows) else []
                        if not isinstance(source_row, list):
                            source_row = []
                        target_row = snapshot[chunk_start + row_offset]
                        for column in range(group_start, group_end + 1):
                            source_index = column - group_start
                            target_row[slot_by_column[column]] = (
                                source_row[source_index] if source_index < len(source_row) else None
                            )

            fingerprints: dict[str, str] = {}
            pipeline_slot = slot_by_column[pipeline_column]
            joint_slot = slot_by_column[joint_column]
            for row_number, values in snapshot.items():
                if not self._row_has_record_key(values, pipeline_slot + 1, joint_slot + 1):
                    continue
                fingerprint = self._row_fingerprint(values, list(range(1, len(values) + 1)))
                key = str(row_number)
                fingerprints[key] = fingerprint
                if next_cursor["row_fingerprints"].get(key) != fingerprint:
                    changed_row_numbers.append(row_number)
            next_cursor["row_fingerprints"] = fingerprints

            # Exact contiguous runs keep the second read limited to cells from
            # changed rows.  A row has at most ``column_count`` cells, so each
            # range is separately chunked below the Tencent limit.
            data_rows_per_request = max(1, self.MAX_CELLS_PER_REQUEST // column_count)
            changed_runs: list[tuple[int, int]] = []
            for row_number in changed_row_numbers:
                if changed_runs and row_number == changed_runs[-1][1] + 1:
                    changed_runs[-1] = (changed_runs[-1][0], row_number)
                else:
                    changed_runs.append((row_number, row_number))
            for run_start, run_end in changed_runs:
                for chunk_start in range(run_start, run_end + 1, data_rows_per_request):
                    chunk_end = min(run_end, chunk_start + data_rows_per_request - 1)
                    rows = self._fetch_range(
                        file_id,
                        actual_sheet_id,
                        f"A{chunk_start}:{end_column}{chunk_end}",
                    )
                    changed_values.extend(rows)
                    changed_source_rows.extend(
                        chunk_start + row_offset for row_offset in range(len(rows))
                    )
                    fetched_cells += (chunk_end - chunk_start + 1) * column_count

        start_row = max(header_row + 1, last_data_row + 1)
        first_key_column = min(pipeline_column, joint_column)
        last_key_column = max(pipeline_column, joint_column)
        key_width = last_key_column - first_key_column + 1
        scan_rows_per_request = max(1, self.MAX_CELLS_PER_REQUEST // key_width)
        newest_data_row = last_data_row
        key_start_column = _column_name(first_key_column)
        key_end_column = _column_name(last_key_column)

        for chunk_start in range(start_row, row_count + 1, scan_rows_per_request):
            chunk_end = min(row_count, chunk_start + scan_rows_per_request - 1)
            key_rows = self._fetch_range(
                file_id,
                actual_sheet_id,
                f"{key_start_column}{chunk_start}:{key_end_column}{chunk_end}",
            )
            scanned_cells += (chunk_end - chunk_start + 1) * key_width
            for offset, row in enumerate(key_rows):
                if not isinstance(row, list):
                    continue
                # The compact range starts at first_key_column, so evaluate the
                # two keys by their relative positions rather than their old
                # absolute sheet columns.
                if self._row_has_record_key(
                    row,
                    pipeline_column - first_key_column + 1,
                    joint_column - first_key_column + 1,
                ):
                    newest_data_row = chunk_start + offset

        appended_values: list[list] = []
        appended_source_rows: list[int] = []
        if newest_data_row > last_data_row:
            if not header_values:
                header_values = self._fetch_range(
                    file_id, actual_sheet_id, f"A{header_row}:{end_column}{header_row}"
                )
                fetched_cells += column_count
            data_rows_per_request = max(1, self.MAX_CELLS_PER_REQUEST // column_count)
            for chunk_start in range(start_row, newest_data_row + 1, data_rows_per_request):
                chunk_end = min(newest_data_row, chunk_start + data_rows_per_request - 1)
                rows = self._fetch_range(
                    file_id,
                    actual_sheet_id,
                    f"A{chunk_start}:{end_column}{chunk_end}",
                )
                appended_values.extend(rows)
                appended_source_rows.extend(
                    chunk_start + row_offset for row_offset in range(len(rows))
                )
                fetched_cells += (chunk_end - chunk_start + 1) * column_count
                for row_offset, row in enumerate(rows):
                    if isinstance(row, list) and self._row_has_record_key(
                        row, pipeline_column, joint_column
                    ):
                        next_cursor["row_fingerprints"][str(chunk_start + row_offset)] = (
                            self._row_fingerprint(row, tracked_columns)
                        )

        next_cursor["last_data_row"] = newest_data_row
        rows_to_sync = [*changed_values, *appended_values]
        values = [*(header_values[:1] if rows_to_sync and header_values else []), *rows_to_sync]
        return values, next_cursor, {
            "mode": "incremental",
            "scanned_cells": scanned_cells,
            "fingerprint_cells": fingerprint_cells,
            "fetched_cells": fetched_cells,
            "new_last_data_row": newest_data_row,
            "changed_rows": len(changed_row_numbers),
            "modification_scan": check_existing_changes,
            # Internal metadata consumed by sync_document; it is removed
            # before the result is saved or returned by the polling API.
            "_source_row_numbers": [*changed_source_rows, *appended_source_rows],
        }
