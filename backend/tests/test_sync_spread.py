import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

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


def test_sync_all_schedules_jobs_in_database(monkeypatch):
    ids = [uuid.uuid4() for _ in range(5)]
    jobs = []

    class FakeSession:
        @contextmanager
        def begin(self):
            yield self

        def scalars(self, _query):
            return iter(ids)

        def add_all(self, queued_jobs):
            jobs.extend(queued_jobs)

    def spread(count, interval):
        assert count == len(ids)
        assert interval == tasks.settings.sync_interval_seconds
        return [0, 100, 200, 300, 400]

    monkeypatch.setattr(tasks, "SessionLocal", FakeSession())
    monkeypatch.setattr(tasks, "spread_countdowns", spread)
    before = datetime.now(timezone.utc)
    assert tasks.sync_all_connections_task() == 5
    assert [job.connection_id for job in jobs] == ids
    assert before <= jobs[0].available_at <= datetime.now(timezone.utc)
    assert [job.available_at - jobs[0].available_at for job in jobs] == [
        timedelta(seconds=index * 100) for index in range(5)
    ]
