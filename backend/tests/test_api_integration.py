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
                "TRUNCATE availability_windows, meetings, busy_intervals, calendar_collections, calendar_connections, team_members, teams, app_users CASCADE"
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


def _meeting_body(hour, minutes=60, title=None):
    start = _tomorrow(hour)
    body = {"start": start.isoformat(), "end": (start + timedelta(minutes=minutes)).isoformat()}
    if title:
        body["title"] = title
    return body


def _team_of_two(client):
    alice, alice_id = _signup(client, "alice@example.com")
    bob, bob_id = _signup(client, "bob@example.com")
    team = alice.post("/api/teams", json={"name": "Проект"}).json()
    bob.post("/api/teams/join", json={"invite_token": team["invite_token"]})
    return alice, bob, team["id"]


def test_meeting_create_and_list_visible_to_team(client):
    alice, bob, team_id = _team_of_two(client)
    outsider, _ = _signup(client, "carol@example.com")

    created = alice.post(f"/api/teams/{team_id}/meetings", json=_meeting_body(10, title="Синк"))
    assert created.status_code == 201, created.text
    assert created.json()["title"] == "Синк"
    assert created.json()["created_by_email"] == "alice@example.com"

    seen = bob.get(f"/api/teams/{team_id}/meetings")
    assert seen.status_code == 200
    assert [item["id"] for item in seen.json()] == [created.json()["id"]]
    assert seen.json()[0]["can_cancel"] is False

    assert outsider.get(f"/api/teams/{team_id}/meetings").status_code == 404
    assert outsider.post(f"/api/teams/{team_id}/meetings", json=_meeting_body(15)).status_code == 404


def test_meeting_validation_errors_are_400(client):
    alice, _, team_id = _team_of_two(client)
    past = {"start": "2020-01-01T10:00:00+03:00", "end": "2020-01-01T11:00:00+03:00"}
    assert alice.post(f"/api/teams/{team_id}/meetings", json=past).status_code == 400
    assert alice.post(f"/api/teams/{team_id}/meetings", json=_meeting_body(10, minutes=0)).status_code == 400


def test_meeting_overlap_returns_409_but_adjacent_is_fine(client):
    alice, bob, team_id = _team_of_two(client)
    assert alice.post(f"/api/teams/{team_id}/meetings", json=_meeting_body(10)).status_code == 201
    clash = bob.post(f"/api/teams/{team_id}/meetings", json=_meeting_body(10, minutes=30))
    assert clash.status_code == 409
    assert "занято" in clash.json()["detail"]
    assert bob.post(f"/api/teams/{team_id}/meetings", json=_meeting_body(11)).status_code == 201


def test_meeting_overlap_is_per_team(client):
    alice, _, team_id = _team_of_two(client)
    other = alice.post("/api/teams", json={"name": "Другая"}).json()["id"]
    assert alice.post(f"/api/teams/{team_id}/meetings", json=_meeting_body(10)).status_code == 201
    assert alice.post(f"/api/teams/{other}/meetings", json=_meeting_body(10)).status_code == 201


