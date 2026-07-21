"""Regression test for the date-selectable pipeline completion API."""
from datetime import date

from app.services.dashboard_service import _build_daily_pipeline_activity


def row(pipeline: str, weld_date=None, ndt_date=None) -> dict:
    return {
        "pipeline_no": pipeline,
        "weld_date": weld_date,
        "actual_ndt_date": ndt_date,
    }


def run():
    rows = [
        row("P-01", date(2026, 7, 1), date(2026, 7, 2)),
        row("P-01", date(2026, 7, 2), date(2026, 7, 2)),
        row("P-02", date(2026, 7, 2), None),
        row("P-02", date(2026, 7, 2), date(2026, 7, 3)),
        row("P-03", None, date(2026, 7, 3)),
    ]

    welding = _build_daily_pipeline_activity(rows, date(2026, 7, 2), "weld_date")
    assert welding["selected_date"] == "2026-07-02"
    assert welding["total_joints"] == 3
    assert welding["pipeline_count"] == 2
    assert welding["pipelines"] == [
        {"pipeline_no": "P-02", "completed_joints": 2, "share": 0.6667},
        {"pipeline_no": "P-01", "completed_joints": 1, "share": 0.3333},
    ]
    assert welding["trend"][-1] == {"date": "2026-07-02", "count": 3}

    ndt = _build_daily_pipeline_activity(rows, date(2026, 7, 3), "actual_ndt_date")
    assert ndt["total_joints"] == 2
    assert ndt["pipelines"][0]["pipeline_no"] == "P-02"
    assert ndt["pipelines"][0]["completed_joints"] == 1
    assert ndt["trend"][-1] == {"date": "2026-07-03", "count": 2}
    print("[OK] Daily pipeline welding and NDT activity stay independently date-selectable")


if __name__ == "__main__":
    run()
