"""availability_windows: свободные окна, отмеченные вручную"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSTZRANGE

revision = "0004_availability"
down_revision = "0003_meetings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "availability_windows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("period", TSTZRANGE(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_availability_windows_user_id", "availability_windows", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_availability_windows_user_id", table_name="availability_windows")
    op.drop_table("availability_windows")
