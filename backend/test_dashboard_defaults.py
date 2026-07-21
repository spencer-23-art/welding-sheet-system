"""Regression test for dashboard defaults used by Tencent Docs records."""

from app.services.dashboard_service import _compute


def run():
    result = _compute(
        [
            {
                "pipeline_no": "P-0",
                "joint_no": "J-0",
                "weld_date": None,
                "actual_ndt_date": None,
                "ndt_date": None,
                "ndt_date_parsed": None,
                "ndt_ratio": None,
                # The V-column NDT date is empty, so a result alone is not a
                # completed NDT record.
                "ndt_result_1": "合格",
                "ndt_result_2": "",
                "ndt_result_3": "",
                "film_total": None,
                "film_status": "",
                "welder": "",
                "ng_notice": "",
                "doc_id": 1,
            }
        ]
    )
    pipeline = result["pipelines"][0]
    assert pipeline["ndt_ratio"] == 0.0
    assert pipeline["required_ndt"] == 0
    assert result["kpi"]["completed_ndt"] == 0
    assert result["latest_ndt"] == []
    assert result["kpi"]["once_ndt_pass_rate"] == 0.0
    assert result["kpi"]["full_ndt_joints"] == 0
    assert result["kpi"]["full_ndt_result_joints"] == 0
    assert result["kpi"]["full_ndt_completion_rate"] == 0.0
    print("[OK] Blank NDT ratio defaults to 0%")


if __name__ == "__main__":
    run()
