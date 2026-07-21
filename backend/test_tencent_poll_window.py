"""Offline regression test for the Tencent automatic call window."""
from datetime import datetime

from app.services.tencent_poller import CHINA_TIMEZONE, _within_automatic_sync_window


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, 15, hour, minute, tzinfo=CHINA_TIMEZONE)


def run():
    default = {}
    assert not _within_automatic_sync_window(default, at(6, 59))
    assert _within_automatic_sync_window(default, at(7, 0))
    assert _within_automatic_sync_window(default, at(23, 59))
    assert not _within_automatic_sync_window(default, at(0, 0))

    overnight = {"poll_start_hour": 21, "poll_end_hour": 6}
    assert _within_automatic_sync_window(overnight, at(22))
    assert _within_automatic_sync_window(overnight, at(5, 59))
    assert not _within_automatic_sync_window(overnight, at(12))
    print("[OK] Tencent automatic calls are restricted to the configured China-time window")


if __name__ == "__main__":
    run()
