"""Encrypt sensitive fields and add keyed Gmail identifier lookups."""

from alembic import op
import sqlalchemy as sa

from backend.security.encryption import blind_index, encrypt_text

revision = "0005_encrypt_sensitive_fields"
down_revision = "0004_sanitize_processed_details"
branch_labels = None
depends_on = None


FIELDS = {
    "applications": (
        "company_name", "position", "notes", "gmail_message_id", "gmail_thread_id",
    ),
    "integration_tokens": ("external_user_id", "access_token", "refresh_token"),
    "events": ("title", "source_message_id", "google_event_id"),
    "processed_messages": ("gmail_message_id", "gmail_thread_id"),
    "recruiter_responses": ("sender_email", "subject"),
}


def _encrypt_existing_rows():
    connection = op.get_bind()
    for table, columns in FIELDS.items():
        selected = ", ".join(("id", *columns))
        rows = connection.execute(sa.text(f"SELECT {selected} FROM {table}")).mappings()
        for row in rows:
            values = {
                column: encrypt_text(row[column], context=f"{table}.{column}")
                for column in columns
                if row[column] is not None
            }
            if table == "applications":
                values["gmail_message_lookup"] = blind_index(
                    row["gmail_message_id"], context="applications.gmail_message_id"
                )
                values["gmail_thread_lookup"] = blind_index(
                    row["gmail_thread_id"], context="applications.gmail_thread_id"
                )
            elif table == "events":
                values["source_message_lookup"] = blind_index(
                    row["source_message_id"], context="events.source_message_id"
                )
            elif table == "processed_messages":
                values["gmail_message_lookup"] = blind_index(
                    row["gmail_message_id"], context="processed_messages.gmail_message_id"
                )
                values["gmail_thread_lookup"] = blind_index(
                    row["gmail_thread_id"], context="processed_messages.gmail_thread_id"
                )
            if values:
                assignments = ", ".join(f"{name} = :{name}" for name in values)
                connection.execute(
                    sa.text(f"UPDATE {table} SET {assignments} WHERE id = :row_id"),
                    {**values, "row_id": row["id"]},
                )


def upgrade():
    with op.batch_alter_table("applications") as batch:
        batch.drop_constraint("uq_application_user_thread", type_="unique")
        batch.drop_index("ix_applications_gmail_message_id")
        batch.drop_index("ix_applications_gmail_thread_id")
        batch.alter_column("company_name", existing_type=sa.String(200), type_=sa.Text())
        batch.alter_column("position", existing_type=sa.String(200), type_=sa.Text())
        batch.alter_column("gmail_message_id", existing_type=sa.String(255), type_=sa.Text())
        batch.alter_column("gmail_thread_id", existing_type=sa.String(255), type_=sa.Text())
        batch.add_column(sa.Column("gmail_message_lookup", sa.String(64), nullable=True))
        batch.add_column(sa.Column("gmail_thread_lookup", sa.String(64), nullable=True))

    with op.batch_alter_table("events") as batch:
        batch.drop_constraint("uq_event_application_message", type_="unique")
        batch.drop_index("ix_events_source_message_id")
        batch.alter_column("title", existing_type=sa.String(100), type_=sa.Text())
        batch.alter_column("source_message_id", existing_type=sa.String(255), type_=sa.Text())
        batch.alter_column("google_event_id", existing_type=sa.String(255), type_=sa.Text())
        batch.add_column(sa.Column("source_message_lookup", sa.String(64), nullable=True))

    with op.batch_alter_table("processed_messages") as batch:
        batch.drop_constraint("uq_processed_user_message", type_="unique")
        batch.drop_index("ix_processed_messages_gmail_message_id")
        batch.alter_column("gmail_message_id", existing_type=sa.String(255), type_=sa.Text())
        batch.alter_column("gmail_thread_id", existing_type=sa.String(255), type_=sa.Text())
        batch.add_column(sa.Column("gmail_message_lookup", sa.String(64), nullable=True))
        batch.add_column(sa.Column("gmail_thread_lookup", sa.String(64), nullable=True))

    with op.batch_alter_table("integration_tokens") as batch:
        batch.alter_column("external_user_id", existing_type=sa.String(100), type_=sa.Text())

    with op.batch_alter_table("recruiter_responses") as batch:
        batch.alter_column("sender_email", existing_type=sa.String(255), type_=sa.Text())
        batch.alter_column("subject", existing_type=sa.String(255), type_=sa.Text())

    _encrypt_existing_rows()

    with op.batch_alter_table("applications") as batch:
        batch.create_index("ix_applications_gmail_message_lookup", ["gmail_message_lookup"])
        batch.create_index("ix_applications_gmail_thread_lookup", ["gmail_thread_lookup"])
        batch.create_unique_constraint(
            "uq_application_user_thread_lookup", ["user_id", "gmail_thread_lookup"]
        )
    with op.batch_alter_table("events") as batch:
        batch.create_index("ix_events_source_message_lookup", ["source_message_lookup"])
        batch.create_unique_constraint(
            "uq_event_application_message_lookup", ["application_id", "source_message_lookup"]
        )
    with op.batch_alter_table("processed_messages") as batch:
        batch.alter_column("gmail_message_lookup", existing_type=sa.String(64), nullable=False)
        batch.create_index("ix_processed_messages_gmail_message_lookup", ["gmail_message_lookup"])
        batch.create_index("ix_processed_messages_gmail_thread_lookup", ["gmail_thread_lookup"])
        batch.create_unique_constraint(
            "uq_processed_user_message_lookup", ["user_id", "gmail_message_lookup"]
        )


def downgrade():
    raise RuntimeError("Encrypted-field migration is forward-only; restore a verified backup")
