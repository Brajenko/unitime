"""Backup, restore and prune PostgreSQL dumps for quest 7.

Run from the repository root. PostgreSQL is reached through Docker Compose;
the script never needs a database password on the host.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone


ROOT = Path(__file__).resolve().parents[1]
DB_NAME = re.compile(r"[a-z][a-z0-9_]*\Z")
DUMP_NAME = re.compile(r"unitime-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}\.dump\Z")


def compose(project: str, *args: str, stdin: object = None, stdout: object = None) -> None:
    command = ["docker", "compose", "-p", project, "exec", "-T", "postgres", *args]
    subprocess.run(command, cwd=ROOT, stdin=stdin, stdout=stdout, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checksum_path(dump: Path) -> Path:
    return dump.with_name(dump.name + ".sha256")


def valid_dump(dump: Path) -> bool:
    checksum = checksum_path(dump)
    if not checksum.is_file():
        return False
    return checksum.read_text(encoding="ascii").strip() == sha256(dump)


def backup(args: argparse.Namespace) -> None:
    if not DB_NAME.fullmatch(args.database):
        raise ValueError("Invalid database name")
    destination = Path(args.directory).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    name = f"unitime-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}.dump"
    dump = destination / name
    temporary = destination / f".{name}.part"
    try:
        with temporary.open("wb") as stream:
            compose(args.project, "pg_dump", "-U", "slot", "-d", args.database, "-Fc", stdout=stream)
            stream.flush()
            os.fsync(stream.fileno())
        with temporary.open("rb") as stream:
            compose(args.project, "pg_restore", "--list", stdin=stream, stdout=subprocess.DEVNULL)
        os.replace(temporary, dump)
        checksum_path(dump).write_text(sha256(dump) + "\n", encoding="ascii")
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    print(f"BACKUP_OK {dump}")
    print(f"SHA256 {sha256(dump)}")


def restore(args: argparse.Namespace) -> None:
    if not DB_NAME.fullmatch(args.target) or not args.target.endswith("_restore_test"):
        raise ValueError("Restore target must be a new database ending in _restore_test")
    dump = Path(args.dump).resolve()
    if not dump.is_file() or not valid_dump(dump):
        raise ValueError("Dump or its SHA256 sidecar is missing or corrupt")
    with dump.open("rb") as stream:
        compose(args.project, "pg_restore", "--list", stdin=stream, stdout=subprocess.DEVNULL)
    compose(args.project, "createdb", "-U", "slot", args.target)
    try:
        with dump.open("rb") as stream:
            compose(
                args.project,
                "pg_restore", "-U", "slot", "-d", args.target,
                "--exit-on-error", "--no-owner", "--no-privileges",
                stdin=stream,
            )
    except BaseException:
        print(f"RESTORE_FAILED: inspect and remove the partial test database {args.target}", file=sys.stderr)
        raise
    print(f"RESTORE_OK {args.target}")


def prune(args: argparse.Namespace) -> None:
    if args.keep_days < 1:
        raise ValueError("keep-days must be at least 1")
    directory = Path(args.directory).resolve()
    if not directory.is_dir():
        raise ValueError("Backup directory does not exist")
    dumps = sorted(
        (path for path in directory.iterdir() if path.is_file() and DUMP_NAME.fullmatch(path.name)),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    usable = [path for path in dumps if valid_dump(path)]
    if not usable:
        raise ValueError("No SHA256-verified backup: nothing will be deleted")
    newest = usable[0]
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.keep_days)
    for dump in dumps:
        if not valid_dump(dump):
            print(f"SKIP_INVALID {dump.name}")
            continue
        old = datetime.fromtimestamp(dump.stat().st_mtime, timezone.utc) < cutoff
        if old and dump != newest:
            print(f"DELETE {dump.name}" if args.apply else f"WOULD_DELETE {dump.name}")
            if args.apply:
                dump.unlink()
                checksum_path(dump).unlink()
        else:
            print(f"KEEP {dump.name}")
    if args.apply and not valid_dump(newest):
        raise RuntimeError("Freshest verified backup was not preserved")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    backup_parser = sub.add_parser("backup")
    backup_parser.add_argument("--project", required=True, help="Docker Compose project name")
    backup_parser.add_argument("--database", default="slot")
    backup_parser.add_argument("--directory", required=True)
    backup_parser.set_defaults(run=backup)

    restore_parser = sub.add_parser("restore")
    restore_parser.add_argument("--project", required=True)
    restore_parser.add_argument("--dump", required=True)
    restore_parser.add_argument("--target", required=True)
    restore_parser.set_defaults(run=restore)

    prune_parser = sub.add_parser("prune")
    prune_parser.add_argument("--directory", required=True)
    prune_parser.add_argument("--keep-days", type=int, default=7)
    prune_parser.add_argument("--apply", action="store_true", help="Delete listed expired dumps")
    prune_parser.set_defaults(run=prune)

    args = parser.parse_args()
    try:
        args.run(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
