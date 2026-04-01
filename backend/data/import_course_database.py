#!/usr/bin/env python3
"""
Replace backend/data/shop.db with your real course database file, then regenerate seed.sql.

Usage (from backend/ directory):
  python data/import_course_database.py /path/to/your/original/shop.db

Example:
  python data/import_course_database.py ~/Downloads/shop.db
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
TARGET = DATA_DIR / "shop.db"
EXPORT = DATA_DIR / "export_seed.py"


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python data/import_course_database.py /path/to/shop.db", file=sys.stderr)
        sys.exit(1)
    src = Path(sys.argv[1]).expanduser().resolve()
    if not src.is_file():
        print(f"Not a file: {src}", file=sys.stderr)
        sys.exit(1)
    shutil.copy2(src, TARGET)
    print(f"Copied -> {TARGET}", file=sys.stderr)
    subprocess.run(
        [sys.executable, str(EXPORT)],
        cwd=DATA_DIR.parent,
        check=True,
    )


if __name__ == "__main__":
    main()
