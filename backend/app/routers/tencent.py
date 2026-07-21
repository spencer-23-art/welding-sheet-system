"""Tencent Docs configuration, secure webhooks, and sync controls."""
import base64
import hashlib
import json
import re
from datetime import datetime
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import tencent_config as tcfg
from app.services import tencent_docs as td
from app.services import tencent_poller as poller

router = APIRouter(prefix="/api/tencent", tags=["tencent"])


def _decode_jwt_claims(token: Optional[str]) -> dict:
    """Read the non-secret claims from a Tencent developer access token."""
    if not token or token.count(".") != 2:
        return {}
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def _now() -> str:
    return datetime.utcnow().isoformat()


def _webhook_token(request: Request, cfg: dict) -> Optional[str]:
    """Extract Tencent's signed JWT from the configured request header."""
    header_name = str(cfg.get("webhook_jwt_header") or "Authorization")
    value = request.headers.get(header_name)
    if not value:
        return None
    scheme, _, token = value.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else value.strip()


def _verify_webhook_request(request: Request, cfg: dict) -> dict:
    """Require a Tencent-signed event before a public callback can sync data."""
    public_key = str(cfg.get("webhook_public_key") or "").replace("\\n", "\n").strip()
    if not public_key:
        raise HTTPException(503, "Webhook public key has not been configured")
    token = _webhook_token(request, cfg)
    if not token:
        raise HTTPException(401, "Webhook signature is missing")
    try:
        return jwt.decode(
            token,
            public_key,
            algorithms=["RS256", "RS384", "RS512"],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Webhook signature verification failed") from exc


class ConfigIn(BaseModel):
    app_id: Optional[str] = None
    open_id: Optional[str] = None
    access_token: Optional[str] = None
    book_id: Optional[str] = None
    webhook_public_key: Optional[str] = None
    webhook_jwt_header: Optional[str] = None
    full_reconcile_hours: Optional[int] = None
    full_reconcile_minutes: Optional[int] = None
    modify_poll_interval_minutes: Optional[int] = None
    poll_start_hour: Optional[int] = None
    poll_end_hour: Optional[int] = None


@router.get("/config")
def get_config(db: Session = Depends(get_db)):
    cfg = tcfg.get_cfg(db)
    return {
        "app_id": cfg.get("app_id"),
        "open_id": cfg.get("open_id"),
        "has_token": bool(cfg.get("access_token")),
        "book_id": cfg.get("book_id") or cfg.get("default_book_id"),
        "sheet_title": cfg.get("sheet_title") or "",
        "poll_enabled": bool(cfg.get("poll_enabled", False)),
        "poll_interval_minutes": int(cfg.get("poll_interval_minutes", 5)),
        "poll_start_hour": int(cfg.get("poll_start_hour", 7)),
        "poll_end_hour": int(cfg.get("poll_end_hour", 24)),
        "modify_poll_interval_minutes": int(cfg.get("modify_poll_interval_minutes", 60)),
        "full_reconcile_hours": int(cfg.get("full_reconcile_hours", 24)),
        "full_reconcile_minutes": int(cfg.get("full_reconcile_minutes", 0)),
        "webhook_ready": bool(cfg.get("webhook_public_key")),
        "webhook_jwt_header": cfg.get("webhook_jwt_header") or "Authorization",
    }


@router.put("/config")
def put_config(
    body: ConfigIn,
    db: Session = Depends(get_db),
):
    cfg = tcfg.get_cfg(db)
    previous_book_id = cfg.get("book_id") or cfg.get("default_book_id")
    if body.access_token is not None:
        cfg["access_token"] = body.access_token
    claims = _decode_jwt_claims(body.access_token)
    if claims.get("clt"):
        cfg["app_id"] = claims["clt"]
    elif body.app_id is not None:
        cfg["app_id"] = body.app_id
    if claims.get("sub"):
        cfg["open_id"] = claims["sub"]
    elif body.open_id is not None:
        cfg["open_id"] = body.open_id
    if body.book_id is not None:
        cfg["book_id"] = body.book_id
    if body.webhook_public_key is not None:
        cfg["webhook_public_key"] = body.webhook_public_key
    if body.webhook_jwt_header is not None:
        cfg["webhook_jwt_header"] = body.webhook_jwt_header.strip() or "Authorization"
    if body.full_reconcile_hours is not None:
        cfg["full_reconcile_hours"] = max(0, int(body.full_reconcile_hours))
    if body.full_reconcile_minutes is not None:
        cfg["full_reconcile_minutes"] = max(0, int(body.full_reconcile_minutes))
    if body.modify_poll_interval_minutes is not None:
        cfg["modify_poll_interval_minutes"] = max(0, int(body.modify_poll_interval_minutes))
    if body.poll_start_hour is not None:
        cfg["poll_start_hour"] = max(0, min(23, int(body.poll_start_hour)))
    if body.poll_end_hour is not None:
        cfg["poll_end_hour"] = max(0, min(24, int(body.poll_end_hour)))
    tcfg.save_cfg(db, cfg)
    if body.book_id is not None and body.book_id != previous_book_id:
        tcfg.clear_poll_state(db)
    return {
        "ok": True,
        "app_id_from_token": bool(claims.get("clt")),
        "open_id_from_token": bool(claims.get("sub")),
    }


class SyncIn(BaseModel):
    book_id: str
    sheet_id: Optional[str] = None
    cell_range: Optional[str] = None


def _range_start_row(cell_range: Optional[str]) -> int:
    """Return the physical first row for a manually supplied A1 range."""
    if not cell_range:
        return 1
    match = re.fullmatch(r"\$?[A-Za-z]+\$?(\d+):\$?[A-Za-z]+\$?\d+", cell_range)
    return int(match.group(1)) if match else 1


@router.post("/sync")
def sync(
    body: SyncIn,
    db: Session = Depends(get_db),
):
    cfg = tcfg.get_cfg(db)
    if not cfg.get("access_token"):
        raise HTTPException(400, "Tencent Docs access token is not configured")
    client = td.TencentDocsClient(cfg)
    configured_book_id = cfg.get("book_id") or cfg.get("default_book_id")
    state = tcfg.get_poll_state(db)
    # A cursor belongs to exactly one configured source workbook.  Reusing its
    # canonical IDs avoids two metadata requests on every manual full refresh.
    source_cursor = (
        state.get("incremental_cursor")
        if not body.cell_range and body.book_id == configured_book_id
        else None
    )
    try:
        values = client.fetch_sheet_values(
            body.book_id,
            body.sheet_id,
            body.cell_range,
            source_cursor=source_cursor,
        )
    except Exception as exc:
        raise HTTPException(502, f"Tencent Docs read failed: {exc}") from exc
    if not values:
        raise HTTPException(502, "Tencent Docs returned no data")
    from app.models.document import Document

    doc = db.query(Document).filter_by(doc_type="welding_db").first()
    if not doc:
        raise HTTPException(404, "welding_db document not found")
    full_snapshot = not body.cell_range
    result = td.sync_document(
        db,
        doc,
        values,
        full_snapshot=full_snapshot,
        source_row_start=_range_start_row(body.cell_range),
    )
    sheet_title = td.first_cell_text(values)
    if sheet_title:
        tcfg.update_cfg(db, {"sheet_title": sheet_title})
    # A normal full/manual sync also seeds or refreshes the append cursor.
    if not body.cell_range and body.book_id == configured_book_id:
        try:
            cursor = client.build_incremental_cursor(
                body.book_id,
                values,
                body.sheet_id,
                source_cursor=source_cursor,
            )
            result.update({"mode": "full", "incremental_cursor": {
                "header_row": cursor["header_row"], "last_data_row": cursor["last_data_row"]
            }})
            tcfg.update_poll_state(
                db,
                {
                    "last_run": _now(),
                    "last_error": None,
                    "last_result": result,
                    "last_full_sync": _now(),
                    "last_modify_scan": _now(),
                    "incremental_cursor": cursor,
                    "last_trigger": "manual_full",
                },
            )
        except Exception as exc:
            # The data has already been safely imported; the next poll can make
            # a full pass if the cursor cannot be derived from this sheet.
            result["cursor_warning"] = str(exc)
    return {"ok": True, "result": result, "raw_rows": len(values)}


@router.post("/webhook")
async def webhook(req: Request, db: Session = Depends(get_db)):
    """Receive a signed Tencent event and immediately run incremental sync."""
    cfg = tcfg.get_cfg(db)
    _verify_webhook_request(req, cfg)
    raw_body = await req.body()
    try:
        json.loads(raw_body or b"{}")
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "Webhook body must be JSON") from exc

    book_id = cfg.get("webhook_book_id") or cfg.get("book_id") or cfg.get("default_book_id")
    if not book_id:
        raise HTTPException(503, "Tencent Docs book_id is not configured")
    event_digest = hashlib.sha256(raw_body).hexdigest()
    state = tcfg.get_poll_state(db)
    if state.get("last_webhook_digest") == event_digest:
        return {"ok": True, "duplicate": True}

    # Record before waiting for the serialised sync so a retransmitted event
    # does not double the Tencent API traffic.  Polling remains the fallback if
    # this specific run later fails.
    tcfg.update_poll_state(
        db,
        {"last_webhook_digest": event_digest, "last_webhook_at": _now()},
    )
    result = await poller.run_once("webhook")
    if result.get("error"):
        raise HTTPException(502, result["error"])
    return {"ok": True, "result": result}


