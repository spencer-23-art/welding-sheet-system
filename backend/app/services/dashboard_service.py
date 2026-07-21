"""焊接大屏统计服务。

单一数据源 = welding_records 表。本服务聚合出大屏所需的 6 类数据，
复刻 keshi/backend 的 excel_service 算法（KPI / 管线 / NG / 最新记录）。
带进程内版本缓存（按 行数 + 最大更新时间），数据变动时自动失效。
"""
import math
from datetime import date, timedelta
from threading import Lock
from typing import Callable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.welding import WeldingRecord
from app.services.converters import clean_str, parse_date, parse_ndt_ratio

# ---- 缓存（按 sheet_id 分桶；None 表示全量汇总）----
_cache_lock = Lock()
_cached_version: dict = {}  # sheet_id -> (count, max_updated_at)
_cached_data: dict = {}     # sheet_id -> computed data

# 数据变动回调（由 dashboard 路由注册，用于 WebSocket 广播）
_on_change_callback: Optional[Callable[[Optional[dict]], None]] = None


def register_change_callback(cb: Callable[[Optional[dict]], None]) -> None:
    global _on_change_callback
    _on_change_callback = cb


def notify_changed(change: Optional[dict] = None) -> None:
    """Invalidate aggregate data after a committed write and notify listeners.

    ``change`` is deliberately small metadata (currently the affected source
    document and pipelines).  The persisted records remain the last known-good
    dashboard snapshot; a failed Tencent import never reaches this point.
    """
    global _cached_version, _cached_data
    with _cache_lock:
        _cached_version = {}
        _cached_data = {}
    if _on_change_callback is not None:
        try:
            _on_change_callback(change)
        except Exception:
            pass


def _fetch_rows(db: Session, sheet_id: Optional[int] = None) -> list[dict]:
    """拉取统计所需的轻量字段（避免加载完整 ORM 对象）。

    sheet_id 给定时仅取该表（document_id）的数据，否则取全量汇总。
    """
    cols = [
        WeldingRecord.pipeline_no,
        WeldingRecord.joint_no,
        WeldingRecord.weld_date,
        WeldingRecord.actual_ndt_date,
        WeldingRecord.ndt_date,
        WeldingRecord.ndt_ratio,
        WeldingRecord.ndt_result_1,
        WeldingRecord.ndt_result_2,
        WeldingRecord.ndt_result_3,
        WeldingRecord.film_total,
        WeldingRecord.film_status,
        WeldingRecord.welder,
        WeldingRecord.ng_notice,
        WeldingRecord.audit_issue,
        WeldingRecord.heat_treatment_required,
        WeldingRecord.heat_treatment_date,
        WeldingRecord.heat_treatment_am,
        WeldingRecord.heat_treatment_an,
        WeldingRecord.heat_treatment_ao,
        WeldingRecord.heat_treatment_ap,
        WeldingRecord.document_id,  # 末位：供按表过滤/溯源
    ]
    q = db.query(*cols)
    if sheet_id is not None:
        q = q.filter(WeldingRecord.document_id == sheet_id)
    raw = q.all()
    rows = []
    for r in raw:
        ndt_date_parsed = parse_date(r[4])
        rows.append(
            {
                "pipeline_no": clean_str(r[0]),
                "joint_no": clean_str(r[1]),
                "weld_date": r[2],
                "actual_ndt_date": r[3],
                "ndt_date": r[4],
                "ndt_date_parsed": ndt_date_parsed,
                "ndt_ratio": r[5],
                "ndt_result_1": clean_str(r[6]),
                "ndt_result_2": clean_str(r[7]),
                "ndt_result_3": clean_str(r[8]),
                "film_total": r[9],
                "film_status": clean_str(r[10]),
                "welder": clean_str(r[11]),
                "ng_notice": clean_str(r[12]),
                "audit_issue": clean_str(r[13]),
                "heat_treatment_required": clean_str(r[14]),
                "heat_treatment_date": r[15],
                "heat_treatment_am": clean_str(r[16]),
                "heat_treatment_an": clean_str(r[17]),
                "heat_treatment_ao": clean_str(r[18]),
                "heat_treatment_ap": clean_str(r[19]),
                "doc_id": r[20],
            }
        )
    return rows


