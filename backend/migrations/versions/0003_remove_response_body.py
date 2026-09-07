"""Remove retained recruiter email bodies."""

from alembic import op
import sqlalchemy as sa

revision = "0003_remove_response_body"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("recruiter_responses") as batch:
        batch.drop_column("body")


def downgrade():
    with op.batch_alter_table("recruiter_responses") as batch:
        batch.add_column(sa.Column("body", sa.Text(), nullable=True))
