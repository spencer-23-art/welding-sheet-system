"""腾讯文档配置读写（SystemConfig 单键存储）。

凭据与轮询配置都存于 system_config(key='tencent_docs')，不在代码里写死 .env，
管理员可在设置页填写 app_id/secret，token 30 天过期自行续期。
"""
import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from threading import Lock

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.system import SystemConfig

CONFIG_KEY = "tencent_docs"
POLL_STATE_KEY = "tencent_poll_state"
API_USAGE_KEY = "tencent_api_usage"
# China Standard Time is a fixed UTC+8 offset.  Keeping the business day here
# makes the counter independent of the server/container time zone.
CHINA_TIMEZONE = timezone(timedelta(hours=8), "Asia/Shanghai")
_api_usage_lock = Lock()
_TOKEN_PREFIX = "enc:v1:"


def _token_cipher() -> Fernet:
    digest = hashlib.sha256(settings.JWT_SECRET.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt_access_token(token: str) -> str:
    if not token or token.startswith(_TOKEN_PREFIX):
        return token
    encrypted = _token_cipher().encrypt(token.encode("utf-8")).decode("ascii")
    return f"{_TOKEN_PREFIX}{encrypted}"


def _decrypt_access_token(token: str) -> str:
    if not token or not token.startswith(_TOKEN_PREFIX):
        return token
    try:
        payload = token.removeprefix(_TOKEN_PREFIX).encode("ascii")
        return _token_cipher().decrypt(payload).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError):
        # A JWT secret rotation invalidates the encryption key. Treat the
        # credential as unavailable instead of sending ciphertext to Tencent.
        return ""


def get_cfg(db) -> dict:
    row = db.query(SystemConfig).filter_by(key=CONFIG_KEY).first()
    if not row or not row.value:
        return {}
    try:
        data = json.loads(row.value)
        if isinstance(data, dict) and isinstance(data.get("access_token"), str):
            data["access_token"] = _decrypt_access_token(data["access_token"])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_cfg(db, data: dict) -> None:
    row = db.query(SystemConfig).filter_by(key=CONFIG_KEY).first()
    if row is None:
        row = SystemConfig(key=CONFIG_KEY, value="")
        db.add(row)
    stored = dict(data)
    if isinstance(stored.get("access_token"), str):
        stored["access_token"] = _encrypt_access_token(stored["access_token"])
    row.value = json.dumps(stored, ensure_ascii=False)
    db.commit()


def migrate_access_token_encryption(db) -> bool:
    """Encrypt a legacy plaintext token once during application startup."""
    row = db.query(SystemConfig).filter_by(key=CONFIG_KEY).first()
    if not row or not row.value:
        return False
    try:
        stored = json.loads(row.value)
    except (TypeError, ValueError):
        return False
    token = stored.get("access_token") if isinstance(stored, dict) else None
    if not isinstance(token, str) or not token or token.startswith(_TOKEN_PREFIX):
        return False
    stored["access_token"] = _encrypt_access_token(token)
    row.value = json.dumps(stored, ensure_ascii=False)
    db.commit()
    return True


def update_cfg(db, patch: dict) -> dict:
    cfg = get_cfg(db)
    cfg.update(patch)
    save_cfg(db, cfg)
    return cfg


def get_poll_state(db) -> dict:
    row = db.query(SystemConfig).filter_by(key=POLL_STATE_KEY).first()
    if not row or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except Exception:
        return {}


def set_poll_state(db, data: dict) -> None:
    row = db.query(SystemConfig).filter_by(key=POLL_STATE_KEY).first()
    if row is None:
        row = SystemConfig(key=POLL_STATE_KEY, value="")
        db.add(row)
    row.value = json.dumps(data, ensure_ascii=False)
    db.commit()


def update_poll_state(db, patch: dict) -> dict:
    """Merge polling metadata without losing an existing incremental cursor."""
    state = get_poll_state(db)
    state.update(patch)
    set_poll_state(db, state)
    return state


def clear_poll_state(db) -> None:
    """Reset the cursor after the configured source workbook changes."""
    set_poll_state(db, {})


def _china_day(now: datetime | None = None) -> str:
    """Return the current calendar day in China time as an ISO date."""
    local_now = now or datetime.now(CHINA_TIMEZONE)
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=CHINA_TIMEZONE)
    else:
        local_now = local_now.astimezone(CHINA_TIMEZONE)
    return local_now.date().isoformat()


def _read_api_usage(row, day: str) -> dict:
    """Normalise a stored counter; an older date is logically already zero."""
    stored = {}
    if row and row.value:
        try:
            stored = json.loads(row.value)
        except Exception:
            stored = {}
    if stored.get("date") != day:
        return {"date": day, "count": 0}
    try:
        count = max(0, int(stored.get("count", 0)))
    except (TypeError, ValueError):
        count = 0
    return {"date": day, "count": count}


def get_api_usage(db, now: datetime | None = None) -> dict:
    """Read today's Tencent OpenAPI call count without mutating old records."""
    day = _china_day(now)
    row = db.query(SystemConfig).filter_by(key=API_USAGE_KEY).first()
    return _read_api_usage(row, day)


def record_api_call(now: datetime | None = None) -> dict:
    """Persist one attempted Tencent OpenAPI request for the China business day.

    The API client counts before sending the request, so failed/network-error
    attempts are included just like Tencent's own request accounting.  The
    service runs with one backend worker; this lock also protects concurrent
    manual-sync and polling calls in that process.
    """
    day = _china_day(now)
    with _api_usage_lock:
        db = SessionLocal()
        try:
            row = db.query(SystemConfig).filter_by(key=API_USAGE_KEY).first()
            usage = _read_api_usage(row, day)
            usage["count"] += 1
            if row is None:
                row = SystemConfig(key=API_USAGE_KEY, value="")
                db.add(row)
            row.value = json.dumps(usage, ensure_ascii=False)
            db.commit()
            return usage
        except Exception:
            db.rollback()
            # Telemetry must never prevent the source data from being synced.
            return {"date": day, "count": 0}
        finally:
            db.close()
