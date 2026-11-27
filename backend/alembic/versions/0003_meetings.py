"""meetings: зафиксированные встречи команды"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSTZRANGE

revision = "0003_meetings"
down_revision = "0002_users_teams"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "meetings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("period", TSTZRANGE(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["app_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "ALTER TABLE meetings ADD CONSTRAINT ex_meeting_overlap EXCLUDE USING gist (team_id WITH =, period WITH &&)"
    )


def downgrade() -> None:
    op.drop_table("meetings")
