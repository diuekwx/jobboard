"""Validate legacy data, standardize status, and enforce the foundation schema."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

STATUS_CHECK = "status IN ('applied', 'process', 'assessment', 'interview', 'offer', 'rejected')"
TIMESTAMPS = {
    "users": ["created_at"],
    "applications": ["created_at", "updated_at"],
    "integration_tokens": ["expires_at", "created_at", "updated_at"],
    "events": ["start_time", "end_time", "created_at"],
    "processed_messages": ["processed_at"],
    "recruiter_responses": ["received_at", "created_at"],
}


def upgrade():
    conn = op.get_bind()
    checks = {
        "applications contain unsupported statuses":
            "SELECT 1 FROM applications WHERE status NOT IN ('sent', 'applied', 'process', 'assessment', 'interview', 'offer', 'rejected') LIMIT 1",
        "integration_tokens contain duplicate user/provider pairs":
            "SELECT 1 FROM integration_tokens GROUP BY user_id, provider HAVING COUNT(*) > 1 LIMIT 1",
        "events contain duplicate application/message pairs":
            "SELECT 1 FROM events WHERE source_message_id IS NOT NULL GROUP BY application_id, source_message_id HAVING COUNT(*) > 1 LIMIT 1",
    }
    for reason, query in checks.items():
        if conn.execute(sa.text(query)).first():
            raise RuntimeError(reason + "; resolve on a backup copy before retrying")
    conn.execute(sa.text("UPDATE applications SET status = 'applied' WHERE status = 'sent'"))
    for table, columns in TIMESTAMPS.items():
        with op.batch_alter_table(table) as batch:
            for column in columns:
                batch.alter_column(
                    column, existing_type=sa.TIMESTAMP(), type_=sa.TIMESTAMP(timezone=True),
                    postgresql_using=f"{column} AT TIME ZONE 'UTC'",
                )
    with op.batch_alter_table("applications") as batch:
        batch.create_check_constraint("ck_application_status", STATUS_CHECK)
    with op.batch_alter_table("integration_tokens") as batch:
        batch.create_unique_constraint("uq_token_user_provider", ["user_id", "provider"])
    with op.batch_alter_table("events") as batch:
        batch.create_unique_constraint("uq_event_application_message", ["application_id", "source_message_id"])
    op.create_index("ix_recruiter_responses_application_id", "recruiter_responses", ["application_id"])


def downgrade():
    raise RuntimeError("This data migration is forward-only; restore a verified backup")