def _version(db: Session, sheet_id: Optional[int] = None) -> tuple:
    q = db.query(func.count(WeldingRecord.id))
    if sheet_id is not None:
        q = q.filter(WeldingRecord.document_id == sheet_id)
    cnt = q.scalar() or 0
    q2 = db.query(func.max(WeldingRecord.updated_at))
    if sheet_id is not None:
        q2 = q2.filter(WeldingRecord.document_id == sheet_id)
    mx = q2.scalar()
    return (cnt, mx.isoformat() if mx else None)


def _contains_ng(val: str) -> bool:
    return "不合格" in val


def _build_heat_treatment_analysis(rows: list[dict]) -> dict:
    """Aggregate AK/AL heat-treatment status for each required weld joint."""
    joints = []
    for row in rows:
        pipeline_no = clean_str(row.get("pipeline_no"))
        joint_no = clean_str(row.get("joint_no"))
        if not pipeline_no or not joint_no:
            continue
        if clean_str(row.get("heat_treatment_required")) != "是":
            continue
        completed_date = parse_date(row.get("heat_treatment_date"))
        completed = completed_date is not None
        joints.append(
            {
                "pipeline_no": pipeline_no,
                "joint_no": joint_no,
                "heat_treatment_required": True,
                "heat_treatment_completed": completed,
                "heat_treatment_date": completed_date.isoformat() if completed_date else None,
                "heat_treatment_am": clean_str(row.get("heat_treatment_am")),
                "heat_treatment_an": clean_str(row.get("heat_treatment_an")),
                "heat_treatment_ao": clean_str(row.get("heat_treatment_ao")),
                "heat_treatment_ap": clean_str(row.get("heat_treatment_ap")),
                "status": "已热处理" if completed else "待热处理",
            }
        )

    # Keep every F/G record.  Sorting by pipeline first makes all of a
    # pipeline's weld joints appear together in the operational list.
    joints.sort(key=lambda item: (item["pipeline_no"], item["joint_no"]))
    required_joints = len(joints)
    completed_joints = sum(item["heat_treatment_completed"] for item in joints)
    return {
        "summary": {
            "required_joints": required_joints,
            "completed_joints": completed_joints,
            "completion_rate": (
                round(completed_joints / required_joints, 4)
                if required_joints
                else 0.0
            ),
        },
        "joints": joints,
    }


