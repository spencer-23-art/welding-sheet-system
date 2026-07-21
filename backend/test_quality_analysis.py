"""Regression test for X-column first-pass quality analysis."""
from app.services.dashboard_service import _compute


def row(welder: str, result: str, pipeline: str = "P-1", **extra) -> dict:
    return {
        "pipeline_no": pipeline,
        "joint_no": extra.pop("joint_no", "J-1"),
        "weld_date": None,
        "actual_ndt_date": None,
        "ndt_date": None,
        "ndt_date_parsed": None,
        "ndt_ratio": 0.0,
        "ndt_result_1": result,
        "ndt_result_2": extra.pop("ndt_result_2", ""),
        "ndt_result_3": extra.pop("ndt_result_3", ""),
        "film_total": None,
        "film_status": extra.pop("film_status", ""),
        "welder": welder,
        "ng_notice": "",
        "audit_issue": extra.pop("audit_issue", ""),
        "doc_id": 1,
        **extra,
    }


def run():
    result = _compute(
        [
            row("W-01", "合格", joint_no="1", film_status="已审"),
            row("W-01", "不合格", joint_no="2", ndt_result_2="合格"),
            row("W-01", "", joint_no="3"),  # Blank X is excluded.
            row("W-02", "不合格", "P-2", joint_no="4", audit_issue="视觉缺陷"),
            row("", "合格", "P-2", joint_no="5"),
        ]
    )["quality_analysis"]

    assert result["summary"] == {
        "inspected_joints": 4,
        "passed_joints": 2,
        "failed_joints": 2,
        "once_pass_rate": 0.5,
        "welder_count": 2,
        "unassigned_inspected": 1,
    }
    assert result["welders"][0]["welder"] == "W-01"
    assert result["welders"][0]["inspected_joints"] == 2
    assert result["welders"][0]["once_pass_rate"] == 0.5
    assert result["repair"] == {
        "first_failures": 2,
        "repaired_after_failure": 1,
        "unresolved_failures": 1,
        "unresolved_cases": [
            {
                "pipeline_no": "P-2",
                "joint_no": "4",
                "second_result": "",
                "third_result": "",
                "closure_status": "待处理 / 未闭环",
            }
        ],
    }
    assert result["audit"]["audited_joints"] == 1
    assert result["audit"]["issue_count"] == 1
    assert result["audit"]["unreviewed_count"] == 3
    assert result["audit"]["unreviewed_films"] == [
        {"pipeline_no": "P-1", "joint_no": "2", "audit_status": "未审核"},
        {"pipeline_no": "P-2", "joint_no": "4", "audit_status": "未审核"},
        {"pipeline_no": "P-2", "joint_no": "5", "audit_status": "未审核"},
    ]

    # Closure eligibility is the exact X → Y → AA rule used by the audit
    # screen.  A later pass closes the item; only blank/fail retests remain.
    closure_cases = _compute(
        [
            row("W", "不合格", joint_no="open-empty"),
            row("W", "不合格", joint_no="open-fail", ndt_result_2="不合格", ndt_result_3="不合格"),
            row("W", "不合格", joint_no="closed-third", ndt_result_2="不合格", ndt_result_3="合格"),
            row("W", "不合格", joint_no="closed-second", ndt_result_2="合格"),
            row("W", "合格", joint_no="not-first-fail", ndt_result_2="不合格", ndt_result_3="不合格"),
        ]
    )["quality_analysis"]["repair"]["unresolved_cases"]
    assert [(item["joint_no"], item["second_result"], item["third_result"]) for item in closure_cases] == [
        ("open-empty", "", ""),
        ("open-fail", "不合格", "不合格"),
    ]

    # O=100% is normalized to ndt_ratio=1.0. Only X=合格/不合格 counts
    # toward the dedicated full-coverage NDT completion KPI.
    full_ndt_kpi = _compute(
        [
            row("W", "合格", joint_no="full-pass", ndt_ratio=1.0),
            row("W", "不合格", joint_no="full-fail", ndt_ratio=1.0),
            row("W", "", joint_no="full-empty", ndt_ratio=1.0),
            row("W", "合格", joint_no="partial", ndt_ratio=0.2),
        ]
    )["kpi"]
    assert full_ndt_kpi["full_ndt_joints"] == 3
    assert full_ndt_kpi["full_ndt_result_joints"] == 2
    assert full_ndt_kpi["full_ndt_completion_rate"] == round(2 / 3, 4)
    print("[OK] Welder first-pass quality analysis excludes blank X results")


if __name__ == "__main__":
    run()
