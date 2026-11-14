"""Prepare storage for fixed team meeting slots."""

from alembic import op
import sqlalchemy as sa

revision = "0003_fixed_slots"
down_revision = "0002_users_teams"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "fixed_slots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "isfinite(starts_at) AND isfinite(ends_at) AND starts_at < ends_at",
            name="ck_fixed_slots_valid_time",
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["app_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fixed_slots_team_starts_at", "fixed_slots", ["team_id", "starts_at"])
    op.execute(
        "ALTER TABLE fixed_slots ADD CONSTRAINT ex_fixed_slots_team_time "
        "EXCLUDE USING gist (team_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&)"
    )


def downgrade() -> None:
    op.drop_table("fixed_slots")
    # btree_gist may be shared by other database objects; do not remove it.