def _compute(rows: list[dict]) -> dict:
    today = date.today()

    # ---------- KPI ----------
    total_pipelines = len({r["pipeline_no"] for r in rows if r["pipeline_no"]})
    total_joints = len(rows)
    completed_welds = sum(1 for r in rows if r["weld_date"] is not None)
    weld_completion_rate = round(completed_welds / total_joints, 4) if total_joints else 0.0

    def ndt_done(r: dict) -> bool:
        # 腾讯台账的探伤日期可能未单列填写，但一旦已有“探伤结果”即表示该
        # 焊口已完成探伤；否则大屏会把有合格/不合格结果的记录错误显示为未探伤。
        return r["actual_ndt_date"] is not None

    completed_ndt = sum(1 for r in rows if ndt_done(r))
    # AH（四方底片审核）为空即未审核；仅“已审”计入已审核道数。
    film_approved = sum(1 for r in rows if r["film_status"] == "已审")

    today_welds = sum(1 for r in rows if r["weld_date"] == today)
    today_ndt = sum(1 for r in rows if r["actual_ndt_date"] == today)

    weld_trend: dict[str, int] = {}
    ndt_trend: dict[str, int] = {}
    for r in rows:
        if r["weld_date"] is not None:
            weld_trend[r["weld_date"].isoformat()] = weld_trend.get(r["weld_date"].isoformat(), 0) + 1
        d = r["actual_ndt_date"]
        if d is not None:
            ndt_trend[d.isoformat()] = ndt_trend.get(d.isoformat(), 0) + 1

    # X-column first-pass results are a three-option field: blank / 合格 /
    # 不合格.  Blank cells do not participate in the first-pass pass rate.
    once_results = [
        r["ndt_result_1"] for r in rows if r["actual_ndt_date"] is not None
    ]
    ok_cnt = sum(value == "合格" for value in once_results)
    ng_cnt = sum(value == "不合格" for value in once_results)
    once_ndt_pass_rate = round(ok_cnt / (ok_cnt + ng_cnt), 4) if (ok_cnt + ng_cnt) else 0.0

    # O 列“探伤比例”已规范化为 ndt_ratio：100% 为 1.0。对每一条
    # 100% 焊口，仅 X 列出现“合格”或“不合格”才视为已完成一次探伤。
    # 不以探伤日期判断，严格按用户定义的 O / X 字段口径统计。
    full_ndt_joints = [
        row
        for row in rows
        if math.isclose(float(row.get("ndt_ratio") or 0), 1.0, abs_tol=1e-9)
    ]
    full_ndt_result_joints = sum(
        row.get("ndt_result_1") in {"合格", "不合格"}
        for row in full_ndt_joints
    )
    full_ndt_completion_rate = (
        round(full_ndt_result_joints / len(full_ndt_joints), 4)
        if full_ndt_joints
        else 0.0
    )

    kpi = {
        "total_pipelines": total_pipelines,
        "total_joints": total_joints,
        "completed_welds": completed_welds,
        "weld_completion_rate": weld_completion_rate,
        "completed_ndt": completed_ndt,
        "film_approved": film_approved,
        "today_welds": today_welds,
        "today_ndt": today_ndt,
        "daily_welding_trend": [{"date": k, "count": v} for k, v in sorted(weld_trend.items())],
        "daily_ndt_trend": [{"date": k, "count": v} for k, v in sorted(ndt_trend.items())],
        "once_ndt_pass_rate": once_ndt_pass_rate,
        "full_ndt_joints": len(full_ndt_joints),
        "full_ndt_result_joints": full_ndt_result_joints,
        "full_ndt_completion_rate": full_ndt_completion_rate,
    }

    # ---------- 管线聚合 ----------
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["pipeline_no"], []).append(r)

    pipelines = []
    for pno, grp in groups.items():
        tj = len(grp)
        cw = sum(1 for r in grp if r["weld_date"] is not None)
        wcr = round(cw / tj, 4) if tj else 0.0
        ratio = 0.0
        for r in grp:
            if r["ndt_ratio"] is not None:
                ratio = float(r["ndt_ratio"])
                break
        ratio = parse_ndt_ratio(ratio)
        required_ndt = int(math.ceil(tj * ratio))
        cndt = sum(1 for r in grp if ndt_done(r))
        ncr = round(cndt / required_ndt, 4) if required_ndt else 1.0
        if ncr > 1.0:
            ncr = 1.0
        ndt_failed = sum(
            1
            for r in grp
            if _contains_ng(r["ndt_result_1"]) or _contains_ng(r["ndt_result_2"]) or _contains_ng(r["ndt_result_3"])
        )
        pipelines.append(
            {
                "pipeline_no": pno,
                "total_joints": tj,
                "completed_welds": cw,
                "weld_completion_rate": wcr,
                "ndt_ratio": ratio,
                "required_ndt": required_ndt,
                "completed_ndt": cndt,
                "ndt_completion_rate": ncr,
                "ndt_failed": ndt_failed,
            }
        )
    pipelines.sort(key=lambda x: x["total_joints"], reverse=True)

    # ---------- NG 清单 ----------
    ng_list = []
    for r in rows:
        # Only an X-column first-pass failure enters the exception list.
        # A later repair/retest value must never create a new exception by
        # itself, and an initial pass never belongs on this list.
        if r["ndt_result_1"] != "不合格":
            continue
        second = r["ndt_result_2"]
        third = r["ndt_result_3"]
        # The list is already defined by X=不合格, so show only the Y/AA
        # retest progression rather than repeating the first-pass result.
        if second == "合格":
            # A successful second inspection closes the repair workflow, so
            # AA must not be shown even if historical data contains a value.
            ndt_result = "二次：合格"
        else:
            ndt_result = f"二次：{second or '未探'}；三次：{third or '未探'}"

        if second == "合格" or (second == "不合格" and third == "合格"):
            repair = "已返修合格"
        else:
            # Y 为空、Y 不合格且 AA 为空、或二三次均不合格，都仍是不合格。
            repair = "不合格"

        td = r["actual_ndt_date"]
        test_date = td.isoformat() if td is not None else ""
        ng_list.append(
            {
                "pipeline_no": r["pipeline_no"],
                "joint_no": r["joint_no"],
                "ndt_result": ndt_result,
                "repair_status": repair,
                "test_date": test_date,
                "audit_status": r["film_status"],
            }
        )
    ng_list.sort(key=lambda x: x["test_date"] or "", reverse=True)

    # ---------- 最新焊接 / 探伤 ----------
    weld_rows = [r for r in rows if r["weld_date"] is not None]
    weld_rows.sort(key=lambda r: r["weld_date"], reverse=True)
    latest_welds = [
        {
            "date": r["weld_date"].isoformat(),
            "pipeline_no": r["pipeline_no"],
            "joint_no": r["joint_no"],
            "welder": r["welder"],
            "status": "已焊接",
        }
        for r in weld_rows[:50]
    ]

    ndt_rows = [r for r in rows if ndt_done(r)]
    # 有结果但未填写日期的腾讯记录同样要展示，使用最小日期保证与有日期记录可排序。
    ndt_rows.sort(
        key=lambda r: (r["actual_ndt_date"] or date.min),
        reverse=True,
    )
    latest_ndt = []
    for r in ndt_rows[:50]:
        res = r["ndt_result_1"]
        if r["ndt_result_2"]:
            res = f"一次:{res};二次:{r['ndt_result_2']}" if res else r["ndt_result_2"]
        if r["ndt_result_3"]:
            res = f"{res};三次:{r['ndt_result_3']}" if res else r["ndt_result_3"]
        td = r["actual_ndt_date"]
        latest_ndt.append(
            {
                "date": td.isoformat() if td else None,
                "pipeline_no": r["pipeline_no"],
                "joint_no": r["joint_no"],
                "ndt_result": res or "已检测",
                "test_date": td.isoformat() if td else None,
                "audit_status": r["film_status"],
            }
        )

    # X is a three-state first-pass result.  Blank means not inspected and is
    # deliberately excluded from every first-pass quality denominator.
    valid_once_results = [
        row for row in rows if row.get("ndt_result_1") in {"合格", "不合格"}
    ]

    def first_pass_stats(group: list[dict]) -> dict:
        passed = sum(row.get("ndt_result_1") == "合格" for row in group)
        failed = sum(row.get("ndt_result_1") == "不合格" for row in group)
        total = passed + failed
        return {
            "inspected_joints": total,
            "passed_joints": passed,
            "failed_joints": failed,
            "once_pass_rate": round(passed / total, 4) if total else 0.0,
        }

    welder_groups: dict[str, list[dict]] = {}
    pipeline_quality_groups: dict[str, list[dict]] = {}
    unassigned_inspected = 0
    for row in valid_once_results:
        welder = row.get("welder") or ""
        if welder:
            welder_groups.setdefault(welder, []).append(row)
        else:
            unassigned_inspected += 1
        pipeline_quality_groups.setdefault(row.get("pipeline_no") or "未填写管线号", []).append(row)

    welders = []
    for welder, group in welder_groups.items():
        stats = first_pass_stats(group)
        stats.update(
            {
                "welder": welder,
                "pipeline_count": len(
                    {row.get("pipeline_no") for row in group if row.get("pipeline_no")}
                ),
            }
        )
        welders.append(stats)
    welders.sort(
        key=lambda item: (-item["inspected_joints"], item["once_pass_rate"], item["welder"])
    )

    quality_pipelines = []
    for pipeline_no, group in pipeline_quality_groups.items():
        stats = first_pass_stats(group)
        stats.update(
            {
                "pipeline_no": pipeline_no,
                "welder_count": len(
                    {row.get("welder") for row in group if row.get("welder")}
                ),
            }
        )
        quality_pipelines.append(stats)
    quality_pipelines.sort(
        key=lambda item: (-item["inspected_joints"], item["once_pass_rate"], item["pipeline_no"])
    )

    once_summary = first_pass_stats(valid_once_results)
    repaired_after_first_failure = sum(
        1
        for row in valid_once_results
        if row.get("ndt_result_1") == "不合格"
        and (
            row.get("ndt_result_2") == "合格"
            or (
                row.get("ndt_result_2") == "不合格"
                and row.get("ndt_result_3") == "合格"
            )
        )
    )
    first_failures = once_summary["failed_joints"]
    # NDT closure list: an X-column failure remains open only when the
    # following retests have not produced a passing result.  The condition is
    # intentionally explicit so a value in Y or AA cannot accidentally put a
    # first-pass pass (or a closed repair) into the operational closure list.
    unresolved_cases = [
        {
            "pipeline_no": row.get("pipeline_no") or "",
            "joint_no": row.get("joint_no") or "",
            "second_result": row.get("ndt_result_2") or "",
            "third_result": row.get("ndt_result_3") or "",
            "closure_status": "待处理 / 未闭环",
        }
        for row in valid_once_results
        if row.get("ndt_result_1") == "不合格"
        and row.get("ndt_result_2") in {"", "不合格"}
        and row.get("ndt_result_3") in {"", "不合格"}
    ]
    audit_issues = [
        {
            "pipeline_no": row.get("pipeline_no") or "",
            "joint_no": row.get("joint_no") or "",
            "issue": row.get("audit_issue") or "",
            "audit_status": row.get("film_status") or "待处理",
        }
        for row in rows
        if row.get("audit_issue")
    ]
    # An empty AH cell means the filmed weld has not yet been reviewed.  X is
    # deliberately required here: a blank X cell has not produced a film and
    # must not be mislabeled as an unreviewed film.
    unreviewed_films = [
        {
            "pipeline_no": row.get("pipeline_no") or "",
            "joint_no": row.get("joint_no") or "",
            "audit_status": "未审核",
        }
        for row in valid_once_results
        if not row.get("film_status")
    ]
    audited_joints = sum(
        row.get("film_status") == "已审" for row in valid_once_results
    )
    quality_analysis = {
        "summary": {
            **once_summary,
            "welder_count": len(welders),
            "unassigned_inspected": unassigned_inspected,
        },
        "welders": welders,
        "pipelines": quality_pipelines,
        "repair": {
            "first_failures": first_failures,
            "repaired_after_failure": repaired_after_first_failure,
            "unresolved_failures": len(unresolved_cases),
            "unresolved_cases": unresolved_cases,
        },
        "audit": {
            "inspected_joints": once_summary["inspected_joints"],
            "audited_joints": audited_joints,
            "pending_joints": once_summary["inspected_joints"] - audited_joints,
            "issue_count": len(audit_issues),
            "issues": audit_issues,
            "unreviewed_count": len(unreviewed_films),
            "unreviewed_films": unreviewed_films,
        },
    }
    heat_treatment_analysis = _build_heat_treatment_analysis(rows)

    return {
        "rows": rows,
        "kpi": kpi,
        "pipelines": pipelines,
        "ng_list": ng_list,
        "latest_welds": latest_welds,
        "latest_ndt": latest_ndt,
        "quality_analysis": quality_analysis,
        "heat_treatment_analysis": heat_treatment_analysis,
    }


