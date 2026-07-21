"""Regression tests for atomic Tencent full-sheet snapshots."""
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.document import Document  # noqa: F401 - register table metadata
from app.models.rbac import User  # noqa: F401 - register table metadata
from app.models.welding import WeldingRecord
from app.services.tencent_docs import (
    parse_range_to_records,
    sync_document,
)


def _values(*data_rows):
    return [["腾讯表格标题"], ["管线号", "焊口号"], *data_rows]


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def run():
    parsed = parse_range_to_records(
        _values(["Z-11", "1"], ["Z-11", "1"]), include_source_rows=True
    )
    assert [record["_source_row"] for record in parsed] == [3, 4]

    db = _session()
    doc = SimpleNamespace(id=7, owner_id=None, project_id=None, department_id=None)
    db.add_all(
        [
            WeldingRecord(
                document_id=doc.id,
                source="tencent_doc",
                source_row=3,
                pipeline_no="OLD",
                joint_no="OLD-3",
            ),
            WeldingRecord(
                document_id=doc.id,
                source="tencent_doc",
                source_row=99,
                pipeline_no="STALE",
                joint_no="OLD-99",
            ),
        ]
    )
    db.commit()

    with patch("app.services.dashboard_service.notify_changed") as notify:
        result = sync_document(
            db,
            doc,
            _values(["Z-11", "1"], ["Z-11", "1"], ["P-2", "2"]),
            full_snapshot=True,
        )

    rows = (
        db.query(WeldingRecord)
        .filter(WeldingRecord.document_id == doc.id, WeldingRecord.source == "tencent_doc")
        .order_by(WeldingRecord.source_row)
        .all()
    )
    assert result["parsed_rows"] == 3
    assert result["active_rows"] == 3
    assert result["stale_removed"] == 1
    assert [row.source_row for row in rows] == [3, 4, 5]
    assert sum(row.pipeline_no == "Z-11" and row.joint_no == "1" for row in rows) == 2
    notify.assert_called_once()

    # A successful full read with identical values is intentionally silent:
    # it must neither mark every database row as updated nor make the big
    # screen repaint just because the polling interval elapsed.
    with patch("app.services.dashboard_service.notify_changed") as notify:
        unchanged = sync_document(
            db,
            doc,
            _values(["Z-11", "1"], ["Z-11", "1"], ["P-2", "2"]),
            full_snapshot=True,
        )
    assert unchanged["created"] == 0
    assert unchanged["updated"] == 0
    assert unchanged["unchanged"] == 3
    assert unchanged["stale_removed"] == 0
    notify.assert_not_called()

    # Incremental data carries its original worksheet row, so it updates the
    # second repeated Z-11 row without touching the first one.
    sync_document(
        db,
        doc,
        [["管线号", "焊口号"], ["Z-11", "1-REV"]],
        source_row_numbers=[4],
    )
    assert (
        db.query(WeldingRecord)
        .filter(WeldingRecord.document_id == doc.id, WeldingRecord.source_row == 4)
        .one()
        .joint_no
        == "1-REV"
    )

    result = sync_document(
        db,
        doc,
        _values(["P-DROP", "1"]),
        full_snapshot=True,
    )
    assert result["active_rows"] == 1
    assert result["stale_removed"] == 2
    assert (
        db.query(WeldingRecord)
        .filter(WeldingRecord.document_id == doc.id, WeldingRecord.source == "tencent_doc")
        .count()
        == 1
    )
    db.close()
    print("[OK] Tencent full snapshots keep duplicate business keys and remove stale cache rows")


if __name__ == "__main__":
    run()
