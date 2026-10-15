"""Сквозная проверка API на реальном Postgres (RUN_INTEGRATION=1, DATABASE_URL на тестовую базу)."""
import os
import uuid
from datetime import datetime, timedelta

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1", reason="нужен Postgres: RUN_INTEGRATION=1")


@pytest.fixture()
def client(monkeypatch):
    import fakeredis
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from app.db import engine
    from app.main import app
    from app.services import auth, cache, oauth_state

    fake = fakeredis.FakeRedis(decode_responses=True)
    for module in (auth, cache, oauth_state):
        monkeypatch.setattr(module, "_client", fake)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE busy_intervals, calendar_collections, calendar_connections, team_members, teams, app_users CASCADE"
            )
        )
    with TestClient(app) as test_client:
        yield test_client


def _signup(client, email):
    from fastapi.testclient import TestClient

    from app.main import app

    other = TestClient(app)
    response = other.post("/api/auth/register", json={"email": email, "password": "correct-horse-1"})
    assert response.status_code == 200, response.text
    return other, response.json()["id"]


def _add_busy(user_id, name, windows):
    from sqlalchemy.dialects.postgresql import Range

    from app.db import SessionLocal
    from app.models import AuthKind, BusyIntervalRow, CalendarCollection, CalendarConnection, ConnectionStatus, Provider

    session = SessionLocal()
    try:
        connection = CalendarConnection(
            user_id=uuid.UUID(user_id),
            provider=Provider.LINK,
            auth_kind=AuthKind.PUBLIC_LINK,
            status=ConnectionStatus.ACTIVE,
            encrypted_secret=b"x",
            last_synced_at=datetime.now().astimezone(),
        )
        collection = CalendarCollection(external_id=name, display_name=name, selected=True)
        connection.collections.append(collection)
        session.add(connection)
        session.flush()
        for start, end in windows:
            session.add(
                BusyIntervalRow(
                    collection_id=collection.id,
                    uid=f"{name}-{start.isoformat()}",
                    occurrence_start=start,
                    period=Range(start, end, bounds="[)"),
                )
            )
        session.commit()
    finally:
        session.close()


def _tomorrow(hour):
    from app.domain import Constants

    day = (datetime.now(Constants.DISPLAY_TZ) + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    return day.replace(hour=hour)


def test_grid_requires_login(client):
    assert client.get("/api/grid").status_code == 401
    assert client.get("/api/teams").status_code == 401


def test_duplicate_email_and_wrong_password(client):
    _signup(client, "a@example.com")
    again = client.post("/api/auth/register", json={"email": "A@example.com", "password": "another-pass-1"})
    assert again.status_code == 409
    bad = client.post("/api/auth/login", json={"email": "a@example.com", "password": "nope-nope-nope"})
    assert bad.status_code == 401


def test_password_is_not_stored_in_clear(client):
    from sqlalchemy import text

    from app.db import engine

    _signup(client, "a@example.com")
    with engine.connect() as connection:
        stored = connection.execute(text("SELECT password_hash FROM app_users")).scalar_one()
    assert "correct-horse-1" not in stored


def test_team_grid_cache_and_membership(client):
    alice, alice_id = _signup(client, "alice@example.com")
    bob, bob_id = _signup(client, "bob@example.com")
    team = alice.post("/api/teams", json={"name": "Проект"}).json()
    assert bob.get(f"/api/teams/{team['id']}").status_code == 404
    joined = bob.post("/api/teams/join", json={"invite_token": team["invite_token"]})
    assert joined.status_code == 200
    assert len(joined.json()["members"]) == 2

    day = _tomorrow(0)
    _add_busy(alice_id, "alice-cal", [(day.replace(hour=10), day.replace(hour=12))])
    _add_busy(bob_id, "bob-cal", [(day.replace(hour=13), day.replace(hour=14))])

    date = day.date().isoformat()
    params = {"team_id": team["id"], "date_from": date, "date_to": date, "step_minutes": 60, "slot_minutes": 120}
    first = alice.get("/api/grid", params=params)
    assert first.status_code == 200
    assert first.headers["x-cache"] == "MISS"
    payload = first.json()
    assert payload["total"] == 2
    by_hour = {cell["hour"]: cell for cell in payload["cells"]}
    assert by_hour[10]["free_count"] == 1 and by_hour[13]["free_count"] == 1 and by_hour[9]["free_count"] == 2
    starts = [hour for hour, cell in by_hour.items() if cell["slot_start"]]
    assert starts == [14, 15, 16, 17, 18, 19]

    second = alice.get("/api/grid", params=params)
    assert second.headers["x-cache"] == "HIT"
    assert second.json() == payload
    etag = second.headers["etag"]
    assert alice.get("/api/grid", params=params, headers={"If-None-Match": etag}).status_code == 304

    from app.services import cache

    cache.bump_user(uuid.UUID(bob_id))
    assert alice.get("/api/grid", params=params).headers["x-cache"] == "MISS"


def test_member_without_calendars_is_not_counted_as_free(client):
    alice, alice_id = _signup(client, "alice@example.com")
    bob, _ = _signup(client, "bob@example.com")
    team = alice.post("/api/teams", json={"name": "Проект"}).json()
    bob.post("/api/teams/join", json={"invite_token": team["invite_token"]})
    day = _tomorrow(0)
    _add_busy(alice_id, "alice-cal", [(day.replace(hour=10), day.replace(hour=12))])
    date = day.date().isoformat()
    payload = alice.get("/api/grid", params={"team_id": team["id"], "date_from": date, "date_to": date}).json()
    assert payload["total"] == 1
    members = {item["email"]: item for item in payload["members"]}
    assert members["bob@example.com"]["in_overlay"] is False
    assert members["alice@example.com"]["in_overlay"] is True


def test_delete_connection_removes_it_and_is_owner_only(client):
    alice, alice_id = _signup(client, "alice@example.com")
    bob, _ = _signup(client, "bob@example.com")
    day = _tomorrow(0)
    _add_busy(alice_id, "alice-cal", [(day.replace(hour=10), day.replace(hour=12))])
    date = day.date().isoformat()
    params = {"date_from": date, "date_to": date}
    sources = alice.get("/api/grid", params=params).json()["sources"]
    assert len(sources) == 1
    connection_id = sources[0]["connection_id"]

    assert bob.delete(f"/api/connections/{connection_id}").status_code == 404
    assert alice.delete(f"/api/connections/{connection_id}").status_code == 204
    assert alice.delete(f"/api/connections/{connection_id}").status_code == 404

    after = alice.get("/api/grid", params=params).json()
    assert after["sources"] == []
    assert after["total"] == 0

    from sqlalchemy import text

    from app.db import engine

    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM busy_intervals")).scalar_one() == 0
