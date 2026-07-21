"""Regression coverage for AK/AL heat-treatment dashboard rules."""
from datetime import date

from app.services.dashboard_service import _build_heat_treatment_analysis
from app.services.tencent_docs import TencentDocsClient, parse_range_to_records


def _sheet_row(
    pipeline: str,
    joint: str,
    required: str,
    completed: str,
    am: str = "",
    an: str = "",
    ao: str = "",
    ap: str = "",
) -> list[str]:
    row = [""] * 42
    row[5] = pipeline  # F
    row[6] = joint     # G
    row[36] = required  # AK
    row[37] = completed  # AL
    row[38] = am  # AM
    row[39] = an  # AN
    row[40] = ao  # AO
    row[41] = ap  # AP
    return row


def run():
    # A pre-feature cursor may have stopped at AL.  It must retain the proven
    # worksheet ID while extending its read through AP; a genuinely narrow
    # legacy sheet must still retain its original range.
    client = TencentDocsClient({"app_id": "client", "open_id": "open", "access_token": "token"})
    expanded_source = client._cached_sheet_source(
        {
            "file_id": "300000000$file",
            "sheet_id": "Sheet1",
            "pipeline_column": 6,
            "joint_column": 7,
            "tracked_columns": list(range(1, 36)),
            "column_count": 42,
        },
        None,
    )
    assert expanded_source is not None
    assert expanded_source["column_count"] == 42
    narrow_source = client._cached_sheet_source(
        {
            "file_id": "300000000$file",
            "sheet_id": "Sheet1",
            "pipeline_column": 5,
            "joint_column": 6,
            "tracked_columns": [1, 2, 3, 4, 5, 6],
            "column_count": 6,
        },
        None,
    )
    assert narrow_source is not None
    assert narrow_source["column_count"] == 6
    extended_source = client._cached_sheet_source(
        {
            "file_id": "300000000$file",
            "sheet_id": "Sheet1",
            "pipeline_column": 6,
            "joint_column": 7,
            "tracked_columns": list(range(1, 39)),
            "column_count": 38,
        },
        None,
    )
    assert extended_source is not None
    assert extended_source["column_count"] == 42

    header = [""] * 42
    header[5] = "管线号"
    header[6] = "焊口号"
    parsed = parse_range_to_records(
        [
            header,
            _sheet_row("HT-01", "J-01", "是", "1899-12-30", "AM-待处理", "AN-1", "AO-1", "AP-1"),
            _sheet_row("HT-02", "J-01", "是", "2026-07-19"),
        ]
    )
    assert parsed[0]["heat_treatment_required"] == "是"
    assert parsed[0]["heat_treatment_date"] is None
    assert parsed[0]["heat_treatment_am"] == "AM-待处理"
    assert parsed[0]["heat_treatment_an"] == "AN-1"
    assert parsed[0]["heat_treatment_ao"] == "AO-1"
    assert parsed[0]["heat_treatment_ap"] == "AP-1"
    assert parsed[1]["heat_treatment_date"] == date(2026, 7, 19)

    result = _build_heat_treatment_analysis(
        [
            {"pipeline_no": "HT-01", "joint_no": "J-01", "heat_treatment_required": "是", "heat_treatment_date": None, "heat_treatment_am": "AM-待处理", "heat_treatment_an": "AN-1", "heat_treatment_ao": "", "heat_treatment_ap": "AP-1"},
            {"pipeline_no": "HT-01", "joint_no": "J-02", "heat_treatment_required": "是", "heat_treatment_date": "1899-12-30"},
            {"pipeline_no": "HT-02", "joint_no": "J-01", "heat_treatment_required": "是", "heat_treatment_date": date(2026, 7, 19)},
            {"pipeline_no": "HT-03", "joint_no": "J-01", "heat_treatment_required": "", "heat_treatment_date": date(2026, 7, 18)},
            {"pipeline_no": "HT-04", "joint_no": "J-01", "heat_treatment_required": "是", "heat_treatment_date": None},
            {"pipeline_no": "HT-04", "joint_no": "J-02", "heat_treatment_required": "是", "heat_treatment_date": date(2026, 7, 20)},
        ]
    )
    assert result["summary"] == {
        "required_joints": 5,
        "completed_joints": 2,
        "completion_rate": round(2 / 5, 4),
    }
    assert result["joints"] == [
        {
            "pipeline_no": "HT-01",
            "joint_no": "J-01",
            "heat_treatment_required": True,
            "heat_treatment_completed": False,
            "heat_treatment_date": None,
            "heat_treatment_am": "AM-待处理",
            "heat_treatment_an": "AN-1",
            "heat_treatment_ao": "",
            "heat_treatment_ap": "AP-1",
            "status": "待热处理",
        },
        {
            "pipeline_no": "HT-01",
            "joint_no": "J-02",
            "heat_treatment_required": True,
            "heat_treatment_completed": False,
            "heat_treatment_date": None,
            "heat_treatment_am": "",
            "heat_treatment_an": "",
            "heat_treatment_ao": "",
            "heat_treatment_ap": "",
            "status": "待热处理",
        },
        {
            "pipeline_no": "HT-02",
            "joint_no": "J-01",
            "heat_treatment_required": True,
            "heat_treatment_completed": True,
            "heat_treatment_date": "2026-07-19",
            "heat_treatment_am": "",
            "heat_treatment_an": "",
            "heat_treatment_ao": "",
            "heat_treatment_ap": "",
            "status": "已热处理",
        },
        {
            "pipeline_no": "HT-04",
            "joint_no": "J-01",
            "heat_treatment_required": True,
            "heat_treatment_completed": False,
            "heat_treatment_date": None,
            "heat_treatment_am": "",
            "heat_treatment_an": "",
            "heat_treatment_ao": "",
            "heat_treatment_ap": "",
            "status": "待热处理",
        },
        {
            "pipeline_no": "HT-04",
            "joint_no": "J-02",
            "heat_treatment_required": True,
            "heat_treatment_completed": True,
            "heat_treatment_date": "2026-07-20",
            "heat_treatment_am": "",
            "heat_treatment_an": "",
            "heat_treatment_ao": "",
            "heat_treatment_ap": "",
            "status": "已热处理",
        },
    ]
    print("[OK] AK/AL heat-treatment rules aggregate by weld joint")


if __name__ == "__main__":
    run()
