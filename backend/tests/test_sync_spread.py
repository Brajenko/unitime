import uuid

from hypothesis import given, strategies as st

from app.sync import tasks
from app.sync.tasks import spread_countdowns


def test_spread_empty_and_single():
    assert spread_countdowns(0, 900) == []
    single = spread_countdowns(1, 900)
    assert len(single) == 1 and 0 <= single[0] < 0.8 * 900


@given(st.integers(min_value=1, max_value=2000), st.integers(min_value=60, max_value=3600))
def test_spread_stays_inside_first_80_percent_and_keeps_distance(count, interval):
    delays = spread_countdowns(count, interval)
    assert len(delays) == count
    assert all(0 <= value < 0.8 * interval for value in delays)
    step = 0.8 * interval / count
    gaps = [later - earlier for earlier, later in zip(delays, delays[1:])]
    assert all(gap >= 0.8 * step - 1e-9 for gap in gaps)


def test_spread_is_not_a_single_burst():
    delays = spread_countdowns(100, 900)
    assert max(delays) - min(delays) > 600


def test_task_time_limits():
    assert tasks.sync_connection_task.soft_time_limit == 50
    assert tasks.sync_connection_task.time_limit == 60


def test_sync_all_schedules_with_countdowns(monkeypatch):
    ids = [uuid.uuid4() for _ in range(5)]

    class FakeSession:
        def scalars(self, _query):
            return iter(ids)

        def close(self):
            pass

    calls = []
    monkeypatch.setattr(tasks, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(
        tasks.sync_connection_task, "apply_async", lambda args, countdown: calls.append((args, countdown))
    )
    assert tasks.sync_all_connections_task() == 5
    assert [args[0] for args, _ in calls] == [str(item) for item in ids]
    countdowns = [countdown for _, countdown in calls]
    assert countdowns == sorted(countdowns)
    assert countdowns[-1] - countdowns[0] > 300
