import os
import random
from typing import Any

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Export it or add it to backend/.env before starting the server."
    )


def db_connect() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def db_query(sql: str, params: tuple = (), *, fetchone: bool = False) -> Any:
    """Run a read-only query and return dict rows (or a single dict)."""
    with db_connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return dict(cur.fetchone()) if fetchone else [dict(r) for r in cur.fetchall()]


def ensure_scoring_column() -> None:
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'shipments'
                  AND column_name = 'predicted_late_probability'
                """
            )
            if cur.fetchone() is None:
                cur.execute(
                    "ALTER TABLE shipments ADD COLUMN predicted_late_probability REAL DEFAULT 0"
                )
        conn.commit()


def compute_late_probability(shipment: dict[str, Any], order: dict[str, Any]) -> float:
    score = 0.05
    if shipment["shipping_method"] == "standard":
        score += 0.25
    if shipment["distance_band"] == "national":
        score += 0.25
    if shipment["distance_band"] == "regional":
        score += 0.12
    if order["promo_used"]:
        score += 0.07
    if order["device_type"] == "mobile":
        score += 0.05
    if order["order_total"] > 300:
        score += 0.11
    if shipment["promised_days"] <= 2 and shipment["distance_band"] != "local":
        score += 0.12

    ratio = shipment["actual_days"] / max(shipment["promised_days"], 1)
    score += max(0, ratio - 1) * 0.3
    return min(0.99, round(score, 4))


app = FastAPI(title="Shop API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class OrderItemIn(BaseModel):
    product_id: int = Field(..., alias="productId")
    quantity: int


class CreateOrderIn(BaseModel):
    customer_id: int = Field(..., alias="customerId")
    payment_method: str = Field(default="card", alias="paymentMethod")
    device_type: str = Field(default="desktop", alias="deviceType")
    ip_country: str = Field(default="US", alias="ipCountry")
    promo_used: bool = Field(default=False, alias="promoUsed")
    promo_code: str | None = Field(default=None, alias="promoCode")
    shipping_zip: str | None = Field(default=None, alias="shippingZip")
    shipping_state: str | None = Field(default=None, alias="shippingState")
    shipping_method: str = Field(default="standard", alias="shippingMethod")
    distance_band: str = Field(default="regional", alias="distanceBand")
    items: list[OrderItemIn]


@app.on_event("startup")
def on_startup() -> None:
    ensure_scoring_column()


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "Shop API",
        "docs": "/docs",
        "customers": "/api/customers",
        "products": "/api/products",
    }


@app.get("/api/customers")
def get_customers() -> list[dict[str, Any]]:
    return db_query(
        """
        SELECT customer_id, full_name, email, city, state, customer_segment, loyalty_tier
        FROM customers
        WHERE is_active = 1
        ORDER BY full_name
        """
    )


@app.get("/api/products")
def get_products() -> list[dict[str, Any]]:
    return db_query(
        """
        SELECT product_id, sku, product_name, category, price
        FROM products
        WHERE is_active = 1
        ORDER BY product_name
        """
    )


@app.get("/api/customers/{customer_id}/dashboard")
def get_dashboard(customer_id: int) -> dict[str, Any]:
    summary = db_query(
        """
        SELECT
          COUNT(*) AS total_orders,
          COALESCE(SUM(order_total), 0) AS lifetime_spend,
          COALESCE(AVG(order_total), 0) AS avg_order_value,
          COALESCE(AVG(risk_score), 0) AS avg_risk
        FROM orders
        WHERE customer_id = %s
        """,
        (customer_id,),
        fetchone=True,
    )

    late = db_query(
        """
        SELECT COUNT(*) AS late_count
        FROM shipments s
        JOIN orders o ON o.order_id = s.order_id
        WHERE o.customer_id = %s AND s.late_delivery = 1
        """,
        (customer_id,),
        fetchone=True,
    )

    recent = db_query(
        """
        SELECT o.order_id, o.order_datetime, o.order_total, o.payment_method, s.late_delivery
        FROM orders o
        LEFT JOIN shipments s ON s.order_id = o.order_id
        WHERE o.customer_id = %s
        ORDER BY o.order_datetime DESC
        LIMIT 5
        """,
        (customer_id,),
    )

    result = summary or {}
    result["late_count"] = late["late_count"] if late else 0
    result["recent_orders"] = recent
    return result


@app.get("/api/customers/{customer_id}/orders")
def get_order_history(customer_id: int) -> list[dict[str, Any]]:
    return db_query(
        """
        SELECT
          o.order_id,
          o.order_datetime,
          o.order_total,
          o.payment_method,
          o.shipping_state,
          o.risk_score,
          s.shipping_method,
          s.distance_band,
          s.promised_days,
          s.actual_days,
          s.late_delivery
        FROM orders o
        LEFT JOIN shipments s ON s.order_id = o.order_id
        WHERE o.customer_id = %s
        ORDER BY o.order_datetime DESC
        """,
        (customer_id,),
    )


@app.post("/api/orders")
def create_order(payload: CreateOrderIn) -> dict[str, Any]:
    if not payload.items:
        raise HTTPException(status_code=400, detail="customerId and at least one item are required.")

    with db_connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            normalized: list[dict[str, Any]] = []
            subtotal = 0.0

            for item in payload.items:
                if item.quantity <= 0:
                    continue
                cur.execute(
                    "SELECT product_id, price FROM products WHERE product_id = %s",
                    (item.product_id,),
                )
                product = cur.fetchone()
                if not product:
                    continue
                unit_price = float(product["price"])
                line_total = round(unit_price * item.quantity, 2)
                subtotal += line_total
                normalized.append(
                    {
                        "product_id": item.product_id,
                        "quantity": item.quantity,
                        "unit_price": unit_price,
                        "line_total": line_total,
                    }
                )

            if not normalized:
                raise HTTPException(status_code=400, detail="No valid items supplied.")

            shipping_fee = (
                18
                if payload.shipping_method == "overnight"
                else 10
                if payload.shipping_method == "expedited"
                else 6
            )
            tax_amount = round(subtotal * 0.08, 2)
            order_total = round(subtotal + shipping_fee + tax_amount, 2)
            risk_score = min(100, round(10 + order_total * 0.07 + (12 if payload.promo_used else 0)))

            cur.execute(
                """
                INSERT INTO orders
                  (customer_id, order_datetime, billing_zip, shipping_zip, shipping_state, payment_method,
                   device_type, ip_country, promo_used, promo_code, order_subtotal, shipping_fee, tax_amount,
                   order_total, risk_score, is_fraud)
                VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
                RETURNING order_id
                """,
                (
                    payload.customer_id,
                    payload.shipping_zip,
                    payload.shipping_zip,
                    payload.shipping_state,
                    payload.payment_method,
                    payload.device_type,
                    payload.ip_country,
                    1 if payload.promo_used else 0,
                    payload.promo_code,
                    round(subtotal, 2),
                    shipping_fee,
                    tax_amount,
                    order_total,
                    risk_score,
                ),
            )
            order_id = cur.fetchone()["order_id"]

            for row in normalized:
                cur.execute(
                    """
                    INSERT INTO order_items (order_id, product_id, quantity, unit_price, line_total)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (order_id, row["product_id"], row["quantity"], row["unit_price"], row["line_total"]),
                )

            promised_days = (
                1
                if payload.shipping_method == "overnight"
                else 2
                if payload.shipping_method == "expedited"
                else 5
            )
            actual_days = max(1, promised_days + random.randint(-1, 1))
            late = 1 if actual_days > promised_days else 0
            pred = compute_late_probability(
                {
                    "shipping_method": payload.shipping_method,
                    "distance_band": payload.distance_band,
                    "promised_days": promised_days,
                    "actual_days": actual_days,
                },
                {
                    "promo_used": 1 if payload.promo_used else 0,
                    "device_type": payload.device_type,
                    "order_total": order_total,
                },
            )

            cur.execute(
                """
                INSERT INTO shipments
                  (order_id, ship_datetime, carrier, shipping_method, distance_band, promised_days, actual_days, late_delivery, predicted_late_probability)
                VALUES (%s, NOW(), 'UPS', %s, %s, %s, %s, %s, %s)
                """,
                (
                    order_id,
                    payload.shipping_method,
                    payload.distance_band,
                    promised_days,
                    actual_days,
                    late,
                    pred,
                ),
            )
        conn.commit()

    return {"orderId": order_id, "orderTotal": order_total}


