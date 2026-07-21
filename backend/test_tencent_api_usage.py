"""Regression tests for the persistent China-time Tencent API usage counter."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.system import SystemConfig
from app.services import tencent_config as tcfg


def run():
    engine = create_engine("sqlite://")
    SystemConfig.__table__.create(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    china = timezone(timedelta(hours=8))
    before_midnight = datetime(2026, 7, 16, 23, 59, tzinfo=china)
    after_midnight = datetime(2026, 7, 17, 0, 0, tzinfo=china)

    with patch("app.services.tencent_config.SessionLocal", test_session):
        assert tcfg.record_api_call(before_midnight) == {
            "date": "2026-07-16",
            "count": 1,
        }
        assert tcfg.record_api_call(before_midnight) == {
            "date": "2026-07-16",
            "count": 2,
        }
        with test_session() as db:
            # No write is needed at midnight; a previous date is read as zero.
            assert tcfg.get_api_usage(db, after_midnight) == {
                "date": "2026-07-17",
                "count": 0,
            }
        assert tcfg.record_api_call(after_midnight) == {
            "date": "2026-07-17",
            "count": 1,
        }

    print("[OK] Tencent API usage is persisted and resets by China calendar day")


if __name__ == "__main__":
    run()
