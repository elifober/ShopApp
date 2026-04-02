"""
One-time script to seed a Supabase (PostgreSQL) database from the existing
SQLite seed.sql.  Parses seed.sql, reorders DDL/DML for PostgreSQL foreign
keys, and executes against DATABASE_URL.

Usage:
    DATABASE_URL=postgresql://... python data/seed_supabase.py

Or place DATABASE_URL in backend/.env and run from the backend/ directory.
"""

import os
import re
import sys
from pathlib import Path

import psycopg2

SCRIPT_DIR = Path(__file__).resolve().parent
SEED_SQL = SCRIPT_DIR / "seed.sql"

# FK-safe order (create + insert).  Matches seed.sql table names.
TABLE_ORDER = [
    "customers",
    "products",
    "orders",
    "order_items",
    "product_reviews",
    "shipments",
]

SEQUENCE_TABLES = {
    "customers": "customer_id",
    "products": "product_id",
    "orders": "order_id",
    "order_items": "order_item_id",
    "shipments": "shipment_id",
    "product_reviews": "review_id",
}


def load_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return url
    env_file = SCRIPT_DIR.parent / ".env"
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip("\"'")
    print("ERROR: DATABASE_URL not set. Export it or add it to backend/.env")
    sys.exit(1)


def sqlite_to_pg_ddl(ddl: str) -> str:
    return ddl.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")


def parse_seed_sql(content: str) -> tuple[dict[str, str], dict[str, list[str]], list[str]]:
    """Return (create_by_table, inserts_by_table, index_statements)."""
    lines = content.splitlines()
    creates: dict[str, str] = {}
    inserts: dict[str, list[str]] = {}
    indexes: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("CREATE TABLE "):
            m = re.match(r"CREATE TABLE (\w+)", stripped)
            if not m:
                i += 1
                continue
            name = m.group(1)
            block_lines = [line]
            i += 1
            while i < len(lines):
                block_lines.append(lines[i])
                if lines[i].strip() == ");":
                    i += 1
                    break
                i += 1
            creates[name] = "\n".join(block_lines)
            continue

        if stripped.startswith("INSERT INTO "):
            m = re.match(r'INSERT INTO "(\w+)"', stripped)
            if m:
                inserts.setdefault(m.group(1), []).append(stripped)
            i += 1
            continue

        if stripped.startswith("CREATE INDEX "):
            indexes.append(stripped)
            i += 1
            continue

        i += 1

    return creates, inserts, indexes


def build_script(raw: str) -> list[str]:
    """Ordered SQL statements (one string per execute)."""
    creates, inserts, indexes = parse_seed_sql(raw)
    stmts: list[str] = []

    stmts.append(
        "DROP TABLE IF EXISTS shipments, order_items, product_reviews, "
        "orders, products, customers CASCADE;"
    )

    for table in TABLE_ORDER:
        if table not in creates:
            raise RuntimeError(f"Missing CREATE TABLE for {table}")
        stmts.append(sqlite_to_pg_ddl(creates[table]) + ";")

    for table in TABLE_ORDER:
        for insert_line in inserts.get(table, []):
            stmts.append(insert_line + ";")

    for idx in indexes:
        stmts.append(idx + ";")

    for table, col in SEQUENCE_TABLES.items():
        seq_name = f"{table}_{col}_seq"
        stmts.append(
            f"SELECT setval('{seq_name}', COALESCE((SELECT MAX({col}) FROM {table}), 1));"
        )

    return stmts


def main() -> None:
    database_url = load_database_url()

    if not SEED_SQL.is_file():
        print(f"ERROR: seed.sql not found at {SEED_SQL}")
        sys.exit(1)

    print(f"Reading {SEED_SQL} ...", flush=True)
    raw_sql = SEED_SQL.read_text(encoding="utf-8")

    print("Building ordered PostgreSQL statements ...", flush=True)
    statements = build_script(raw_sql)

    print("Connecting to database ...", flush=True)
    conn = psycopg2.connect(database_url)
    try:
        cur = conn.cursor()
        # Supabase enforces a default statement timeout; bulk DDL/DML can exceed it.
        cur.execute("SET statement_timeout = '30min'")
        print(
            f"Applying seed ({len(statements)} statements, this may take a few minutes) ...",
            flush=True,
        )
        for k, stmt in enumerate(statements):
            cur.execute(stmt)
            if (k + 1) % 2000 == 0:
                print(f"  ... {k + 1} statements applied", flush=True)
        conn.commit()
        print("Seed applied successfully.", flush=True)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
