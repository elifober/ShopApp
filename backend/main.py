import random
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = (BASE_DIR / "../../shop.db").resolve()

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


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_scoring_column() -> None:
    with db_connect() as conn:
        cols = conn.execute("PRAGMA table_info(shipments)").fetchall()
        has_predicted = any(col["name"] == "predicted_late_probability" for col in cols)
        if not has_predicted:
            conn.execute(
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


@app.on_event("startup")
def on_startup() -> None:
    ensure_scoring_column()


@app.get("/api/customers")
def get_customers() -> list[dict[str, Any]]:
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT customer_id, full_name, email, city, state, customer_segment, loyalty_tier
            FROM customers
            WHERE is_active = 1
            ORDER BY full_name
            """
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/products")
def get_products() -> list[dict[str, Any]]:
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT product_id, sku, product_name, category, price
            FROM products
            WHERE is_active = 1
            ORDER BY product_name
            """
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/customers/{customer_id}/dashboard")
def get_dashboard(customer_id: int) -> dict[str, Any]:
    with db_connect() as conn:
        summary = conn.execute(
            """
            SELECT
              COUNT(*) AS total_orders,
              COALESCE(SUM(order_total), 0) AS lifetime_spend,
              COALESCE(AVG(order_total), 0) AS avg_order_value,
              COALESCE(AVG(risk_score), 0) AS avg_risk
            FROM orders
            WHERE customer_id = ?
            """,
            (customer_id,),
        ).fetchone()

        late = conn.execute(
            """
            SELECT COUNT(*) AS late_count
            FROM shipments s
            JOIN orders o ON o.order_id = s.order_id
            WHERE o.customer_id = ? AND s.late_delivery = 1
            """,
            (customer_id,),
        ).fetchone()

        recent = conn.execute(
            """
            SELECT o.order_id, o.order_datetime, o.order_total, o.payment_method, s.late_delivery
            FROM orders o
            LEFT JOIN shipments s ON s.order_id = o.order_id
            WHERE o.customer_id = ?
            ORDER BY o.order_datetime DESC
            LIMIT 5
            """,
            (customer_id,),
        ).fetchall()

    result = dict(summary) if summary else {}
    result["late_count"] = late["late_count"] if late else 0
    result["recent_orders"] = [dict(r) for r in recent]
    return result


@app.get("/api/customers/{customer_id}/orders")
def get_order_history(customer_id: int) -> list[dict[str, Any]]:
    with db_connect() as conn:
        rows = conn.execute(
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
            WHERE o.customer_id = ?
            ORDER BY o.order_datetime DESC
            """,
            (customer_id,),
        ).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/orders")
def create_order(payload: CreateOrderIn) -> dict[str, Any]:
    if not payload.items:
        raise HTTPException(status_code=400, detail="customerId and at least one item are required.")

    with db_connect() as conn:
        cur = conn.cursor()
        normalized: list[dict[str, Any]] = []
        subtotal = 0.0

        for item in payload.items:
            if item.quantity <= 0:
                continue
            product = cur.execute(
                "SELECT product_id, price FROM products WHERE product_id = ?",
                (item.product_id,),
            ).fetchone()
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
            VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
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
        order_id = int(cur.lastrowid)

        for row in normalized:
            cur.execute(
                """
                INSERT INTO order_items (order_id, product_id, quantity, unit_price, line_total)
                VALUES (?, ?, ?, ?, ?)
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
            VALUES (?, datetime('now'), 'UPS', ?, ?, ?, ?, ?, ?)
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
    with db_connect() as conn:
        rows = conn.execute(
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
        ).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/scoring/run")
def run_scoring() -> dict[str, Any]:
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT s.shipment_id, s.shipping_method, s.distance_band, s.promised_days, s.actual_days,
                   o.promo_used, o.device_type, o.order_total
            FROM shipments s
            JOIN orders o ON o.order_id = s.order_id
            """
        ).fetchall()
        cur = conn.cursor()
        for row in rows:
            row_dict = dict(row)
            p = compute_late_probability(row_dict, row_dict)
            cur.execute(
                "UPDATE shipments SET predicted_late_probability = ? WHERE shipment_id = ?",
                (p, row["shipment_id"]),
            )
        conn.commit()

        queue = conn.execute(
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
        ).fetchall()
        return {"scored": len(rows), "queue": [dict(r) for r in queue]}
