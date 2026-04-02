"""
Compare row counts in the database to the expected totals from seed.sql
(sqlite_sequence values).  Uses DATABASE_URL from the environment or backend/.env.

Usage:
    python data/verify_supabase_seed.py
"""

import os
import sys
from pathlib import Path

import psycopg2

SCRIPT_DIR = Path(__file__).resolve().parent

# Expected row counts from seed.sql (sqlite_sequence max ids = row counts for this dump)
EXPECTED = {
    "customers": 400,
    "products": 80,
    "orders": 1800,
    "order_items": 4556,
    "shipments": 1800,
    "product_reviews": 298,
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
    print("ERROR: Set DATABASE_URL or add it to backend/.env", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    database_url = load_database_url()
    conn = psycopg2.connect(database_url)
    try:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '60s'")
        print("Checking row counts against seed.sql expectations...\n")
        all_ok = True
        for table, expected in EXPECTED.items():
            cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            count = cur.fetchone()[0]
            ok = count == expected
            status = "OK" if ok else "MISMATCH"
            if not ok:
                all_ok = False
            print(f"  {table:20}  rows={count:5}  expected={expected:5}  [{status}]")

        # Quick FK sanity: every order should have a customer, etc.
        print("\nSanity checks:")
        cur.execute(
            """
            SELECT COUNT(*) FROM orders o
            LEFT JOIN customers c ON c.customer_id = o.customer_id
            WHERE c.customer_id IS NULL
            """
        )
        orphan_orders = cur.fetchone()[0]
        print(f"  orders without matching customer: {orphan_orders}  [{'OK' if orphan_orders == 0 else 'FAIL'}]")
        if orphan_orders:
            all_ok = False

        cur.execute(
            """
            SELECT COUNT(*) FROM order_items oi
            LEFT JOIN orders o ON o.order_id = oi.order_id
            WHERE o.order_id IS NULL
            """
        )
        orphan_items = cur.fetchone()[0]
        print(f"  order_items without matching order: {orphan_items}  [{'OK' if orphan_items == 0 else 'FAIL'}]")
        if orphan_items:
            all_ok = False

        cur.execute(
            """
            SELECT COUNT(*) FROM shipments s
            LEFT JOIN orders o ON o.order_id = s.order_id
            WHERE o.order_id IS NULL
            """
        )
        orphan_ship = cur.fetchone()[0]
        print(f"  shipments without matching order: {orphan_ship}  [{'OK' if orphan_ship == 0 else 'FAIL'}]")
        if orphan_ship:
            all_ok = False

        print()
        if all_ok:
            print("Result: All checks passed — seed matches expectations.")
        else:
            print("Result: Some checks failed — re-run seed or investigate partial load.")
            sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