class PollSetIn(BaseModel):
    enabled: Optional[bool] = None
    interval_minutes: Optional[int] = None
    book_id: Optional[str] = None
    full_reconcile_hours: Optional[int] = None
    full_reconcile_minutes: Optional[int] = None
    modify_poll_interval_minutes: Optional[int] = None
    start_hour: Optional[int] = None
    end_hour: Optional[int] = None


@router.get("/poll/status")
def poll_status(db: Session = Depends(get_db)):
    cfg = tcfg.get_cfg(db)
    state = poller.get_state(db)
    api_usage = tcfg.get_api_usage(db)
    cursor = state.get("incremental_cursor") or {}
    return {
        "enabled": bool(cfg.get("poll_enabled", False)),
        "interval_minutes": int(cfg.get("poll_interval_minutes", 5)),
        "start_hour": int(cfg.get("poll_start_hour", 7)),
        "end_hour": int(cfg.get("poll_end_hour", 24)),
        "modify_poll_interval_minutes": int(cfg.get("modify_poll_interval_minutes", 60)),
        "full_reconcile_hours": int(cfg.get("full_reconcile_hours", 24)),
        "full_reconcile_minutes": int(cfg.get("full_reconcile_minutes", 0)),
        "book_id": cfg.get("book_id") or cfg.get("default_book_id"),
        "has_token": bool(cfg.get("access_token")),
        "webhook_ready": bool(cfg.get("webhook_public_key")),
        "today_api_calls": api_usage["count"],
        "api_call_date": api_usage["date"],
        "last_run": state.get("last_run"),
        "last_error": state.get("last_error"),
        "last_result": state.get("last_result"),
        "last_full_sync": state.get("last_full_sync"),
        "last_modify_scan": state.get("last_modify_scan"),
        "incremental_cursor": {
            "header_row": cursor.get("header_row"),
            "last_data_row": cursor.get("last_data_row"),
        } if cursor else None,
    }


