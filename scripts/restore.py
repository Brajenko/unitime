import argparse
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def restore(project: str, dump: Path, target: str) -> None:
    compose = ["docker", "compose", "-p", project, "exec", "-T", "postgres"]
    with dump.open("rb") as archive:
        subprocess.run(
            [*compose, "pg_restore", "--exit-on-error", "--file=-"],
            cwd=ROOT, stdin=archive, stdout=subprocess.DEVNULL, check=True,
        )
        archive.seek(0)
        subprocess.run(
            [*compose, "createdb", "-U", "slot", "--template=template0", target],
            cwd=ROOT, check=True,
        )
        try:
            subprocess.run(
                [
                    *compose, "pg_restore", "-U", "slot", "-d", target,
                    "--single-transaction", "--no-owner", "--no-privileges",
                ],
                cwd=ROOT, stdin=archive, check=True,
            )
        except (OSError, subprocess.CalledProcessError, KeyboardInterrupt):
            print(
                f"Target database {target} was created. An uncommitted restore is rolled back. "
                "Check the database before retrying.",
                file=sys.stderr,
            )
            raise
    print(f"Database restored: {target}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore a PostgreSQL backup into a new database.")
    parser.add_argument("--project", required=True, help="Docker Compose project name")
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("--target", required=True, help="New database name")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", args.target):
        parser.error("Invalid target database name")
    try:
        restore(args.project, args.dump, args.target)
    except KeyboardInterrupt:
        parser.exit(130, "Restore interrupted.\n")
    except (OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Restore error: {error}\n")


if __name__ == "__main__":
    main()
