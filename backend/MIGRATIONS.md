# Database migrations

Run commands from the repository root using the project virtual environment.
Set `DATABASE_URL` to the intended database; Alembic also reads the root `.env`.
Examples below use PowerShell. Stop application writes during migration and
take a backup you have verified you can restore. Test on a restored copy first.

Fresh database:

```powershell
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic current
```

Existing database created before Alembic:

```powershell
.venv/Scripts/python.exe -m backend.adopt_database
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic check
```

Adoption compares the schema to the frozen `0001` baseline before stamping.
It refuses missing/extra tables, columns, type differences, and index or unique
constraint differences reported by Alembic. It does not print database contents.
Alembic comparison is not a comprehensive audit of check constraints or triggers;
review any custom database objects separately. Do not bypass validation with an
unverified `alembic stamp`.

Older PostgreSQL installations missing the event feature's `source_message_id`
or nullable `end_time` can run `python -m backend.migrate_events` on the restored
copy before adoption. Other schema variants require explicit reconciliation;
the migration does not guess how to preserve an unknown schema. Legacy SQLite
databases with native `UUID` declarations may also fail adoption because current
portable UUID storage uses `CHAR(32)` there. PostgreSQL continues to use native UUID.

Revision `0002` checks for unsupported application statuses, duplicate
user/provider tokens, and duplicate application/source-message events before
changing any data. Resolve those conflicts deliberately on the restored copy;
no automatic row deletion or token selection is performed. It maps `sent` to
`applied`. Supported statuses are `applied`, `process`, `assessment`, `interview`,
`offer`, and `rejected`; additional outcomes remain milestone 8 work.

Legacy timestamps without offsets are interpreted as UTC. PostgreSQL conversion
uses an explicit `AT TIME ZONE 'UTC'`, independent of the database session timezone.
Confirm that assumption against the installation's history before upgrading.
An incorrect timestamp originally produced by an import-time default cannot be
reconstructed by this migration. New ORM defaults run per insert/update, and
timestamps read from both SQLite and PostgreSQL carry UTC offsets. Application
dates remain dates. Naive datetime inputs are interpreted as UTC.

The token user/provider and application user/thread unique indexes cover their
ownership queries. Event application/start and recruiter-response application
indexes cover child lookups. Null event source IDs and null application thread
IDs allow multiple manual records.

Editing now uses `PATCH /job/{application_id}` with a UUID and a partial JSON
body containing `company`, `position`, `status`, or `notes`. The former `/update`
lookup by company and position was removed. Company and status cannot be null;
position and notes can be cleared. Unknown fields/statuses and invalid lengths
return validation errors. Application IDs are returned by creation and listing.

For subsequent changes:

```powershell
.venv/Scripts/python.exe -m alembic revision --autogenerate -m "describe change"
# Review generated migration, particularly data transformations.
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic check
.venv/Scripts/python.exe -m pytest backend/tests/test_database_foundation.py -q
```

Revision `0005_encrypt_sensitive_fields` requires `DATA_ENCRYPTION_KEY` and
`DATA_ENCRYPTION_KEY_ID`. Test the upgrade on a restored backup first. It
encrypts existing application details, Gmail identifiers and credentials,
event details, and recruiter headers. It also replaces plaintext Gmail-ID
indexes with keyed lookup indexes. The migration is forward-only; recovery
requires both the pre-migration backup and its matching application version.

Revision `0007_background_scan_jobs` adds the durable Gmail scan queue. Apply
it before starting `backend.scan_worker`; the worker does not create tables at
runtime. Existing application and Gmail ledger rows are unchanged.

These initial revisions are forward-only. Recover by restoring the backup and
the matching application version. `backend.create_tables` now delegates to
Alembic; it no longer drops tables or bypasses migrations.

Verification: disposable SQLite tests cover fresh/adopted schema convergence,
repeat upgrade, row retention, duplicate preflight, status migration and check
constraint, rejection of schema drift, UTC round trips, callable defaults, input
validation, and edit ownership. PostgreSQL execution and restoration rehearsal
remain required before applying this to a deployed database. No configured
database was migrated during implementation.
