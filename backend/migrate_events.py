"""Bring an existing ``events`` table up to what the In-Process feature needs.

``Base.metadata.create_all`` only ever creates missing tables, so a database
that already has ``events`` will not pick up these changes on its own:

* ``source_message_id`` - the Gmail message an event was read out of, so
  re-syncing the same mail corrects the slot instead of duplicating it.
* ``end_time`` becomes nullable - most invites name a start and nothing else,
  and an assessment deadline has no end at all.

Idempotent; safe to run more than once. Postgres syntax::

    python -m backend.migrate_events
"""

from sqlalchemy import text

from backend.db.session import engine

STATEMENTS = [
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS source_message_id VARCHAR(255)",
    "ALTER TABLE events ALTER COLUMN end_time DROP NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_events_source_message_id "
    "ON events (source_message_id)",
    "CREATE INDEX IF NOT EXISTS ix_events_application_start "
    "ON events (application_id, start_time)",
]


def main() -> None:
    with engine.begin() as conn:
        for statement in STATEMENTS:
            conn.execute(text(statement))
            print(f"ok: {statement}")
    print("done - events table is up to date")


if __name__ == "__main__":
    main()
