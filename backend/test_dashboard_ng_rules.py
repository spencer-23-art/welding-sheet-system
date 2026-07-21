"""Regression tests for the Tencent X/Y/AA NDT exception workflow."""
from datetime import date

from app.services.dashboard_service import _compute


def row(joint_no: str, first: str, second: str = "", third: str = "") -> dict:
    return {
        "pipeline_no": "P-NG",
        "joint_no": joint_no,
        "weld_date": None,
        "actual_ndt_date": date(2026, 7, 16),
        "ndt_date": None,
        "ndt_date_parsed": None,
        "ndt_ratio": 1.0,
        "ndt_result_1": first,
        "ndt_result_2": second,
        "ndt_result_3": third,
        "film_total": None,
        "film_status": "",
        "welder": "",
        "ng_notice": "",
        "doc_id": 1,
    }


def run():
    result = _compute(
        [
            row("PASS", "合格", "不合格", "不合格"),  # initial pass is excluded
            row("Y-PASS", "不合格", "合格", "不合格"),
            row("Y-AA-FAIL", "不合格", "不合格", "不合格"),
            row("Y-AA-PASS", "不合格", "不合格", "合格"),
            row("Y-BLANK", "不合格"),
            row("AA-BLANK", "不合格", "不合格"),
        ]
    )
    actual = {item["joint_no"]: item for item in result["ng_list"]}
    assert set(actual) == {"Y-PASS", "Y-AA-FAIL", "Y-AA-PASS", "Y-BLANK", "AA-BLANK"}
    assert actual["Y-PASS"]["repair_status"] == "已返修合格"
    assert actual["Y-AA-PASS"]["repair_status"] == "已返修合格"
    assert actual["Y-AA-FAIL"]["repair_status"] == "不合格"
    assert actual["Y-BLANK"]["repair_status"] == "不合格"
    assert actual["AA-BLANK"]["repair_status"] == "不合格"
    assert actual["Y-BLANK"]["ndt_result"] == "二次：未探；三次：未探"
    assert actual["Y-PASS"]["ndt_result"] == "二次：合格"
    assert actual["Y-AA-PASS"]["ndt_result"] == "二次：不合格；三次：合格"
    print("[OK] Tencent X/Y/AA NDT exception workflow")


if __name__ == "__main__":
    run()
