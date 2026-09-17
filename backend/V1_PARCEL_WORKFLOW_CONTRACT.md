# V1 Parcel Workflow API

Task 2 builds on migration `0014` and exposes the staff-side intake and handover slice. Every route requires a Bearer session; tenant, active site and building grants come from the server-side `UserContext`.

## Routes

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/parcels` | Scoped, paginated queue; optional `building_id` and status filter |
| `POST` | `/api/v1/parcels` | Receive a parcel and create its recipient/PIN snapshots |
| `GET` | `/api/v1/parcels/{parcel_id}` | Scoped detail |
| `POST` | `/api/v1/parcels/{parcel_id}/ready` | `RECEIVED → READY_FOR_PICKUP` |
| `POST` | `/api/v1/parcels/{parcel_id}/handover` | Verify PIN and `READY_FOR_PICKUP → HANDED_OVER` |
| `POST` | `/api/v1/parcels/{parcel_id}/exception` | Record `RETURNED`, `LOST`, or `DAMAGED` with a reason |

Create and command requests require `Idempotency-Key`. State-changing bodies require `expected_version`; stale commands return `409 ERR-CONFLICT`. The database row is locked during a transition, so two commands cannot both hand over the same parcel.

## Roles and scope

`admin` and `director` may operate parcels across their active site. `cskh` and `security` require a matching building grant. Other roles and resident accounts receive `403 ERR-FORBIDDEN`; a parcel outside the active tenant/site/building scope is indistinguishable from a missing record (`404 ERR-SCOPE-NOTFOUND`).

## PIN and audit behavior

The create request accepts a PIN only to hash it immediately with the backend password hasher. Responses and persisted idempotency records never contain the PIN or hash. Failed verification increments a bounded attempt counter, locks the PIN for 15 minutes after five failures, and writes an audit event. Successful handover writes `ParcelHandedOver` audit/outbox records and the handover actor/time; it never edits recipient snapshots.

Case linkage, evidence attachments, resident self-service UI, and frontend screens are deliberately outside Task 2.
