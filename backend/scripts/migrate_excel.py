"""Excel 历史数据迁移脚本（一次性 / 可重跑）。

将「尿素信华安装焊接数据库.xlsx」(表头第 2 行，33 列) 迁移进 welding_records 表，
并与结构化焊接库文档(welding_db)关联。采用 upsert，重复运行安全。

用法:
  cd welding-sheet-system/backend
  python scripts/migrate_excel.py [--excel 路径.xlsx] [--doc-id N] [--limit N]
"""
import argparse
import os
import sys

# 允许以脚本方式直接 import app
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.rbac import User  # noqa: E402
from app.models.welding import COLUMN_DEFS, HEADER_TO_ATTR, WeldingRecord  # noqa: E402
from app.services.converters import clean_str, parse_date, parse_ndt_ratio, to_float, to_int  # noqa: E402

DEFAULT_EXCEL = r"C:\Users\Administrator\Desktop\keshi\尿素信华安装焊接数据库.xlsx"
ATTR_TYPE = {c[0]: c[2] for c in COLUMN_DEFS}


def _coerce(attr: str, raw):
    typ = ATTR_TYPE.get(attr, "str")
    if typ == "int":
        return to_int(raw)
    if typ == "float":
        return to_float(raw)
    if typ == "date":
        return parse_date(raw)
    return clean_str(raw)


def _resolve_doc(db: Session, doc_id: int | None) -> Document:
    if doc_id is not None:
        doc = db.get(Document, doc_id)
        if doc is None:
            raise SystemExit(f"doc_id={doc_id} 不存在")
        return doc
    doc = (
        db.query(Document)
        .filter(Document.doc_type == "welding_db")
        .order_by(Document.id)
        .first()
    )
    if doc is not None:
        return doc
    # 兜底：创建一个 welding_db 文档
    owner = db.query(User).order_by(User.id).first()
    if owner is None:
        raise SystemExit("未找到任何用户，请先启动服务完成 seed")
    doc = Document(
        name="尿素信华焊接数据库",
        is_folder=False,
        doc_type="welding_db",
        owner_id=owner.id,
        project_id="A",
    )
    db.add(doc)
    db.flush()
    print("已创建 welding_db 文档:", doc.id)
    return doc


def _iter_excel(excel_path: str):
    import openpyxl

    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(min_row=2, values_only=True)
    try:
        header = next(rows)
    except StopIteration:
        raise SystemExit("Excel 无数据行")
    # 列 -> 属性（按中文表头反查，失败退化位置映射）
    col_to_attr: dict[int, str] = {}
    for c, h in enumerate(header):
        attr = HEADER_TO_ATTR.get(clean_str(h))
        if attr:
            col_to_attr[c] = attr
    if not col_to_attr:
        col_to_attr = {i: attr for i, (attr, _h, _t) in enumerate(COLUMN_DEFS)}
    print(f"识别到 {len(col_to_attr)} 个有效列")

    for vals in rows:
        rec: dict = {}
        for c, attr in col_to_attr.items():
            raw = vals[c] if c < len(vals) else None
            rec[attr] = _coerce(attr, raw)
        pno = (rec.get("pipeline_no") or "").strip()
        jno = (rec.get("joint_no") or "").strip()
        if pno == "" and jno == "":
            continue
        yield rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", default=DEFAULT_EXCEL)
    ap.add_argument("--doc-id", type=int, default=None)
    ap.add_argument("--limit", type=int, default=None, help="仅迁移前 N 行（调试用）")
    args = ap.parse_args()

    if not os.path.exists(args.excel):
        raise SystemExit(f"Excel 不存在: {args.excel}")

    db: Session = SessionLocal()
    try:
        doc = _resolve_doc(db, args.doc_id)
        print(f"目标文档: id={doc.id} name={doc.name}")

        # 预载已有行用于 upsert
        existing = {
            (r.pipeline_no, r.joint_no): r
            for r in db.query(WeldingRecord)
            .filter(WeldingRecord.document_id == doc.id)
            .all()
        }
        print(f"已存在记录: {len(existing)} 条")

        inserted = updated = skipped = 0
        batch = 0
        n = 0
        for rec in _iter_excel(args.excel):
            if args.limit is not None and (inserted + updated) >= args.limit:
                break
            key = (rec.get("pipeline_no") or "", rec.get("joint_no") or "")
            row = existing.get(key)
            if row is None:
                row = WeldingRecord(
                    document_id=doc.id,
                    owner_id=doc.owner_id,
                    project_id=doc.project_id,
                    department_id=doc.department_id,
                    source="excel",
                )
                db.add(row)
                existing[key] = row
                inserted += 1
            else:
                updated += 1
            # 写入全部字段
            for attr in ATTR_TYPE:
                if attr in rec:
                    setattr(row, attr, rec[attr])
            row.row_index = n
            n += 1
            # 探伤比例规范化
            if row.ndt_ratio is not None:
                row.ndt_ratio = parse_ndt_ratio(row.ndt_ratio)
            batch += 1
            if batch >= 2000:
                db.commit()
                batch = 0

        if batch:
            db.commit()
        print(f"迁移完成 -> 新增 {inserted}, 更新 {updated}, 跳过空行 {skipped}")
        total = db.query(WeldingRecord).filter(WeldingRecord.document_id == doc.id).count()
        print(f"文档 {doc.id} 当前焊接记录总数: {total}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