def _get_model(db: Session, sheet_id: Optional[int] = None) -> dict:
    global _cached_version, _cached_data
    ver = _version(db, sheet_id)
    key = sheet_id
    with _cache_lock:
        if _cached_version.get(key) == ver and _cached_data.get(key):
            return _cached_data[key]
    data = _compute(_fetch_rows(db, sheet_id))
    with _cache_lock:
        _cached_version[key] = ver
        _cached_data[key] = data
    return data


# ---- 对外接口 ----
def get_kpi(db: Session, sheet_id: Optional[int] = None) -> dict:
    return _get_model(db, sheet_id)["kpi"]


def get_pipelines(db: Session, sheet_id: Optional[int] = None) -> list[dict]:
    return _get_model(db, sheet_id)["pipelines"]


def get_ndt_ng(db: Session, sheet_id: Optional[int] = None) -> list[dict]:
    return _get_model(db, sheet_id)["ng_list"]


def get_latest_welding(db: Session, sheet_id: Optional[int] = None) -> list[dict]:
    return _get_model(db, sheet_id)["latest_welds"]


def get_latest_ndt(db: Session, sheet_id: Optional[int] = None) -> list[dict]:
    return _get_model(db, sheet_id)["latest_ndt"]


def get_quality_analysis(db: Session, sheet_id: Optional[int] = None) -> dict:
    """Return first-pass welder, pipeline, repair and audit aggregates."""
    return _get_model(db, sheet_id)["quality_analysis"]


