#!/usr/bin/env python3
"""
Apply seed.sql to shop.db in this same directory.

Run from the backend folder:
  python data/seed.py

seed.sql is a full SQLite dump (schema + data) generated from shop.db.
To refresh seed.sql after replacing shop.db with your real database:
  python data/export_seed.py
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
DEFAULT_DB = DATA_DIR / "shop.db"
SEED_SQL = DATA_DIR / "seed.sql"


def run_seed(db_path: Path | None = None) -> Path:
    target = db_path or DEFAULT_DB
    override = os.environ.get("SHOP_DB_PATH", "").strip()
    if override:
        target = Path(override).expanduser().resolve()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SEED_SQL.is_file():
        raise FileNotFoundError(f"Missing {SEED_SQL}")
    sql = SEED_SQL.read_text(encoding="utf-8")
    conn = sqlite3.connect(target)
    try:
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()
    return target


def main() -> None:
    out = run_seed()
    print(f"Seeded database: {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
