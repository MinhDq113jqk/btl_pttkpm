# Task 1 — Candidate scope and data reconciliation

- **Date:** 2026-10-01
- **Status:** `SCOPE_RECONCILED_NOT_FROZEN`
- **Purpose:** record the current candidate boundary and local-only data facts
  without exposing raw values or treating the result as a submission gate.

## 1. Candidate boundary

| Group | Files or path | Current disposition | Reason |
|---|---|---|---|
| Data-replay implementation | 7 modified tracked files; xem mục 1.1 | LOCAL VERIFIED — TASK 2 | Đã qua focused test và PostgreSQL disposable; chỉ được đưa vào candidate sau khi Task 5 freeze/re-run. |
| Source manifest | `documents/greencity-project/DATA_SOURCE_MANIFEST.json` | LOCAL ONLY — VERIFIED TASK 2 | Dry-run đã xác minh manifest khớp source hiện tại; checksum của nguồn thật được giữ local, loại khỏi Git và teacher package. |
| Frontend timing test | `greencity-app/tests/resident-ux.cjs` | LOCAL VERIFIED — TASK 3 | 18 controlled-API UX checks and a 13-check real-backend GF-01/GF-02 rehearsal passed locally; see `TASK3_FRONTEND_REAL_BACKEND_VERIFICATION.md`. |
| Untracked course artifacts | `btl.docx`, `greencity-use-case-full.puml`, `greencity-use-case-overview.html`, `greencity-use-case-overview.png`, `greencity-use-case-srs.drawio`, `greencity-use-case-srs.html` | HOLD FOR TASK 4 / USER-OWNER DECISION | They have not been linked, packaged or reviewed as part of the current candidate. |
| Real source and runtime database | `documents/greencity-project/excel-data/` and `green_city` | EXCLUDE | They are local-only and must not enter Git, the teacher package, logs or review material. |

This document does not stage, commit, delete or package anything. The candidate
cannot be frozen until the remaining HOLD items receive a disposition and Tasks
4–5 finish.

### 1.1 Proposed seven-file data-replay code slice

The seven implementation/test files are:

1. `backend/app/services/submission_data_operational_replay.py`
2. `backend/app/services/submission_data_replay.py`
3. `backend/scripts/load_submission_data.py`
4. `backend/scripts/test_isolated.py`
5. `backend/tests/test_submission_data_loader_gate.py`
6. `backend/tests/test_submission_data_security_parcel_replay.py`
7. `backend/tests/test_submission_data_service_request_replay.py`

These seven code/test files are the proposed published slice.
`documents/greencity-project/DATA_SOURCE_MANIFEST.json` was verified with them
in Task 2 but remains local metadata and is excluded from Git/package during
the 2026-10-02 cleanup. This inventory is not a candidate ID: Task 5 must record
a new immutable digest after all HOLD items are decided and verify that this
list has not changed.

## 2. Local data evidence

### Source preflight

At `2026-10-01T16:59:59Z`, preflight of the local source returned `PASS` with
12 workbooks, 101 decided rows, verified source checksums and 0 orphan rows.
There were 42 future timestamps, 0 future-terminal candidates and 36
`FUTURE_SCHEDULE` warnings. Planned schedules are non-blocking, but the
preflight must be rerun on any later source revision.

### Database aggregate

A `READ ONLY` query on database `green_city` recorded 61 base tables excluding
`alembic_version`, 38 non-empty tables and 272 rows in total. No row values,
credentials or personal data were read into this evidence.

The aggregate confirms that the database is populated. It does not prove the
source of every row, prove that no prior/demo data exists, or replace the
candidate-specific apply/verify, clean-clone, privacy or package gates.

## 3. Handoff to subsequent tasks

1. Task 2 đã xác minh local eight-file data-replay slice trên PostgreSQL
   disposable. Xem [TASK2_DATA_REPLAY_VERIFICATION.md](TASK2_DATA_REPLAY_VERIFICATION.md);
   kết quả không freeze candidate hoặc đóng Final Submission Gate.
2. Task 3 resolved the held frontend test with frontend and real-backend
   Golden-Flow evidence. See
   [TASK3_FRONTEND_REAL_BACKEND_VERIFICATION.md](TASK3_FRONTEND_REAL_BACKEND_VERIFICATION.md);
   this remains local evidence, not a Final Submission Gate result.
3. Task 4 decides whether the six untracked course artifacts belong in the
   teacher package, then performs document/package review without raw data.
4. Task 5 freezes one candidate and reruns every required gate on that exact
   candidate.
