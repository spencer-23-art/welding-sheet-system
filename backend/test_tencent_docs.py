"""腾讯文档同步的离线回归测试。"""
from datetime import date
from unittest.mock import patch

from app.services.tencent_docs import TencentDocsClient, header_to_attr, parse_range_to_records
from app.services.converters import parse_date, parse_ndt_ratio


class FakeResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code
        self.is_error = status_code >= 400

    def json(self):
        return self._body


def fake_get(url, **kwargs):
    if url.endswith("/util/converter"):
        assert kwargs["params"] == {"type": 2, "value": "DEncoded"}
        return FakeResponse({"ret": 0, "data": {"fileID": "300000000$file"}})
    if url.endswith("/sheets-info"):
        return FakeResponse(
            {
                "ret": 0,
                "data": {
                    "sheetData": [
                        {"sheetID": "Sheet1", "rowCount": 3, "columnCount": 3}
                    ]
                },
            }
        )
    if "/openapi/spreadsheet/v3/files/" in url:
        return FakeResponse(
            {
                "gridData": {
                    "rows": [
                        {
                            "values": [
                                {"cellValue": {"text": "管线号"}},
                                {"cellValue": {"text": "焊口号"}},
                                {"cellValue": {"text": "焊接日期"}},
                            ]
                        },
                        {
                            "values": [
                                {"cellValue": {"text": "P-1"}},
                                {"cellValue": {"text": "J-1"}},
                                {"cellValue": {"text": "2026-07-15"}},
                            ]
                        },
                    ]
                }
            }
        )
    raise AssertionError(f"Unexpected URL: {url}")


def run():
    client = TencentDocsClient(
        {"app_id": "client", "open_id": "open", "access_token": "token"}
    )
    assert client._cell_value(
        {"cellValue": {"time": {"year": 2026, "month": 7, "day": 15}}}
    ) == "2026-07-15"
    assert client._cell_value(
        {"cellValue": {"time": {"year": 1899, "month": 12, "day": 30}}}
    ) == ""
    assert parse_date("1899-12-30") is None
    assert client._cell_value(
        {
            "cellValue": {
                "select": {
                    "value": ["ok"],
                    "options": [{"id": "ok", "text": "合格"}],
                }
            }
        }
    ) == "合格"
    assert parse_ndt_ratio(None) == 0.0
    assert header_to_attr("一次探伤结果") == "ndt_result_1"
    assert header_to_attr("一次返修探伤结果") == "ndt_result_2"
    assert header_to_attr("二次返修探伤结果") == "ndt_result_3"
    with patch("app.services.tencent_docs.httpx.get", fake_get), patch(
        "app.services.tencent_docs.tcfg.record_api_call"
    ) as record_api_call:
        values = client.fetch_sheet_values("https://docs.qq.com/sheet/DEncoded")

    # Converter, sheet metadata, and one V3 range read are all Tencent API
    # calls and must be included in the daily quota counter.
    assert record_api_call.call_count == 3

    assert values[1] == ["P-1", "J-1", "2026-07-15"]
    # A previously successful full sync already knows the canonical file ID,
    # sheet ID and imported columns.  A later full refresh must reuse that
    # metadata: for this small sheet only the V3 data-range request is sent.
    prior_cursor = {
        "version": 2,
        "file_id": "300000000$file",
        "sheet_id": "Sheet1",
        "pipeline_column": 1,
        "joint_column": 2,
        "tracked_columns": [1, 2, 3],
        "last_data_row": 2,
    }
    with patch("app.services.tencent_docs.httpx.get", fake_get), patch(
        "app.services.tencent_docs.tcfg.record_api_call"
    ) as record_api_call:
        cached_values = client.fetch_sheet_values(
            "https://docs.qq.com/sheet/DEncoded", source_cursor=prior_cursor
        )
        refreshed_cursor = client.build_incremental_cursor(
            "https://docs.qq.com/sheet/DEncoded",
            cached_values,
            source_cursor=prior_cursor,
        )
    assert record_api_call.call_count == 1
    assert refreshed_cursor["file_id"] == "300000000$file"
    assert refreshed_cursor["sheet_id"] == "Sheet1"

    records = parse_range_to_records([["焊接数据库"], *values])
    assert records == [{"pipeline_no": "P-1", "joint_no": "J-1", "weld_date": date(2026, 7, 15)}]
    assert parse_range_to_records(
        [
            ["管线号", "焊口号", "备注实际探伤日期"],
            ["P-NDT", "J-EMPTY", "1899-12-30"],
            ["P-NDT", "J-DONE", "2026-07-16"],
        ]
    ) == [
        {"pipeline_no": "P-NDT", "joint_no": "J-EMPTY", "actual_ndt_date": None},
        {"pipeline_no": "P-NDT", "joint_no": "J-DONE", "actual_ndt_date": date(2026, 7, 16)},
    ]
    target_records = parse_range_to_records(
        [
            ["施工焊口台账"],
            [
                "管线号", "焊口号", "压力管道级别", "焊口规格\n外径*壁厚", "管道焊口材质",
                "焊口变更备注", "探伤方式\n备注：RT+TOFD", "一次探伤结果", "复探1",
                "复探2", "一次拍片合格数量", "一次拍片数量", "不合格数量", "检测单位",
                "底片审核状态", "不合格通知单", "焊接\n日期（实际）", "探伤结果（一次）",
                "底片审核（状态）",
            ],
            [
                "P-2", "J-2", "GC2", "114*6", "20#", "无", "RT", "不合格", "合格",
                "合格", "3", "4", "1", "检测公司", "已审核", "NG-01", "2026-07-14", "合格", "已审核",
            ],
        ]
    )
    assert target_records == [
        {
            "pipeline_no": "P-2", "joint_no": "J-2", "pipe_level": "GC2", "spec": "114*6",
            "material": "20#", "joint_remark": "无", "ndt_method": "RT",
            "ndt_result_2": "合格", "ndt_result_3": "合格", "film_count_1": 3,
            "film_total": 4, "ng_count": 1, "test_unit": "检测公司", "film_status": "已审核",
            "ng_notice": "NG-01", "weld_date": date(2026, 7, 14), "ndt_result_1": "合格",
        }
    ]
    assert parse_range_to_records(
        [["施工焊口台账"], ["管线号", "焊口号"], ["P-半填", ""]]
    ) == []
    print("[OK] Tencent Docs encoded ID conversion, V3 range read, and title-row parsing")


if __name__ == "__main__":
    run()