@app.get("/api/warehouse/priority-queue")
def get_priority_queue() -> list[dict[str, Any]]:
    return db_query(
        """
        SELECT
          o.order_id,
          o.order_datetime,
          c.full_name AS customer_name,
          o.order_total,
          s.shipping_method,
          s.distance_band,
          s.promised_days,
          s.actual_days,
          COALESCE(s.predicted_late_probability, 0) AS predicted_late_probability
        FROM shipments s
        JOIN orders o ON o.order_id = s.order_id
        JOIN customers c ON c.customer_id = o.customer_id
        ORDER BY predicted_late_probability DESC, o.order_datetime DESC
        LIMIT 50
        """
    )


@app.post("/api/scoring/run")
def run_scoring() -> dict[str, Any]:
    with db_connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT s.shipment_id, s.shipping_method, s.distance_band, s.promised_days, s.actual_days,
                       o.promo_used, o.device_type, o.order_total
                FROM shipments s
                JOIN orders o ON o.order_id = s.order_id
                """
            )
            rows = cur.fetchall()
            for row in rows:
                row_dict = dict(row)
                p = compute_late_probability(row_dict, row_dict)
                cur.execute(
                    "UPDATE shipments SET predicted_late_probability = %s WHERE shipment_id = %s",
                    (p, row["shipment_id"]),
                )
        conn.commit()

    queue = db_query(
        """
        SELECT
          o.order_id,
          o.order_datetime,
          c.full_name AS customer_name,
          o.order_total,
          s.shipping_method,
          s.distance_band,
          s.promised_days,
          s.actual_days,
          COALESCE(s.predicted_late_probability, 0) AS predicted_late_probability
        FROM shipments s
        JOIN orders o ON o.order_id = s.order_id
        JOIN customers c ON c.customer_id = o.customer_id
        ORDER BY predicted_late_probability DESC, o.order_datetime DESC
        LIMIT 50
        """
    )
    return {"scored": len(rows), "queue": queue}
