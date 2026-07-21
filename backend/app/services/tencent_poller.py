"""Tencent Docs polling fallback and append-only incremental synchronisation."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.core.database import SessionLocal
from app.models.document import Document
from app.services import tencent_config as tc
from app.services import tencent_docs as td

logger = logging.getLogger("tencent_poller")

_running = False
_task = None
_wake = asyncio.Event()
_lock = asyncio.Lock()
# China Standard Time is fixed UTC+8 and has no daylight-saving transitions;
# using a fixed offset keeps the container and Windows development runtime
# independent from an optional IANA time-zone database package.
CHINA_TIMEZONE = timezone(timedelta(hours=8), "Asia/Shanghai")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_utc(value: str) -> datetime:
    """Parse both legacy naive UTC timestamps and timezone-aware values."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_token_expired(cfg: dict) -> bool:
    """Developer tokens are long lived; only a missing token is unusable."""
    return not bool(cfg.get("access_token"))


def get_state(db) -> dict:
    return tc.get_poll_state(db)


def _save_state(db, patch: dict) -> dict:
    """Merge state so an error never accidentally drops the sync cursor."""
    state = tc.get_poll_state(db)
    state.update(patch)
    tc.set_poll_state(db, state)
    return state


def _full_reconcile_due(cfg: dict, state: dict) -> bool:
    """Return whether a full-sheet reconciliation is due.

    ``full_reconcile_minutes`` takes precedence when configured, allowing an
    operator to choose a short full-refresh interval.  The legacy hourly
    setting remains as a backwards-compatible fallback.
    """
    if not state.get("incremental_cursor"):
        return True
    try:
        minutes = int(cfg.get("full_reconcile_minutes") or 0)
    except (TypeError, ValueError):
        minutes = 0
    if minutes > 0:
        interval_seconds = minutes * 60
    else:
        try:
            hours = int(cfg.get("full_reconcile_hours", 24))
        except (TypeError, ValueError):
            hours = 24
        interval_seconds = hours * 3600
    if interval_seconds <= 0:
        return False
    last_full_sync = state.get("last_full_sync")
    if not last_full_sync:
        return True
    try:
        elapsed = datetime.now(timezone.utc) - _parse_utc(last_full_sync)
    except (TypeError, ValueError):
        return True
    return elapsed.total_seconds() >= interval_seconds


def _modification_scan_due(cfg: dict, state: dict) -> bool:
    """Whether a low-cost append poll should also check existing row hashes."""
    try:
        minutes = int(cfg.get("modify_poll_interval_minutes", 60))
    except (TypeError, ValueError):
        minutes = 60
    if minutes <= 0:
        return False
    last_scan = state.get("last_modify_scan")
    if not last_scan:
        return True
    try:
        elapsed = datetime.now(timezone.utc) - _parse_utc(last_scan)
    except (TypeError, ValueError):
        return True
    return elapsed.total_seconds() >= minutes * 60


def _within_automatic_sync_window(cfg: dict, now: datetime | None = None) -> bool:
    """Return whether automatic Tencent calls are allowed at China local time.

    Defaults to 07:00 inclusive through 24:00 exclusive.  Hours are kept in
    config so the window can later be changed without a redeploy; an equal
    start/end means all day and an end before start supports overnight windows.
    """
    try:
        start_hour = int(cfg.get("poll_start_hour", 7))
        end_hour = int(cfg.get("poll_end_hour", 24))
    except (TypeError, ValueError):
        start_hour, end_hour = 7, 24
    start_hour = max(0, min(start_hour, 23))
    end_hour = max(0, min(end_hour, 24))
    local_now = now or datetime.now(CHINA_TIMEZONE)
    hour = local_now.hour
    if start_hour == end_hour:
        return True
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def _full_sync(
    db,
    client: td.TencentDocsClient,
    doc,
    book_id: str,
    sheet_id=None,
    source_cursor: dict | None = None,
) -> tuple[dict, dict]:
    """Read the whole sheet once and create the durable append cursor."""
    values = client.fetch_sheet_values(book_id, sheet_id, source_cursor=source_cursor)
    result = td.sync_document(db, doc, values, full_snapshot=True)
    sheet_title = td.first_cell_text(values)
    if sheet_title:
        tc.update_cfg(db, {"sheet_title": sheet_title})
    cursor = client.build_incremental_cursor(
        book_id,
        values,
        sheet_id,
        source_cursor=source_cursor,
    )
    result.update(
        {
            "mode": "full",
            "raw_rows": len(values),
            "incremental_cursor": {
                "header_row": cursor["header_row"],
                "last_data_row": cursor["last_data_row"],
            },
        }
    )
    return result, cursor


