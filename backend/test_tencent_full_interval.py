"""Regression test for minute-based full Tencent sheet refreshes."""
from datetime import datetime, timedelta, timezone

from app.services.tencent_poller import _full_reconcile_due


def state_ago(minutes: int) -> dict:
    return {
        "incremental_cursor": {"version": 2},
        "last_full_sync": (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat(),
    }


def run():
    assert not _full_reconcile_due({"full_reconcile_minutes": 10}, state_ago(9))
    assert _full_reconcile_due({"full_reconcile_minutes": 10}, state_ago(11))
    # A minute setting intentionally overrides the legacy daily/hourly value.
    assert _full_reconcile_due(
        {"full_reconcile_minutes": 10, "full_reconcile_hours": 24}, state_ago(11)
    )
    assert not _full_reconcile_due({"full_reconcile_hours": 1}, state_ago(59))
    print("[OK] Tencent full refresh supports a minute interval")


if __name__ == "__main__":
    run()
