"""Test-only calendar source and transaction pauses for the Quest 8 stand."""

import os
from datetime import date
from pathlib import Path
from sys import argv
from time import monotonic, sleep
from urllib.parse import urlsplit

from app.adapters import link
from app.main import app
from app.sync import tasks

original_download = link.download


def download(url: str) -> str:
    parts = urlsplit(url)
    if parts.netloc != "quest8.example":
        return original_download(url)
    day = date.fromisoformat(parts.path.removeprefix("/").removesuffix(".ics"))
    stamp = day.strftime("%Y%m%d")
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Unitime//Quest 8//EN\r\n"
        f"BEGIN:VEVENT\r\nUID:quest8-morning\r\nDTSTAMP:{stamp}T060000Z\r\n"
        f"DTSTART:{stamp}T070000Z\r\nDTEND:{stamp}T080000Z\r\nEND:VEVENT\r\n"
        f"BEGIN:VEVENT\r\nUID:quest8-afternoon\r\nDTSTAMP:{stamp}T060000Z\r\n"
        f"DTSTART:{stamp}T110000Z\r\nDTEND:{stamp}T120000Z\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    )


link.download = download


def wait_at(stage: str, job_id: str) -> None:
    release = Path("/tmp/quest8-release")
    if release.exists():
        return
    print(f"demo_pause stage={stage} job_id={job_id}", flush=True)
    deadline = monotonic() + 120
    while not release.exists():
        if monotonic() >= deadline:
            raise TimeoutError(f"Demo was not released at {stage}")
        sleep(0.1)


def install_worker_pause() -> None:
    stage = os.environ.get("QUEST8_PAUSE")
    original_collect = tasks._collect_calendar
    original_replace = tasks.replace_busy_window
    original_save = tasks._save_result
    current_job = None

    def collect(attempt):
        nonlocal current_job
        current_job = str(attempt.job_id)
        return original_collect(attempt)

    def replace(*args):
        count = original_replace(*args)
        wait_at("before_commit", current_job)
        return count

    def save(attempt, snapshot):
        applied = original_save(attempt, snapshot)
        if applied:
            wait_at("after_commit", str(attempt.job_id))
        return applied

    if stage == "before_commit":
        tasks._collect_calendar = collect
        tasks.replace_busy_window = replace
    elif stage == "after_commit":
        tasks._save_result = save


if __name__ == "__main__":
    install_worker_pause()
    tasks.celery_app.worker_main(argv[1:])
