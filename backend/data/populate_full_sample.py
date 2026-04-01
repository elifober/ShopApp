#!/usr/bin/env python3
"""
Build a large synthetic shop database (NOT the course "official" file — use
import_course_database.py if you have the real shop.db).

Removes backend/data/shop.db and creates a new one with hundreds of customers,
products, orders, items, and shipments (no "Demo Customer" row).

From backend/:
  python data/populate_full_sample.py
  python data/export_seed.py
"""

from __future__ import annotations

import random
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
DB_PATH = DATA_DIR / "shop.db"

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Christopher", "Karen", "Charles", "Lisa", "Daniel", "Nancy",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Steven", "Ashley",
    "Andrew", "Kimberly", "Paul", "Emily", "Joshua", "Donna", "Kenneth", "Michelle",
    "Kevin", "Carol", "Brian", "Amanda", "George", "Dorothy", "Edward", "Melissa",
    "Ronald", "Deborah", "Timothy", "Stephanie", "Jason", "Rebecca", "Jeffrey", "Sharon",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas",
    "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White",
    "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young",
    "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
]
CITIES = [
    ("Seattle", "WA", "98101"), ("Portland", "OR", "97201"), ("Denver", "CO", "80202"),
    ("Austin", "TX", "78701"), ("Chicago", "IL", "60601"), ("Miami", "FL", "33101"),
    ("Atlanta", "GA", "30301"), ("Boston", "MA", "02101"), ("Phoenix", "AZ", "85001"),
    ("Dallas", "TX", "75201"), ("Nashville", "TN", "37201"), ("Minneapolis", "MN", "55401"),
]
CATEGORIES = [
    ("electronics", "Gadget"),
    ("apparel", "T-Shirt"),
    ("home", "Lamp"),
    ("sports", "Weights"),
    ("books", "Textbook"),
    ("kitchen", "Blender"),
    ("garden", "Hose"),
    ("toys", "Puzzle"),
]
PAYMENT = ["card", "paypal", "bank", "crypto"]
DEVICE = ["mobile", "desktop", "tablet"]
COUNTRY = ["US", "US", "US", "US", "CA"]
CARRIER = ["UPS", "FedEx", "USPS"]
SHIP_METHOD = ["standard", "expedited", "overnight"]
DISTANCE = ["local", "regional", "national"]

N_CUSTOMERS = 400
N_PRODUCTS = 80
N_ORDERS = 1800


def late_prob(shipping_method: str, distance_band: str, promised_days: int, actual_days: int, promo_used: int, device_type: str, order_total: float) -> float:
    score = 0.05
    if shipping_method == "standard":
        score += 0.25
    if distance_band == "national":
        score += 0.25
    if distance_band == "regional":
        score += 0.12
    if promo_used:
        score += 0.07
    if device_type == "mobile":
        score += 0.05
    if order_total > 300:
        score += 0.11
    if promised_days <= 2 and distance_band != "local":
        score += 0.12
    ratio = actual_days / max(promised_days, 1)
    score += max(0, ratio - 1) * 0.3
    return min(0.99, round(score, 4))


def schema() -> str:
    return """
PRAGMA foreign_keys = ON;
CREATE TABLE customers (
  customer_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  full_name        TEXT NOT NULL,
  email            TEXT NOT NULL UNIQUE,
  gender           TEXT NOT NULL,
  birthdate        TEXT NOT NULL,
  created_at       TEXT NOT NULL,
  city             TEXT,
  state            TEXT,
  zip_code         TEXT,
  customer_segment TEXT,
  loyalty_tier     TEXT,
  is_active        INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE products (
  product_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  sku          TEXT NOT NULL UNIQUE,
  product_name TEXT NOT NULL,
  category     TEXT NOT NULL,
  price        REAL NOT NULL,
  cost         REAL NOT NULL,
  is_active    INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE orders (
  order_id           INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id        INTEGER NOT NULL,
  order_datetime     TEXT NOT NULL,
  billing_zip        TEXT,
  shipping_zip       TEXT,
  shipping_state     TEXT,
  payment_method     TEXT NOT NULL,
  device_type        TEXT NOT NULL,
  ip_country         TEXT NOT NULL,
  promo_used         INTEGER NOT NULL DEFAULT 0,
  promo_code         TEXT,
  order_subtotal     REAL NOT NULL,
  shipping_fee       REAL NOT NULL,
  tax_amount         REAL NOT NULL,
  order_total        REAL NOT NULL,
  risk_score         REAL NOT NULL,
  is_fraud           INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);
CREATE TABLE order_items (
  order_item_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id       INTEGER NOT NULL,
  product_id     INTEGER NOT NULL,
  quantity       INTEGER NOT NULL,
  unit_price     REAL NOT NULL,
  line_total     REAL NOT NULL,
  FOREIGN KEY (order_id) REFERENCES orders(order_id),
  FOREIGN KEY (product_id) REFERENCES products(product_id)
);
CREATE TABLE shipments (
  shipment_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id           INTEGER NOT NULL UNIQUE,
  ship_datetime      TEXT NOT NULL,
  carrier            TEXT NOT NULL,
  shipping_method    TEXT NOT NULL,
  distance_band      TEXT NOT NULL,
  promised_days      INTEGER NOT NULL,
  actual_days        INTEGER NOT NULL,
  late_delivery      INTEGER NOT NULL DEFAULT 0,
  predicted_late_probability REAL DEFAULT 0,
  FOREIGN KEY (order_id) REFERENCES orders(order_id)
);
CREATE TABLE product_reviews (
  review_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id     INTEGER NOT NULL,
  product_id      INTEGER NOT NULL,
  rating          INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
  review_datetime TEXT NOT NULL,
  review_text     TEXT,
  FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
  FOREIGN KEY (product_id) REFERENCES products(product_id),
  UNIQUE(customer_id, product_id)
);
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_datetime ON orders(order_datetime);
CREATE INDEX idx_items_order ON order_items(order_id);
CREATE INDEX idx_items_product ON order_items(product_id);
CREATE INDEX idx_shipments_late ON shipments(late_delivery);
CREATE INDEX idx_reviews_product ON product_reviews(product_id);
CREATE INDEX idx_reviews_customer ON product_reviews(customer_id);
"""


