# V1 Parcel Data Foundation

Migration `0014` adds the durable `greencity.parcels` record for the parcel-to-case roadmap slice.

## Scope and invariants

- Every row is scoped by `tenant_id`, `site_id`, `building_id`, and `unit_id` through composite foreign keys.
- `site_id + parcel_code` is unique, so a retry cannot create the same parcel twice inside a site.
- Recipient and actor references are tenant-bound composite foreign keys.
- `recipient_name_snapshot` and contact snapshot are copied at receipt time; later identity edits do not rewrite parcel history.
- Only `pin_hash` is stored. Plaintext PINs are not a column or part of the migration contract.
- PIN attempts are bounded to `0..10`; hash values must meet the minimum encoded-hash length.
- `RETURNED`, `LOST`, and `DAMAGED` require an exception reason.
- `HANDED_OVER` requires both handover time and actor; all other states keep those fields empty.

## State contract

```text
RECEIVED -> READY_FOR_PICKUP -> HANDED_OVER
RECEIVED -> RETURNED | LOST | DAMAGED
READY_FOR_PICKUP -> RETURNED | LOST | DAMAGED
```

`HANDED_OVER`, `RETURNED`, `LOST`, and `DAMAGED` are terminal in the foundation contract. Application commands must enforce the transition map in `app.models.parcel.PARCEL_STATUS_TRANSITIONS`.

## Migration and verification

`0014_v1_parcel_foundation.py` revises `0013`. Downgrade refuses to remove the table while parcel rows exist; after an explicit data cleanup, downgrade to `0013` and re-upgrade to `0014` are supported.

The migration-path check is `python -m scripts.test_migration_0014` and is run by `scripts.test_isolated` before the full PostgreSQL regression. API commands, pickup verification, case linkage, attachments, and frontend screens are intentionally deferred to the next tasks.
