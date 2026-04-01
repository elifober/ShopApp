-- Shop database schema + minimal seed (for empty Railway deploys).
-- Lives next to shop.db in this folder. Replace shop.db with your full class DB for production data.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
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

CREATE TABLE IF NOT EXISTS products (
  product_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  sku          TEXT NOT NULL UNIQUE,
  product_name TEXT NOT NULL,
  category     TEXT NOT NULL,
  price        REAL NOT NULL,
  cost         REAL NOT NULL,
  is_active    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS orders (
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

CREATE TABLE IF NOT EXISTS order_items (
  order_item_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id       INTEGER NOT NULL,
  product_id     INTEGER NOT NULL,
  quantity       INTEGER NOT NULL,
  unit_price     REAL NOT NULL,
  line_total     REAL NOT NULL,
  FOREIGN KEY (order_id) REFERENCES orders(order_id),
  FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE IF NOT EXISTS shipments (
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

CREATE TABLE IF NOT EXISTS product_reviews (
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

CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_datetime ON orders(order_datetime);
CREATE INDEX IF NOT EXISTS idx_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_items_product ON order_items(product_id);
CREATE INDEX IF NOT EXISTS idx_shipments_late ON shipments(late_delivery);
CREATE INDEX IF NOT EXISTS idx_reviews_product ON product_reviews(product_id);
CREATE INDEX IF NOT EXISTS idx_reviews_customer ON product_reviews(customer_id);

-- Minimal demo rows (optional; full dataset: copy a real shop.db into this folder)
INSERT OR IGNORE INTO customers (customer_id, full_name, email, gender, birthdate, created_at, city, state, zip_code, customer_segment, loyalty_tier, is_active)
VALUES (1, 'Demo Customer', 'demo@example.com', 'Non-binary', '1990-01-01', datetime('now'), 'Austin', 'TX', '78701', 'standard', 'silver', 1);

INSERT OR IGNORE INTO products (product_id, sku, product_name, category, price, cost, is_active)
VALUES (1, 'DEMO-SKU-1', 'Demo Product', 'general', 19.99, 10.00, 1);
