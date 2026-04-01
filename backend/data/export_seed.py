#!/usr/bin/env python3
"""
Regenerate seed.sql from shop.db in this folder (full SQLite dump: schema + all data).

Use this whenever you replace shop.db with your real dataset:
  1. Copy your full shop.db to backend/data/shop.db (overwrite).
  2. From the backend directory run:
       python data/export_seed.py
  3. Commit the updated seed.sql (and shop.db if you track it).

Does not require the sqlite3 CLI — uses Python's connection.iterdump().
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
DB_PATH = DATA_DIR / "shop.db"
OUT_PATH = DATA_DIR / "seed.sql"

HEADER = """-- seed.sql — generated from shop.db (schema + all rows).
-- Regenerate: copy your shop.db to data/shop.db, then from backend/: python data/export_seed.py

"""


def main() -> None:
    if not DB_PATH.is_file():
        print(f"Missing database: {DB_PATH}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    try:
        lines = "\n".join(conn.iterdump())
    finally:
        conn.close()
    OUT_PATH.write_text(HEADER + lines + "\n", encoding="utf-8")
    print(f"Wrote {OUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
