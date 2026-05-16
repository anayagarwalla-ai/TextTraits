#!/usr/bin/env python3
"""Apply TextTraits database schema updates for the configured environment."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "texttraits_app"
sys.path.insert(0, str(APP_DIR))

from env_loader import load_env_file  # noqa: E402
from storage import check_database, database_status, init_db  # noqa: E402


def main() -> None:
    load_env_file()
    init_db()
    status = check_database()
    backend = database_status(include_path=True)
    print(f"TextTraits database migrated: backend={backend['backend']} ok={status['ok']}")


if __name__ == "__main__":
    main()
