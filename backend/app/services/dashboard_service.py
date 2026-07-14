"""焊接大屏统计服务。

单一数据源 = welding_records 表。本服务聚合出大屏所需的 6 类数据，
复刻 keshi/backend 的 excel_service 算法（KPI / 管线 / NG / 最新记录）。
带进程内版本缓存（按 行数 + 最大更新时间），数据变动时自动失效。
"""
import math
from datetime import date, datetime
from threading import Lock
from typing import Any, Callable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.welding import WeldingRecord
from app.services.converters import clean_str, parse_date, parse_ndt_ratio

# ---- 缓存 ----
_cache_lock = Lock()
_cached_version: tuple = (None, None)  # (count, max_updated_at)
_cached_data: dict = {}

# 数据变动回调（由 dashboard 路由注册，用于 WebSocket 广播）
_on_change_callback: Optional[Callable[[], None]] = None


def register_change_callback(cb: Callable[[], None]) -> None:
    global _on_change_callback
    _on_change_callback = cb


def notify_changed() -> None:
    """数据写入后调用：清除缓存并触发广播回调。"""
    global _cached_version, _cached_data
    with _cache_lock:
        _cached_version = (None, None)
        _cached_data = {}
    if _on_change_callback is not None:
        try:
            _on_change_callback()
        except Exception:
            pass


def _fetch_rows(db: Session) -> list[dict]:
    """拉取统计所需的轻量字段（避免加载完整 ORM 对象）。"""
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
    ]
    raw = db.query(*cols).all()
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
            }
        )
    return rows


def _version(db: Session) -> tuple:
    cnt = db.query(func.count(WeldingRecord.id)).scalar() or 0
    mx = db.query(func.max(WeldingRecord.updated_at)).scalar()
    return (cnt, mx.isoformat() if mx else None)


def _contains_ng(val: str) -> bool:
    return "不合格" in val


def _compute(rows: list[dict]) -> dict:
    today = date.today()

    # ---------- KPI ----------
    total_pipelines = len({r["pipeline_no"] for r in rows if r["pipeline_no"]})
    total_joints = len(rows)
    completed_welds = sum(1 for r in rows if r["weld_date"] is not None)
    weld_completion_rate = round(completed_welds / total_joints, 4) if total_joints else 0.0

    def ndt_done(r: dict) -> bool:
        return r["actual_ndt_date"] is not None or r["ndt_date_parsed"] is not None

    completed_ndt = sum(1 for r in rows if ndt_done(r))
    film_approved = sum(1 for r in rows if "已审" in r["film_status"])

    today_welds = sum(1 for r in rows if r["weld_date"] == today)
    today_ndt = sum(
        1 for r in rows if (r["actual_ndt_date"] == today) or (r["ndt_date_parsed"] == today)
    )

    weld_trend: dict[str, int] = {}
    ndt_trend: dict[str, int] = {}
    for r in rows:
        if r["weld_date"] is not None:
            weld_trend[r["weld_date"].isoformat()] = weld_trend.get(r["weld_date"].isoformat(), 0) + 1
        d = r["actual_ndt_date"] or r["ndt_date_parsed"]
        if d is not None:
            ndt_trend[d.isoformat()] = ndt_trend.get(d.isoformat(), 0) + 1

    ok_cnt = ng_cnt = 0
    for r in rows:
        v = r["ndt_result_1"]
        if v:
            if _contains_ng(v):
                ng_cnt += 1
            elif "合格" in v:
                ok_cnt += 1
    once_ndt_pass_rate = round(ok_cnt / (ok_cnt + ng_cnt), 4) if (ok_cnt + ng_cnt) else 0.0

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
        ratio = 0.05
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
        is_ng = (
            _contains_ng(r["ndt_result_1"])
            or _contains_ng(r["ndt_result_2"])
            or _contains_ng(r["ndt_result_3"])
            or (r["ng_notice"] != "" and r["ng_notice"] != "/")
        )
        if not is_ng:
            continue
        results = []
        if r["ndt_result_1"]:
            results.append(f"一次:{r['ndt_result_1']}")
        if r["ndt_result_2"]:
            results.append(f"二次:{r['ndt_result_2']}")
        if r["ndt_result_3"]:
            results.append(f"三次:{r['ndt_result_3']}")
        ndt_result = "; ".join(results) if results else "不合格"

        repair = "未返修"
        if "合格" in r["ndt_result_2"] or "合格" in r["ndt_result_3"]:
            repair = "已返修合格"
        elif r["ndt_result_2"] == "不合格" or r["ndt_result_3"] == "不合格":
            repair = "返修后仍不合格"
        elif r["ndt_result_1"] == "不合格":
            repair = "待返修"

        td = r["actual_ndt_date"] or r["ndt_date_parsed"]
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
    ndt_rows.sort(key=lambda r: (r["actual_ndt_date"] or r["ndt_date_parsed"]), reverse=True)
    latest_ndt = []
    for r in ndt_rows[:50]:
        res = r["ndt_result_1"]
        if r["ndt_result_2"]:
            res = f"一次:{res};二次:{r['ndt_result_2']}" if res else r["ndt_result_2"]
        if r["ndt_result_3"]:
            res = f"{res};三次:{r['ndt_result_3']}" if res else r["ndt_result_3"]
        td = r["actual_ndt_date"] or r["ndt_date_parsed"]
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

    return {
        "rows": rows,
        "kpi": kpi,
        "pipelines": pipelines,
        "ng_list": ng_list,
        "latest_welds": latest_welds,
        "latest_ndt": latest_ndt,
    }


