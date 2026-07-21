"""Regression coverage for Tencent AH/AI audit fields."""

from app.services.tencent_docs import first_cell_text, parse_range_to_records


def run():
    assert first_cell_text([["30万吨甲醇精馏管道安装焊接数据库（809B）"]]) == "30万吨甲醇精馏管道安装焊接数据库（809B）"
    records = parse_range_to_records(
        [
            [
                "管线号",
                "焊口号",
                "一次探伤结果",
                "四方底片审核",
                "审核问题及闭环情况（问题描述清晰，整改完成后注明已闭环）",
            ],
            ["P-AUDIT", "J-01", "合格", "已审", "底片边缘需复核"],
            ["P-AUDIT", "J-02", "", "", ""],
        ]
    )

    assert records == [
        {
            "pipeline_no": "P-AUDIT",
            "joint_no": "J-01",
            "ndt_result_1": "合格",
            "film_status": "已审",
            "audit_issue": "底片边缘需复核",
        },
        {
            "pipeline_no": "P-AUDIT",
            "joint_no": "J-02",
            "ndt_result_1": "",
            "film_status": "",
            "audit_issue": "",
        },
    ]
    print("[OK] Tencent AH/AI audit fields are parsed")


if __name__ == "__main__":
    run()
