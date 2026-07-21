# Tencent Snapshot Sync Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure the dashboard reflects exactly the latest Tencent sheet rows, including repeated business keys, without retaining deleted or replaced rows.

**Architecture:** Treat a successful whole-sheet read as an atomic cache snapshot. Each Tencent record is identified by its source worksheet row, not the business values in F/G; all rows are upserted and obsolete Tencent rows are deleted in one database commit. Incremental reads only update the returned source rows.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL production database, Tencent Docs V3 API, existing Python regression scripts.

---

### Task 1: Cover source-row parsing and snapshot replacement

**Files:**
- Modify: `backend/test_tencent_docs.py`
- Create: `backend/test_tencent_snapshot_sync.py`

**Step 1:** Assert parser output retains the physical source row number after the detected header.

**Step 2:** Build an in-memory SQLAlchemy fixture with old Tencent records, including duplicate pipeline/joint values and a stale row.

**Step 3:** Assert a full snapshot keeps duplicate business values as separate source rows, deletes stale Tencent rows, and reports the exact active count.

**Step 4:** Assert a smaller full snapshot removes prior Tencent rows and publishes only the latest source rows.

### Task 2: Make Tencent rows source-row keyed

**Files:**
- Modify: `backend/app/models/welding.py`
- Modify: `backend/app/seed.py`
- Modify: `backend/app/services/tencent_docs.py`

**Step 1:** Add nullable `source_row` metadata for physical Tencent row numbers and remove the old pipeline/joint uniqueness assumption.

**Step 2:** Add an idempotent production migration: add `source_row`, drop `uq_wr_doc_pipeline_joint`, and create a partial Tencent-only unique index on `(document_id, source_row)`.

**Step 3:** Parse records with `_source_row` metadata and upsert Tencent records by that number.

**Step 4:** On a full sync, update/create/delete Tencent rows in a single commit, so the committed cache exactly matches the latest source rows.

### Task 3: Apply snapshot semantics at sync boundaries

**Files:**
- Modify: `backend/app/routers/tencent.py`
- Modify: `backend/app/services/tencent_poller.py`

**Step 1:** Mark a no-range manual import and every reconciled poll as a full snapshot.

**Step 2:** Keep incremental reads non-destructive and preserve their source row identity.

**Step 3:** Persist full-sync result metadata, including the active cache row count and deleted stale-row count.

### Task 4: Verify and deploy

**Files:**
- Verify: `backend/test_tencent_docs.py`
- Verify: `backend/test_tencent_snapshot_sync.py`
- Verify: existing Tencent polling and dashboard tests

**Step 1:** Run the targeted regression scripts and static syntax checks.

**Step 2:** Build and deploy the backend; verify the migration and backend health.

**Step 3:** Run one manual full Tencent sync, then confirm the dashboard total equals the parsed source total and Z-11 is counted by source rows.