def _get_model(db: Session) -> dict:
    global _cached_version, _cached_data
    ver = _version(db)
    with _cache_lock:
        if ver == _cached_version and _cached_data:
            return _cached_data
    data = _compute(_fetch_rows(db))
    with _cache_lock:
        _cached_version = ver
        _cached_data = data
    return data


# ---- 对外接口 ----
def get_kpi(db: Session) -> dict:
    return _get_model(db)["kpi"]


def get_pipelines(db: Session) -> list[dict]:
    return _get_model(db)["pipelines"]


def get_ndt_ng(db: Session) -> list[dict]:
    return _get_model(db)["ng_list"]


def get_latest_welding(db: Session) -> list[dict]:
    return _get_model(db)["latest_welds"]


def get_latest_ndt(db: Session) -> list[dict]:
    return _get_model(db)["latest_ndt"]


def get_pipeline_detail(db: Session, pipeline_no: str) -> Optional[dict]:
    rows = _get_model(db)["rows"]
    grp = [r for r in rows if r["pipeline_no"] == pipeline_no]
    if not grp:
        return None
    tj = len(grp)
    cw = sum(1 for r in grp if r["weld_date"] is not None)
    uncompleted = tj - cw
    wcr = round(cw / tj, 4) if tj else 0.0
    ratio = 0.05
    for r in grp:
        if r["ndt_ratio"] is not None:
            ratio = float(r["ndt_ratio"])
            break
    ratio = parse_ndt_ratio(ratio)
    required_ndt = int(math.ceil(tj * ratio))

    def ndt_done(r: dict) -> bool:
        return r["actual_ndt_date"] is not None or r["ndt_date_parsed"] is not None

    cndt = sum(1 for r in grp if ndt_done(r))
    ncr = round(cndt / required_ndt, 4) if required_ndt else 1.0
    if ncr > 1.0:
        ncr = 1.0
    ndt_failed = sum(
        1
        for r in grp
        if _contains_ng(r["ndt_result_1"]) or _contains_ng(r["ndt_result_2"]) or _contains_ng(r["ndt_result_3"])
    )
    film_total = sum(int(r["film_total"]) for r in grp if r["film_total"] is not None)
    film_approved = sum(1 for r in grp if "已审" in r["film_status"])

    weld_dates = [r["weld_date"] for r in grp if r["weld_date"] is not None]
    ndt_dates = [(r["actual_ndt_date"] or r["ndt_date_parsed"]) for r in grp if ndt_done(r)]
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
        "last_welding_date": max(weld_dates).isoformat() if weld_dates else None,
        "last_ndt_date": max(ndt_dates).isoformat() if ndt_dates else None,
    }


def get_dashboard_payload(db: Session) -> dict:
    """WebSocket 广播用的完整数据包。"""
    m = _get_model(db)
    return {
        "kpi": m["kpi"],
        "pipelines": m["pipelines"],
        "ndt_ng": m["ng_list"],
        "latest_welds": m["latest_welds"],
    }
