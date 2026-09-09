"""Add archival, terminal outcomes, and reversible application actions."""

from alembic import op
import sqlalchemy as sa

from backend.db.types import UTCDateTime


revision = "0008_product_workflows"
down_revision = "0007_background_scan_jobs"
branch_labels = None
depends_on = None

STATUS_CHECK = (
    "status IN ('applied', 'process', 'assessment', 'interview', 'offer', "
    "'accepted', 'withdrawn', 'rejected')"
)


def upgrade():
    with op.batch_alter_table("applications") as batch:
        batch.drop_constraint("ck_application_status", type_="check")
        batch.create_check_constraint("ck_application_status", STATUS_CHECK)
        batch.add_column(sa.Column("archived_at", UTCDateTime(), nullable=True))

    op.create_table(
        "application_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("undo_payload", sa.Text(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("undone_at", UTCDateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_application_actions_user_id", "application_actions", ["user_id"])
    op.create_index("ix_application_actions_application_id", "application_actions", ["application_id"])
    op.create_index("ix_application_actions_action", "application_actions", ["action"])


def downgrade():
    raise RuntimeError("This product-workflow migration is forward-only; restore a verified backup")