def main() -> None:
    random.seed(42)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(schema())
        cur = conn.cursor()

        segments = ["budget", "standard", "premium"]
        tiers = ["none", "silver", "gold"]
        genders = ["Male", "Female", "Non-binary"]

        for i in range(1, N_CUSTOMERS + 1):
            fn = random.choice(FIRST_NAMES)
            ln = random.choice(LAST_NAMES)
            city, st, z = random.choice(CITIES)
            cur.execute(
                """INSERT INTO customers (full_name, email, gender, birthdate, created_at, city, state, zip_code, customer_segment, loyalty_tier, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    f"{fn} {ln}",
                    f"{fn.lower()}.{ln.lower()}.{i}@mail.example",
                    random.choice(genders),
                    f"{random.randint(1955, 2005)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
                    datetime.now().isoformat(timespec="seconds"),
                    city,
                    st,
                    z,
                    random.choice(segments),
                    random.choice(tiers),
                ),
            )

        for i in range(1, N_PRODUCTS + 1):
            cat, base = random.choice(CATEGORIES)
            price = round(random.uniform(9.99, 499.99), 2)
            cost = round(price * random.uniform(0.35, 0.65), 2)
            cur.execute(
                """INSERT INTO products (sku, product_name, category, price, cost, is_active)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (f"SKU-{i:05d}", f"{base} {cat.title()} {i}", cat, price, cost),
            )

        start = datetime.now() - timedelta(days=730)
        for _ in range(N_ORDERS):
            cid = random.randint(1, N_CUSTOMERS)
            order_dt = start + timedelta(seconds=random.randint(0, 730 * 86400))
            pay = random.choice(PAYMENT)
            dev = random.choice(DEVICE)
            ip = random.choice(COUNTRY)
            promo_used = random.random() < 0.15
            city, st, z = random.choice(CITIES)
            ship_m = random.choice(SHIP_METHOD)
            dist = random.choice(DISTANCE)
            n_lines = random.randint(1, 4)
            pids = random.sample(range(1, N_PRODUCTS + 1), n_lines)

            subtotal = 0.0
            lines = []
            for pid in pids:
                cur.execute("SELECT price FROM products WHERE product_id = ?", (pid,))
                unit = float(cur.fetchone()[0])
                qty = random.randint(1, 3)
                lt = round(unit * qty, 2)
                subtotal += lt
                lines.append((pid, qty, unit, lt))

            ship_fee = 18 if ship_m == "overnight" else 10 if ship_m == "expedited" else 6
            tax = round(subtotal * 0.08, 2)
            total = round(subtotal + ship_fee + tax, 2)
            risk = min(100, round(10 + total * 0.07 + (12 if promo_used else 0)))

            cur.execute(
                """INSERT INTO orders (customer_id, order_datetime, billing_zip, shipping_zip, shipping_state, payment_method, device_type, ip_country, promo_used, promo_code, order_subtotal, shipping_fee, tax_amount, order_total, risk_score, is_fraud)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (
                    cid,
                    order_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    z,
                    z,
                    st,
                    pay,
                    dev,
                    ip,
                    1 if promo_used else 0,
                    "SAVE10" if promo_used else None,
                    round(subtotal, 2),
                    ship_fee,
                    tax,
                    total,
                    risk,
                ),
            )
            oid = cur.lastrowid

            for pid, qty, unit, lt in lines:
                cur.execute(
                    """INSERT INTO order_items (order_id, product_id, quantity, unit_price, line_total)
                       VALUES (?, ?, ?, ?, ?)""",
                    (oid, pid, qty, unit, lt),
                )

            promised = 1 if ship_m == "overnight" else 2 if ship_m == "expedited" else 5
            actual = max(1, promised + random.randint(-1, 3))
            late = 1 if actual > promised else 0
            car = random.choice(CARRIER)
            ship_dt = order_dt + timedelta(hours=random.randint(2, 48))
            pred = late_prob(ship_m, dist, promised, actual, 1 if promo_used else 0, dev, total)

            cur.execute(
                """INSERT INTO shipments (order_id, ship_datetime, carrier, shipping_method, distance_band, promised_days, actual_days, late_delivery, predicted_late_probability)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    oid,
                    ship_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    car,
                    ship_m,
                    dist,
                    promised,
                    actual,
                    late,
                    pred,
                ),
            )

        for _ in range(min(300, N_CUSTOMERS * N_PRODUCTS // 20)):
            c = random.randint(1, N_CUSTOMERS)
            p = random.randint(1, N_PRODUCTS)
            try:
                cur.execute(
                    """INSERT INTO product_reviews (customer_id, product_id, rating, review_datetime, review_text)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        c,
                        p,
                        random.randint(1, 5),
                        (start + timedelta(days=random.randint(0, 700))).strftime("%Y-%m-%d %H:%M:%S"),
                        None,
                    ),
                )
            except sqlite3.IntegrityError:
                pass

        conn.commit()
    finally:
        conn.close()

    print(f"Wrote {DB_PATH} with {N_CUSTOMERS} customers, {N_PRODUCTS} products, {N_ORDERS} orders.", file=sys.stderr)


if __name__ == "__main__":
    main()
