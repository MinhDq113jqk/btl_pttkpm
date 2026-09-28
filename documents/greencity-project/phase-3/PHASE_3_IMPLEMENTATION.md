# Phase 3 implementation evidence

This phase adds a reproducible local deployment and operations rehearsal. It
does not establish production approval, owner sign-off, or a Go/No-Go decision.

## OR-11 — deployment target

`deploy/compose.yml` describes PostgreSQL, a non-root backend, the frontend,
and Caddy HTTPS termination. Caddy redirects HTTP to HTTPS and adds security
headers. The backend and migration job receive separate DSNs from mounted
secret files. The backend alone mounts the durable private-evidence volume;
Nginx and Caddy cannot read or serve its contents. The optional backup worker
gets read-only access through the backup group. `.dockerignore` excludes
credentials, dependency caches, generated artifacts, and project documents from
the build context.

Patch tags and dependency lockfiles are fixed to supported releases. Before a
pilot, record the resolved image digests and run a browser HTTPS smoke test.
The earlier N1–N5 snapshot could not access the Docker daemon; N6–N7 later
verified local Compose startup and the HTTPS smoke. Production/pilot evidence
remains open.

## OR-12 — database roles

`backend/scripts/phase3_provision_roles.py` provisions a `NOLOGIN` schema owner,
a `NOINHERIT` migrator that must `SET ROLE` to the owner, and a `NOINHERIT`
runtime role with DML and sequence privileges only. Alembic sets the owner role
on its migration connection. `phase3_runtime_role_test.py` exercises DML and
checks that DDL is denied for the actual runtime role.

## OR-13 — migrations and rollback

`phase3_migration_rehearsal.py` requires explicit opt-in and a loopback DSN. It
checks upgrade from empty, Alembic drift, downgrade to base, re-upgrade and
final revision `0017`. The unified runner executes this against a fresh,
disposable PostgreSQL/TLS cluster and configures the distinct roles first.

## OR-14 — private evidence

Evidence remains on the filesystem API, now backed in deployment by a dedicated
persistent volume. `private_storage.py` writes atomically with mode `0640` and
directories at `0750` for the application owner and restricted backup group,
rejects traversal and verifies SHA-256 and size before downloads. The volume is
never mounted into the frontend or proxy.
`deploy/STORAGE_POLICY.yaml` specifies ACL, encryption, lifecycle, quarantine
and tenant isolation controls. Encryption at rest must be supplied by the host
or managed storage provider; the local rehearsal does not claim it.

## OR-15 — backup and restore

The unified rehearsal dumps PostgreSQL as the runtime role, restores to a new
empty database, compares catalog and per-table row checksums, and verifies a
committed marker.
It also backs up two synthetic tenant objects, restores them to a clean path,
checks their checksums and rejects traversal. The report includes observed
backup and restore times; `rpo_observed_seconds: 0` means the latest committed
rehearsal marker was present after restore, not a production RPO commitment.

`deploy/compose.yml` includes an opt-in `scheduled-backup` profile. It writes a
database dump, private-evidence archive and checksum manifest to a separate
persistent volume, then removes only expired artifacts produced by this worker.
Before enabling it, governance must provide `BACKUP_RETENTION_DAYS` and
`BACKUP_INTERVAL_SECONDS`; neither is assigned a default. The backup volume
must use host/provider encryption before a pilot. The earlier N1–N5 snapshot
could not start this worker; N7 later ran one controlled scheduled-backup cycle
and restore against disposable data. This does not establish production RPO/RTO.

## Local command

From `backend`, run:

```powershell
.\.venv\Scripts\python.exe -m scripts.phase3_local_rehearsal `
  --pg-bin "C:\Program Files\PostgreSQL\18\bin" `
  --openssl "C:\Program Files\Git\usr\bin\openssl.exe"
```

The runner reads no `.env`, creates only a random cluster under
`backend/.test-runtime`, and shuts it down and removes it on completion.
The full backend runner also sets its pytest temporary directory inside that
workspace to avoid reliance on the Windows `%TEMP%` ACL.
## N1–N5 — follow-up rehearsal

`backend/scripts/phase3_real_backend_browser.py` starts a disposable
PostgreSQL/TLS cluster, Uvicorn and Vite, then runs the Playwright slice for
GF-01/GF-02 against the real API. It keeps demo credentials in the temporary
workspace and removes the cluster at shutdown. The run proved first-login
password change, resident scope, request persistence after reload, idempotency
and the resident audit timeline.

`backend/requirements.txt` and `requirements.lock.txt` now include `httpx2`
and Starlette 1.7.0. The fresh full isolated regression reports 295 passed, 1
skipped and 2 known deprecation warnings from the FastAPI/Starlette TestClient
and anyio compatibility path. `docker compose config` and the scheduled-backup
profile parse successfully. The N1–N5 snapshot recorded Docker engine access as
blocked; the subsequent N6–N7 evidence verifies local Compose startup, HTTPS and
one scheduled-backup/restore cycle. The disposable Phase 3 runner still proves
migration, role, database dump/restore and private-evidence checksum behavior
locally.

The detailed decision and evidence index are in
[N1-N5_EXECUTION_EVIDENCE.md](N1-N5_EXECUTION_EVIDENCE.md).

## V3-16 — presentation evidence

The consolidated local regression, Golden Flow, source scan and disposable
recovery checklist are in [V3-16_PRESENTATION_EVIDENCE.md](V3-16_PRESENTATION_EVIDENCE.md).
N8–N9 now record GF-03..08 real-browser runs against the local Compose/PostgreSQL
backend. Formal Gate/pilot/production approval, owner sign-off and deployment
target controls remain open; N6–N7 records the local container and recovery work.