def get_heat_treatment_analysis(db: Session, sheet_id: Optional[int] = None) -> dict:
    """Return AK/AL weld-joint heat-treatment status for the big screen."""
    return _get_model(db, sheet_id)["heat_treatment_analysis"]


def _build_daily_pipeline_activity(
    rows: list[dict],
    selected_date: Optional[date],
    date_field: str,
) -> dict:
    """Summarise a single day's completed joints by pipeline plus a 14-day trend.

    ``weld_date`` is the R-column welding date and ``actual_ndt_date`` is the
    V-column inspection date.  The two activities intentionally remain
    independent so the dashboard can compare different days side by side.
    """
    dated_rows = [row for row in rows if row.get(date_field) is not None]
    available_dates = sorted({row[date_field] for row in dated_rows})
    selected = selected_date or (available_dates[-1] if available_dates else date.today())

    grouped: dict[str, int] = {}
    for row in dated_rows:
        if row[date_field] != selected:
            continue
        pipeline_no = row.get("pipeline_no") or "未填写管线号"
        grouped[pipeline_no] = grouped.get(pipeline_no, 0) + 1

    total_joints = sum(grouped.values())
    pipelines = [
        {
            "pipeline_no": pipeline_no,
            "completed_joints": count,
            "share": round(count / total_joints, 4) if total_joints else 0.0,
        }
        for pipeline_no, count in grouped.items()
    ]
    pipelines.sort(key=lambda item: (-item["completed_joints"], item["pipeline_no"]))

    counts_by_date: dict[date, int] = {}
    for row in dated_rows:
        item_date = row[date_field]
        counts_by_date[item_date] = counts_by_date.get(item_date, 0) + 1

    trend = []
    for offset in range(13, -1, -1):
        trend_date = selected - timedelta(days=offset)
        trend.append({"date": trend_date.isoformat(), "count": counts_by_date.get(trend_date, 0)})

    return {
        "selected_date": selected.isoformat(),
        "available_date_range": {
            "min": available_dates[0].isoformat() if available_dates else None,
            "max": available_dates[-1].isoformat() if available_dates else None,
        },
        "total_joints": total_joints,
        "pipeline_count": len(pipelines),
        "pipelines": pipelines,
        "trend": trend,
    }


