"""Database-level checks for the fixed-slot migration.

Run only against a disposable database whose name ends in ``_migration_test``.
"""

import os
import uuid

import psycopg
import pytest
from sqlalchemy.engine import make_url


def test_fixed_slot_constraints() -> None:
    if os.getenv("RUN_MIGRATION_TEST") != "1":
        pytest.skip("Set RUN_MIGRATION_TEST=1 for the disposable migration database")

    url = make_url(os.environ["DATABASE_URL"])
    if not url.database or not url.database.endswith("_migration_test"):
        pytest.fail("Migration tests require a database name ending in _migration_test")

    conninfo = url.set(drivername="postgresql").render_as_string(hide_password=False)
    user_id, first_team, second_team = (uuid.uuid4() for _ in range(3))

    with psycopg.connect(conninfo) as conn:
        try:
            assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0003_fixed_slots"
            conn.execute(
                "INSERT INTO app_users (id, email) VALUES (%s, %s)",
                (user_id, f"quest7-{user_id}@example.test"),
            )
            for team_id in (first_team, second_team):
                conn.execute(
                    "INSERT INTO teams (id, name, invite_token, owner_id) VALUES (%s, %s, %s, %s)",
                    (team_id, "Migration test", str(team_id), user_id),
                )

            def add_slot(team_id: uuid.UUID, start: str, end: str, author: uuid.UUID = user_id) -> None:
                conn.execute(
                    "INSERT INTO fixed_slots (id, team_id, created_by, starts_at, ends_at) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (uuid.uuid4(), team_id, author, start, end),
                )

            add_slot(first_team, "2026-11-16 10:00+03", "2026-11-16 11:00+03")
            add_slot(first_team, "2026-11-16 11:00+03", "2026-11-16 12:00+03")
            add_slot(second_team, "2026-11-16 10:30+03", "2026-11-16 11:30+03")

            with pytest.raises(psycopg.errors.ExclusionViolation):
                with conn.transaction():
                    add_slot(first_team, "2026-11-16 10:30+03", "2026-11-16 11:30+03")
            with pytest.raises(psycopg.errors.CheckViolation):
                with conn.transaction():
                    add_slot(first_team, "2026-11-16 13:00+03", "2026-11-16 12:00+03")
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                with conn.transaction():
                    add_slot(first_team, "2026-11-16 13:00+03", "2026-11-16 14:00+03", uuid.uuid4())

            assert conn.execute("SELECT count(*) FROM fixed_slots WHERE created_by = %s", (user_id,)).fetchone()[0] == 3
        finally:
            conn.rollback()
