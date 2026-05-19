from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    source = Path(os.getenv("TEXTTRAITS_DB_PATH", "texttraits_app/artifacts/texttraits_workspace.sqlite3")).expanduser()
    target_dir = Path(os.getenv("TEXTTRAITS_BACKUP_DIR", "texttraits_app/artifacts/backups")).expanduser()
    if not source.exists():
        print(f"No SQLite database found at {source}.", file=sys.stderr)
        return 1
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = target_dir / f"{source.stem}-{timestamp}.sqlite3"
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    shutil.copy2(target, target.with_suffix(".sqlite3.bak"))
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