def test_meeting_concurrent_fix_only_one_wins(client):
    import threading

    from sqlalchemy import text

    from app.db import engine

    alice, bob, team_id = _team_of_two(client)
    barrier = threading.Barrier(2)
    codes = []

    def fix(user):
        barrier.wait()
        codes.append(user.post(f"/api/teams/{team_id}/meetings", json=_meeting_body(10)).status_code)

    threads = [threading.Thread(target=fix, args=(user,)) for user in (alice, bob)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(codes) == [201, 409]
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM meetings")).scalar_one() == 1


def test_meeting_cancel_permissions(client):
    alice, bob, team_id = _team_of_two(client)
    carol, _ = _signup(client, "carol@example.com")
    carol.post("/api/teams/join", json={"invite_token": alice.get("/api/teams").json()[0]["invite_token"]})

    by_bob = bob.post(f"/api/teams/{team_id}/meetings", json=_meeting_body(10)).json()["id"]
    assert carol.delete(f"/api/meetings/{by_bob}").status_code == 403
    assert alice.delete(f"/api/meetings/{by_bob}").status_code == 204
    assert alice.delete(f"/api/meetings/{by_bob}").status_code == 404

    by_alice = alice.post(f"/api/teams/{team_id}/meetings", json=_meeting_body(12)).json()["id"]
    assert bob.delete(f"/api/meetings/{by_alice}").status_code == 403
    own = bob.post(f"/api/teams/{team_id}/meetings", json=_meeting_body(14)).json()["id"]
    assert bob.delete(f"/api/meetings/{own}").status_code == 204
    assert alice.get(f"/api/teams/{team_id}/meetings").json()[0]["can_cancel"] is True


def _add_connection(user_id, status, synced_ago=None):
    from app.db import SessionLocal
    from app.models import AuthKind, CalendarCollection, CalendarConnection, Provider

    session = SessionLocal()
    try:
        connection = CalendarConnection(
            user_id=uuid.UUID(user_id),
            provider=Provider.LINK,
            auth_kind=AuthKind.PUBLIC_LINK,
            status=status,
            encrypted_secret=b"x",
            last_synced_at=datetime.now().astimezone() - synced_ago if synced_ago is not None else None,
        )
        connection.collections.append(CalendarCollection(external_id="c", display_name="c", selected=True))
        session.add(connection)
        session.commit()
    finally:
        session.close()


def test_grid_member_status(client):
    from app.models import ConnectionStatus

    alice, alice_id = _signup(client, "alice@example.com")
    members = {"alice": (alice, alice_id)}
    for name in ("bob", "carol", "dave", "erin"):
        members[name] = _signup(client, f"{name}@example.com")
    team = alice.post("/api/teams", json={"name": "Проект"}).json()
    for name in ("bob", "carol", "dave", "erin"):
        members[name][0].post("/api/teams/join", json={"invite_token": team["invite_token"]})

    _add_connection(alice_id, ConnectionStatus.ACTIVE, timedelta(minutes=3))
    # bob: календарей нет вовсе
    _add_connection(members["carol"][1], ConnectionStatus.AUTH_FAILED, timedelta(hours=5))
    _add_connection(members["dave"][1], ConnectionStatus.ACTIVE, timedelta(hours=1))
    # erin: подключение есть, но ни разу не синхронизировалось
    _add_connection(members["erin"][1], ConnectionStatus.PENDING, None)

    payload = alice.get("/api/grid", params={"team_id": team["id"]}).json()
    statuses = {item["email"].split("@")[0]: item["status"] for item in payload["members"]}
    assert statuses == {
        "alice": "ok",
        "bob": "no_calendars",
        "carol": "auth_failed",
        "dave": "stale",
        "erin": "stale",
    }


def test_grid_generated_at_is_preserved_on_cache_hit(client):
    alice, _ = _signup(client, "alice@example.com")
    first = alice.get("/api/grid")
    second = alice.get("/api/grid")
    assert first.headers["x-cache"] == "MISS" and second.headers["x-cache"] == "HIT"
    assert first.json()["generated_at"] == second.json()["generated_at"]


def test_grid_tz_param(client):
    alice, alice_id = _signup(client, "alice@example.com")
    day = _tomorrow(0)
    _add_busy(alice_id, "cal", [(day.replace(hour=10), day.replace(hour=12))])
    params = {"date_from": day.date().isoformat(), "date_to": day.date().isoformat()}

    moscow = alice.get("/api/grid", params=params)
    ekb = alice.get("/api/grid", params={**params, "tz": "Asia/Yekaterinburg"})
    assert moscow.status_code == 200 and ekb.status_code == 200
    assert moscow.json()["tz"] == "Europe/Moscow" and ekb.json()["tz"] == "Asia/Yekaterinburg"

    def busy_hours(response):
        return [cell["hour"] for cell in response.json()["cells"] if cell["free_count"] == 0]

    assert busy_hours(moscow) == [10, 11]
    assert busy_hours(ekb) == [12, 13]
    assert ekb.json()["cells"][0]["start"].endswith("+05:00")

    assert alice.get("/api/grid", params={**params, "tz": "Mars/Base"}).status_code == 400
    assert alice.get("/api/grid", params={**params, "tz": "../etc"}).status_code == 400


def _day_params(day):
    date = day.date().isoformat()
    return {"date_from": date, "date_to": date}


def _windows(*pairs):
    return {"windows": [{"start": start.isoformat(), "end": end.isoformat()} for start, end in pairs]}


def test_availability_put_get_roundtrip(client):
    alice, _ = _signup(client, "alice@example.com")
    day = _tomorrow(0)
    params = _day_params(day)
    body = _windows(
        (day.replace(hour=10), day.replace(hour=11)),
        (day.replace(hour=11), day.replace(hour=12)),
        (day.replace(hour=15), day.replace(hour=16)),
    )
    saved = alice.put("/api/me/availability", params=params, json=body)
    assert saved.status_code == 200, saved.text
    assert len(saved.json()) == 2
    got = alice.get("/api/me/availability", params=params).json()
    assert [(item["start"][11:16], item["end"][11:16]) for item in got] == [("10:00", "12:00"), ("15:00", "16:00")]


def test_availability_replace_only_in_range(client):
    alice, _ = _signup(client, "alice@example.com")
    day = _tomorrow(0)
    later = day + timedelta(days=7)
    alice.put("/api/me/availability", params=_day_params(later), json=_windows((later.replace(hour=9), later.replace(hour=10))))
    alice.put("/api/me/availability", params=_day_params(day), json=_windows((day.replace(hour=9), day.replace(hour=10))))
    alice.put("/api/me/availability", params=_day_params(day), json=_windows())
    assert alice.get("/api/me/availability", params=_day_params(day)).json() == []
    assert len(alice.get("/api/me/availability", params=_day_params(later)).json()) == 1


def test_availability_validation_400(client):
    alice, _ = _signup(client, "alice@example.com")
    day = _tomorrow(0)
    outside = _windows((day.replace(hour=10) + timedelta(days=1), day.replace(hour=11) + timedelta(days=1)))
    assert alice.put("/api/me/availability", params=_day_params(day), json=outside).status_code == 400
    assert alice.get("/api/me/availability", params={**_day_params(day), "tz": "Mars/Base"}).status_code == 400
    wide = {"date_from": day.date().isoformat(), "date_to": (day + timedelta(days=20)).date().isoformat()}
    assert alice.get("/api/me/availability", params=wide).status_code == 400
    assert client.get("/api/me/availability", params=_day_params(day)).status_code == 401


def _team_with(alice, bob):
    team = alice.post("/api/teams", json={"name": "Проект"}).json()
    bob.post("/api/teams/join", json={"invite_token": team["invite_token"]})
    return team["id"]


def test_manual_member_counted_in_team_grid(client):
    alice, alice_id = _signup(client, "alice@example.com")
    bob, _ = _signup(client, "bob@example.com")
    team_id = _team_with(alice, bob)
    day = _tomorrow(0)
    _add_busy(alice_id, "alice-cal", [(day.replace(hour=11), day.replace(hour=12))])
    bob.put("/api/me/availability", params=_day_params(day), json=_windows((day.replace(hour=10), day.replace(hour=13))))

    payload = alice.get("/api/grid", params={**_day_params(day), "team_id": team_id}).json()
    assert payload["total"] == 2
    statuses = {item["email"]: (item["status"], item["in_overlay"]) for item in payload["members"]}
    assert statuses["bob@example.com"] == ("manual", True)
    free = {cell["hour"]: cell["free_count"] for cell in payload["cells"]}
    assert free[10] == 2 and free[12] == 2
    assert free[11] == 1  # alice занята по календарю
    assert free[9] == 1 and free[14] == 1  # bob вне своих окон занят


def test_calendar_wins_over_manual(client):
    alice, _ = _signup(client, "alice@example.com")
    bob, bob_id = _signup(client, "bob@example.com")
    team_id = _team_with(alice, bob)
    day = _tomorrow(0)
    bob.put("/api/me/availability", params=_day_params(day), json=_windows((day.replace(hour=10), day.replace(hour=11))))
    _add_busy(bob_id, "bob-cal", [(day.replace(hour=15), day.replace(hour=16))])

    payload = alice.get("/api/grid", params={**_day_params(day), "team_id": team_id}).json()
    bob_info = next(item for item in payload["members"] if item["email"] == "bob@example.com")
    assert bob_info["status"] == "ok"
    free = {cell["hour"]: cell["free_count"] for cell in payload["cells"]}
    # alice без календаря и без окон в сетку не входит, считается только календарь bob
    assert payload["total"] == 1
    assert free[9] == 1 and free[15] == 0


def test_clearing_availability_returns_no_calendars(client):
    alice, _ = _signup(client, "alice@example.com")
    bob, _ = _signup(client, "bob@example.com")
    team_id = _team_with(alice, bob)
    day = _tomorrow(0)
    params = _day_params(day)
    bob.put("/api/me/availability", params=params, json=_windows((day.replace(hour=10), day.replace(hour=11))))
    bob.put("/api/me/availability", params=params, json=_windows())
    payload = alice.get("/api/grid", params={**params, "team_id": team_id}).json()
    bob_info = next(item for item in payload["members"] if item["email"] == "bob@example.com")
    assert bob_info["status"] == "no_calendars" and bob_info["in_overlay"] is False
    assert payload["total"] == 0


def test_availability_change_invalidates_grid_cache(client):
    alice, _ = _signup(client, "alice@example.com")
    bob, _ = _signup(client, "bob@example.com")
    team_id = _team_with(alice, bob)
    day = _tomorrow(0)
    params = {**_day_params(day), "team_id": team_id}
    alice.get("/api/grid", params=params)
    assert alice.get("/api/grid", params=params).headers["x-cache"] == "HIT"
    bob.put("/api/me/availability", params=_day_params(day), json=_windows((day.replace(hour=10), day.replace(hour=11))))
    after = alice.get("/api/grid", params=params)
    assert after.headers["x-cache"] == "MISS"
    assert after.json()["total"] == 1
