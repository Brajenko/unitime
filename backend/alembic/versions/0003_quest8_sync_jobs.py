"""Track calendar sync jobs and pending publication."""

import sqlalchemy as sa
from alembic import op

revision = "0003_quest8_sync_jobs"
down_revision = "0002_users_teams"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("calendar_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("retries", sa.Integer(), nullable=False),
        sa.Column("process_count", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("activity_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("interval_count", sa.Integer()),
        sa.Column("error", sa.Text()),
    )
    op.create_index("ix_sync_jobs_connection_id", "sync_jobs", ["connection_id"])
    op.create_index("ix_sync_jobs_dispatch", "sync_jobs", ["status", "available_at"])


def downgrade() -> None:
    op.drop_table("sync_jobs")
