"""Merge the sync job and availability migration branches."""

revision = "0005_merge_sync_availability"
down_revision = ("0003_quest8_sync_jobs", "0004_availability")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
