"""Remove the unused local-password credential column."""

from alembic import op
import sqlalchemy as sa


revision = "0006_remove_password_login"
down_revision = "0005_encrypt_sensitive_fields"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_column("hashed_password")


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("hashed_password", sa.String(), nullable=True))
