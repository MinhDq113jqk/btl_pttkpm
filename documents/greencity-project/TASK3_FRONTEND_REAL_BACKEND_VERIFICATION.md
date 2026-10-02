# Task 3 — Frontend and real-backend verification

- **Date:** 2026-10-01
- **Status:** `LOCAL VERIFIED — NOT A FINAL SUBMISSION GATE`
- **Scope:** Resident self-service frontend, GF-01/GF-02 rehearsal, and
  synthetic-import readback only.

## Result

Task 3 resolves the frontend-test HOLD from Task 1 with two local checks. It
does not freeze a candidate, approve a package, or complete the Final
Submission Gate.

| Check | Environment | Result | Evidence |
|---|---|---|---|
| Resident UX | Vite frontend with controlled API responses | PASS — 18 checks | `greencity-app/artifacts/resident-ux/test-results.json` and `resident-portal-mobile.png` |
| GF-01/GF-02 browser rehearsal | Real local backend + disposable PostgreSQL + synthetic import | PASS — 13 checks | `backend/.test-runtime/task3-real-browser-evidence/browser.log`, `n2-resident-request-created.png`, and `n2-resident-request-after-reload.png` |
| Imported-data restart readback | Same disposable database after synthetic apply and backend restart | PASS | `submission-preflight.log`, `submission-apply.log`, and `submission-post-restart-verify.log` |

The disposable import preflight processed 12 workbooks and 101 synthetic rows.
It reported zero orphan rows; the apply and post-restart verify logs both
reported `PASS`. The test never connected to `green_city` or used the raw Excel
source as a submission artifact.

## What was verified

The Resident UX test covered server-selected role and scope, empty state,
linked invalid-form feedback, visible network failure, stable idempotency key,
no forged scope fields, API-success-only display, timeline and evidence views,
integer-VND billing with one `as_of`, read-only invoice detail, notification
acknowledgement, mobile layout, and no browser page errors.

The real-backend browser rehearsal verified first-login password change,
login plus `/auth/me`, real service options/list, in-memory bearer session,
request creation, double-submit idempotency, reload plus re-authentication
readback, replaying the idempotency key, audit timeline, server-owned resident
site/unit scope, and no browser page errors.

## Boundaries and follow-up

- Only the `resident-ux.cjs` HOLD is resolved. The six untracked course
  artifacts remain a Task 4/User-Owner decision.
- The rehearsal proves local GF-01/GF-02 behavior on synthetic disposable
  data. It does **not** mark E2E-02..09, clean-clone, package scan, recovery,
  independent review, or any Final Submission Gate checkbox as complete.
- The Vite servers created for this test were stopped after verification. The
  reproducible evidence directory is local test output and must not be added
  to a teacher package without the later package/privacy review.
