"""Offline regression test for Tencent Docs append-only reads."""
import re

from app.services.tencent_docs import TencentDocsClient, parse_range_to_records


def _column_index(name: str) -> int:
    value = 0
    for char in name:
        value = value * 26 + ord(char) - 64
    return value


def _range_cell_count(cell_range: str) -> int:
    match = re.fullmatch(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", cell_range)
    assert match, cell_range
    start_column, start_row, end_column, end_row = match.groups()
    return (
        (_column_index(end_column) - _column_index(start_column) + 1)
        * (int(end_row) - int(start_row) + 1)
    )


def run():
    client = TencentDocsClient({"app_id": "client", "open_id": "open", "access_token": "token"})
    client.resolve_file_id = lambda _book_id: "300000000$file"  # type: ignore[method-assign]
    client._select_sheet = lambda _file_id, _sheet_id: {  # type: ignore[method-assign]
        "sheetID": "Sheet1", "rowCount": 12, "columnCount": 6
    }

    header = ["序号", "装置区", "介质", "等级", "管线号", "焊口号"]
    full_values = [["施工焊口台账"], header, [1, "A", "M", "L", "P-1", "J-1"]]
    cursor = client.build_incremental_cursor("https://docs.qq.com/sheet/DEncoded", full_values)
    assert cursor["header_row"] == 2
    assert cursor["last_data_row"] == 3
    assert (cursor["pipeline_column"], cursor["joint_column"]) == (5, 6)

    calls = []
    appended_rows = [
        [None, None, None, None, None, None],
        [2, "A", "M", "L", "P-2", "J-2"],
        [None, None, None, None, None, None],
        [None, None, None, None, None, None],
        [3, "A", "M", "L", "P-3", "J-3"],
    ]

    def fake_fetch(_file_id, _sheet_id, cell_range):
        calls.append(cell_range)
        if cell_range == "E4:F12":
            return [
                [None, None], ["P-2", "J-2"], [None, None],
                [None, None], ["P-3", "J-3"], [None, None],
                [None, None], [None, None], [None, None],
            ]
        if cell_range == "A2:F2":
            return [header]
        if cell_range == "A4:F8":
            return appended_rows
        if cell_range == "A3:C8":
            return [
                [1, "A", "M"], [None, None, None], [2, "B", "M"],
                [None, None, None], [None, None, None], [3, "A", "M"],
            ]
        if cell_range == "E3:F8":
            return [
                ["P-1", "J-1"], [None, None], ["P-2", "J-2"],
                [None, None], [None, None], ["P-3", "J-3"],
            ]
        if cell_range == "A5:F5":
            return [[2, "B", "M", "L", "P-2", "J-2"]]
        if cell_range == "E9:F12":
            return [[None, None], [None, None], [None, None], [None, None]]
        raise AssertionError(f"Unexpected range: {cell_range}")

    client._fetch_range = fake_fetch  # type: ignore[method-assign]
    values, next_cursor, detail = client.fetch_incremental_values("book", cursor)
    assert calls == ["E4:F12", "A2:F2", "A4:F8"]
    assert all(_range_cell_count(cell_range) <= 10_000 for cell_range in calls)
    assert detail["scanned_cells"] == 18
    assert detail["fetched_cells"] == 36
    assert detail["_source_row_numbers"] == [4, 5, 6, 7, 8]
    assert next_cursor["last_data_row"] == 8
    assert parse_range_to_records(values) == [
        {"seq": 2, "zone_code": "A", "medium": "M", "pipeline_no": "P-2", "joint_no": "J-2"},
        {"seq": 3, "zone_code": "A", "medium": "M", "pipeline_no": "P-3", "joint_no": "J-3"},
    ]

    calls.clear()
    values, stable_cursor, detail = client.fetch_incremental_values("book", next_cursor)
    assert values == []
    assert stable_cursor["last_data_row"] == 8
    assert detail["fetched_cells"] == 0
    assert detail["_source_row_numbers"] == []
    assert calls == ["E9:F12"]

    calls.clear()
    values, modified_cursor, detail = client.fetch_incremental_values(
        "book", stable_cursor, check_existing_changes=True
    )
    assert calls == ["A2:F2", "A3:C8", "E3:F8", "A5:F5", "E9:F12"]
    assert all(_range_cell_count(cell_range) <= 10_000 for cell_range in calls)
    assert detail["changed_rows"] == 1
    assert detail["modification_scan"] is True
    assert detail["_source_row_numbers"] == [5]
    assert parse_range_to_records(values) == [
        {"seq": 2, "zone_code": "B", "medium": "M", "pipeline_no": "P-2", "joint_no": "J-2"}
    ]
    assert modified_cursor["row_fingerprints"]["5"] != stable_cursor["row_fingerprints"]["5"]
    print("[OK] Tencent Docs incremental scan reads keys first and fetches only appended rows")


if __name__ == "__main__":
    run()
