"""Tencent credentials are encrypted at rest without changing callers."""
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.system import SystemConfig
from app.services import tencent_config as config


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SystemConfig.__table__.create(engine)

with Session(engine) as db:
    config.save_cfg(db, {"app_id": "client-id", "access_token": "secret-token"})
    raw = db.query(SystemConfig).filter_by(key=config.CONFIG_KEY).one()
    stored = json.loads(raw.value)
    assert stored["access_token"].startswith("enc:v1:")
    assert "secret-token" not in raw.value
    assert config.get_cfg(db)["access_token"] == "secret-token"

    # Legacy plaintext stays readable and migrates on the next save.
    raw.value = json.dumps({"access_token": "legacy-token"})
    db.commit()
    legacy = config.get_cfg(db)
    assert legacy["access_token"] == "legacy-token"
    assert config.migrate_access_token_encryption(db)
    db.refresh(raw)
    assert "legacy-token" not in raw.value
    assert not config.migrate_access_token_encryption(db)

print("[OK] Tencent access token encryption and plaintext migration")
