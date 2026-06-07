#!/usr/bin/env python
"""Wipe the local SQLite database and recreate an empty schema.

Run this before a fresh demo: ``python scripts/reset_db.py``.
Backend auto-seed kicks in on the next boot when ``agent_runs`` is empty.

Removes:
- ``backend/phoenixloop.db``
- ``backend/phoenixloop.db-wal`` (SQLite WAL sidecar)
- ``backend/phoenixloop.db-shm`` (SQLite shared-memory sidecar)

Then recreates the schema by calling ``src.db.init_db``. This means a freshly
reset DB has the seed prompt row but no tickets, agent runs, or evals.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _PROJECT_ROOT / "backend"

if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

logger = logging.getLogger(__name__)


def _candidate_db_paths() -> list[Path]:
    """Return every SQLite file or sidecar we should remove for a clean reset."""
    candidates = [
        _BACKEND / "phoenixloop.db",
        _BACKEND / "phoenixloop.db-wal",
        _BACKEND / "phoenixloop.db-shm",
    ]
    # Also catch the working-directory variant in case someone ran the
    # backend from the repo root.
    candidates += [
        _PROJECT_ROOT / "phoenixloop.db",
        _PROJECT_ROOT / "phoenixloop.db-wal",
        _PROJECT_ROOT / "phoenixloop.db-shm",
    ]
    return candidates


def _delete_path(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        path.unlink()
        return True
    except OSError as exc:
        print(f"  ! failed to delete {path}: {exc}", file=sys.stderr)
        return False


async def _recreate_schema(db_path: Path) -> None:
    from src.db import init_db

    await init_db(str(db_path))


def main() -> int:
    print("PhoenixLoop — resetting local database")
    deleted = 0
    for path in _candidate_db_paths():
        if _delete_path(path):
            print(f"  - deleted {path.relative_to(_PROJECT_ROOT)}")
            deleted += 1
    if deleted == 0:
        print("  (nothing to delete — DB was already absent)")

    target_db = _BACKEND / "phoenixloop.db"
    print(f"Recreating schema at {target_db.relative_to(_PROJECT_ROOT)} ...")
    asyncio.run(_recreate_schema(target_db))
    print("Done. Start the backend; auto-seed will populate demo data on first boot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
