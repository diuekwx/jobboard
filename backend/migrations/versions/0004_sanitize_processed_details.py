"""Remove potentially sensitive processed-message details."""

from alembic import op

revision = "0004_sanitize_processed_details"
down_revision = "0003_remove_response_body"
branch_labels = None
depends_on = None


def upgrade():
    # Older values sometimes included an email subject. Clear every historical
    # value because there is no reliable way to distinguish safe reason codes
    # from user-controlled message text.
    op.execute("UPDATE processed_messages SET detail = NULL")


def downgrade():
    # Removed message content cannot and should not be reconstructed.
    pass