@router.post("/poll/set")
def poll_set(
    body: PollSetIn,
    db: Session = Depends(get_db),
):
    cfg = tcfg.get_cfg(db)
    old_book_id = cfg.get("book_id") or cfg.get("default_book_id")
    if body.enabled is not None:
        cfg["poll_enabled"] = body.enabled
    if body.interval_minutes is not None:
        cfg["poll_interval_minutes"] = max(1, int(body.interval_minutes))
    if body.book_id is not None:
        cfg["book_id"] = body.book_id
    if body.full_reconcile_hours is not None:
        cfg["full_reconcile_hours"] = max(0, int(body.full_reconcile_hours))
    if body.full_reconcile_minutes is not None:
        cfg["full_reconcile_minutes"] = max(0, int(body.full_reconcile_minutes))
    if body.modify_poll_interval_minutes is not None:
        cfg["modify_poll_interval_minutes"] = max(0, int(body.modify_poll_interval_minutes))
    if body.start_hour is not None:
        cfg["poll_start_hour"] = max(0, min(23, int(body.start_hour)))
    if body.end_hour is not None:
        cfg["poll_end_hour"] = max(0, min(24, int(body.end_hour)))
    tcfg.save_cfg(db, cfg)
    if body.book_id is not None and body.book_id != old_book_id:
        tcfg.clear_poll_state(db)
    poller.trigger_now()
    return {"ok": True}


@router.post("/poll/trigger")
async def poll_trigger(
    db: Session = Depends(get_db),
):
    result = await poller.run_once("manual")
    return {"ok": True, "result": result}