async def _do_poll(trigger: str = "poll") -> dict:
    """Perform one first/full or append-only sync and persist its state."""
    with SessionLocal() as db:
        cfg = tc.get_cfg(db)
        book_id = cfg.get("book_id") or cfg.get("default_book_id")
        if not book_id or not cfg.get("access_token"):
            return {"skipped": True, "reason": "book_id or access_token is not configured"}
        if trigger != "manual" and not _within_automatic_sync_window(cfg):
            return {
                "skipped": True,
                "reason": "outside automatic sync window (China time 07:00-24:00)",
                "local_time": datetime.now(CHINA_TIMEZONE).isoformat(timespec="minutes"),
            }

        doc = db.query(Document).filter_by(doc_type="welding_db").first()
        if not doc:
            _save_state(db, {"last_run": _now(), "last_error": "welding_db document not found"})
            return {"error": "welding_db document not found"}

        client = td.TencentDocsClient(cfg)
        state = tc.get_poll_state(db)
        try:
            if _full_reconcile_due(cfg, state):
                result, cursor = _full_sync(
                    db,
                    client,
                    doc,
                    book_id,
                    source_cursor=state.get("incremental_cursor"),
                )
                _save_state(
                    db,
                    {
                        "last_run": _now(),
                        "last_error": None,
                        "last_result": result,
                        "last_full_sync": _now(),
                        "last_modify_scan": _now(),
                        "incremental_cursor": cursor,
                        "last_trigger": trigger,
                    },
                )
                return result

            check_existing_changes = trigger in {"manual", "webhook"} or _modification_scan_due(cfg, state)
            values, cursor, detail = client.fetch_incremental_values(
                book_id,
                state["incremental_cursor"],
                check_existing_changes=check_existing_changes,
            )
            if detail.get("requires_full"):
                result, cursor = _full_sync(
                    db,
                    client,
                    doc,
                    book_id,
                    source_cursor=state.get("incremental_cursor"),
                )
                result["full_sync_reason"] = detail.get("reason")
                _save_state(
                    db,
                    {
                        "last_run": _now(),
                        "last_error": None,
                        "last_result": result,
                        "last_full_sync": _now(),
                        "last_modify_scan": _now(),
                        "incremental_cursor": cursor,
                        "last_trigger": trigger,
                    },
                )
                return result

            source_row_numbers = detail.pop("_source_row_numbers", None)
            result = (
                td.sync_document(
                    db,
                    doc,
                    values,
                    source_row_numbers=source_row_numbers,
                )
                if values
                else {
                    "parsed_rows": 0,
                    "created": 0,
                    "updated": 0,
                    "stale_removed": 0,
                    "snapshot": False,
                }
            )
            result.update(detail)
            state_patch = {
                "last_run": _now(),
                "last_error": None,
                "last_result": result,
                "incremental_cursor": cursor,
                "last_trigger": trigger,
            }
            if detail.get("modification_scan"):
                state_patch["last_modify_scan"] = _now()
            _save_state(db, state_patch)
            return result
        except Exception as exc:
            message = f"sync failed: {exc}"
            _save_state(db, {"last_run": _now(), "last_error": message, "last_trigger": trigger})
            return {"error": message}


async def run_once(trigger: str = "manual") -> dict:
    """Run once, serialised with the background poll and webhook events."""
    async with _lock:
        return await _do_poll(trigger)


async def _loop() -> None:
    global _running
    while _running:
        interval = 5
        enabled = False
        try:
            with SessionLocal() as db:
                cfg = tc.get_cfg(db)
                enabled = bool(cfg.get("poll_enabled", False))
                interval = max(1, int(cfg.get("poll_interval_minutes", 5)))
            if enabled:
                async with _lock:
                    await _do_poll("poll")
        except Exception:
            logger.exception("tencent poll loop error")
        try:
            await asyncio.wait_for(_wake.wait(), timeout=interval * 60)
        except asyncio.TimeoutError:
            pass
        _wake.clear()


def start() -> None:
    global _running, _task
    if _running:
        return
    _running = True
    _task = asyncio.create_task(_loop())


def stop() -> None:
    global _running
    _running = False
    _wake.set()


def trigger_now() -> None:
    _wake.set()
