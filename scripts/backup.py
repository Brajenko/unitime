import argparse
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import errno
import os
from pathlib import Path
import re
import stat
import subprocess
import uuid

if os.name == "nt":
    import msvcrt
else:
    import fcntl


ROOT = Path(__file__).resolve().parents[1]
PROJECT_NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")
DATABASE_NAME = re.compile(r"[a-z_][a-z0-9_]{0,62}")
DUMP_NAME = re.compile(r"unitime-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}\.dump")
RETENTION = timedelta(days=7)


class BackupInProgress(Exception):
    pass


class CleanupError(Exception):
    pass


@contextmanager
def backup_lock(directory: Path) -> Iterator[None]:
    with (directory / ".unitime-backup.lock").open("a+b") as handle:
        handle.seek(0)
        fd = handle.fileno()
        try:
            if os.name == "nt":
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
                raise BackupInProgress(f"Backup already in progress for {directory}") from error
            raise
        try:
            yield
        finally:
            if os.name == "nt":
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


def write_dump(compose: list[str], database: str, dump: Path) -> None:
    partial = dump.with_suffix(".dump.part")
    stream = partial.open("xb")
    try:
        with stream:
            subprocess.run(
                [*compose, "pg_dump", "-U", "slot", "-d", database, "-Fc", "--lock-wait-timeout=15s"],
                cwd=ROOT, stdout=stream, check=True,
            )
            stream.flush()
            os.fsync(stream.fileno())
        with partial.open("rb") as archive:
            subprocess.run(
                [*compose, "pg_restore", "--exit-on-error", "--file=-"],
                cwd=ROOT, stdin=archive, stdout=subprocess.DEVNULL, check=True,
            )
        partial.rename(dump)
    finally:
        partial.unlink(missing_ok=True)

def prune(directory: Path, dump: Path, cutoff: float) -> None:
    previous = []
    for path in directory.iterdir():
        if path == dump or not DUMP_NAME.fullmatch(path.name):
            continue
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISREG(info.st_mode):
            previous.append((info.st_mtime, path))
    for modified, path in sorted(previous, reverse=True)[1:]:
        if modified < cutoff:
            path.unlink(missing_ok=True)
            print(f"Expired backup removed: {path.name}")


def backup(project: str, database: str, directory: Path) -> None:
    directory = directory / project / database
    directory.mkdir(parents=True, exist_ok=True)
    compose = ["docker", "compose", "-p", project, "exec", "-T", "postgres"]
    with backup_lock(directory):
        now = datetime.now(timezone.utc)
        dump = directory / f"unitime-{now:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}.dump"
        write_dump(compose, database, dump)
        print(f"Backup saved: {dump}")
        try:
            prune(directory, dump, (now - RETENTION).timestamp())
        except OSError as error:
            raise CleanupError(f"Backup saved at {dump}; cleanup failed: {error}") from error


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up a PostgreSQL database and remove expired copies.")
    parser.add_argument("--project", required=True, help="Docker Compose project name")
    parser.add_argument("--database", default="slot")
    parser.add_argument("--directory", type=Path, default=ROOT / "backups")
    args = parser.parse_args()
    if not PROJECT_NAME.fullmatch(args.project):
        parser.error("Invalid Compose project name")
    if not DATABASE_NAME.fullmatch(args.database):
        parser.error("Invalid database name")
    try:
        backup(args.project, args.database, args.directory.resolve())
    except BackupInProgress as error:
        parser.exit(75, f"{error}\n")
    except CleanupError as error:
        parser.exit(3, f"{error}\n")
    except (OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Backup error: {error}\n")


if __name__ == "__main__":
    main()