def get_daily_pipeline_activity(
    db: Session,
    weld_date: Optional[date] = None,
    ndt_date: Optional[date] = None,
    sheet_id: Optional[int] = None,
) -> dict:
    """Return date-selectable daily welding and NDT completion activity."""
    rows = _get_model(db, sheet_id)["rows"]
    return {
        "welding": _build_daily_pipeline_activity(rows, weld_date, "weld_date"),
        "ndt": _build_daily_pipeline_activity(rows, ndt_date, "actual_ndt_date"),
    }


def get_pipeline_detail(db: Session, pipeline_no: str, sheet_id: Optional[int] = None) -> Optional[dict]:
    rows = _get_model(db, sheet_id)["rows"]
    grp = [
        r for r in rows
        if r["pipeline_no"] == pipeline_no
        and (sheet_id is None or r.get("doc_id") == sheet_id)
    ]
    if not grp:
        return None
    tj = len(grp)
    cw = sum(1 for r in grp if r["weld_date"] is not None)
    uncompleted = tj - cw
    wcr = round(cw / tj, 4) if tj else 0.0
    ratio = 0.0
    for r in grp:
        if r["ndt_ratio"] is not None:
            ratio = float(r["ndt_ratio"])
            break
    ratio = parse_ndt_ratio(ratio)
    required_ndt = int(math.ceil(tj * ratio))

    def ndt_done(r: dict) -> bool:
        return r["actual_ndt_date"] is not None

    cndt = sum(1 for r in grp if ndt_done(r))
    ncr = round(cndt / required_ndt, 4) if required_ndt else 1.0
    if ncr > 1.0:
        ncr = 1.0
    ndt_failed = sum(
        1
        for r in grp
        if _contains_ng(r["ndt_result_1"]) or _contains_ng(r["ndt_result_2"]) or _contains_ng(r["ndt_result_3"])
    )
    # X（一次探伤结果）为“合格”或“不合格”的焊口才算已拍片；空值不计。
    film_total = sum(
        1 for r in grp if r["ndt_result_1"] in {"合格", "不合格"}
    )
    film_approved = sum(1 for r in grp if r["film_status"] == "已审")
    # Keep every non-empty AI cell in source-row order.  The detail panel
    # displays the original audit-problem text and scrolls it when it spans
    # multiple weld joints, so repeated source entries must not be collapsed.
    audit_issues = [
        {
            "pipeline_no": r["pipeline_no"],
            "joint_no": r["joint_no"],
            "issue": r["audit_issue"],
        }
        for r in grp
        if r["audit_issue"]
    ]

    weld_dates = [r["weld_date"] for r in grp if r["weld_date"] is not None]
    ndt_dates = [
        value
        for r in grp
        for value in [r["actual_ndt_date"]]
        if value is not None
    ]
    return {
        "pipeline_no": pipeline_no,
        "total_joints": tj,
        "completed_welds": cw,
        "uncompleted_welds": uncompleted,
        "weld_completion_rate": wcr,
        "ndt_ratio": ratio,
        "required_ndt": required_ndt,
        "completed_ndt": cndt,
        "ndt_completion_rate": ncr,
        "ndt_failed": ndt_failed,
        "film_total": film_total,
        "film_approved": film_approved,
        "audit_issue": "\n".join(item["issue"] for item in audit_issues),
        "audit_issues": audit_issues,
        "last_welding_date": max(weld_dates).isoformat() if weld_dates else None,
        "last_ndt_date": max(ndt_dates).isoformat() if ndt_dates else None,
    }


def get_dashboard_payload(db: Session, sheet_id: Optional[int] = None) -> dict:
    """WebSocket 广播用的完整数据包（可按 sheet_id 取单表）。"""
    m = _get_model(db, sheet_id)
    return {
        "kpi": m["kpi"],
        "pipelines": m["pipelines"],
        "ndt_ng": m["ng_list"],
        "latest_welds": m["latest_welds"],
    }
