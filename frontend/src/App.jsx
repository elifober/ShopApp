import { useEffect, useMemo, useState } from "react";
import { api } from "./api.js";

const customerTabs = ["dashboard", "order-history", "new-order"];

function App() {
  const [page, setPage] = useState("home");
  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState("");
  const [tab, setTab] = useState("dashboard");
  const [dashboard, setDashboard] = useState(null);
  const [history, setHistory] = useState([]);
  const [queue, setQueue] = useState([]);
  const [runStatus, setRunStatus] = useState("");
  const [saveStatus, setSaveStatus] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const [orderForm, setOrderForm] = useState({
    paymentMethod: "card",
    deviceType: "desktop",
    ipCountry: "US",
    promoUsed: false,
    promoCode: "",
    shippingZip: "",
    shippingState: "",
    shippingMethod: "standard",
    distanceBand: "regional",
    items: [{ productId: "", quantity: 1 }],
  });

  const selectedCustomer = useMemo(
    () => customers.find((c) => String(c.customer_id) === String(selectedCustomerId)),
    [customers, selectedCustomerId]
  );

  useEffect(() => {
    async function loadInitial() {
      const [c, p, q] = await Promise.all([
        api("/customers"),
        api("/products"),
        api("/warehouse/priority-queue"),
      ]);
      setCustomers(c);
      setProducts(p);
      setQueue(q);
    }

    loadInitial().catch((err) => setRunStatus(err.message));
  }, []);

  useEffect(() => {
    if (!selectedCustomerId) return;
    refreshCustomerData(selectedCustomerId);
  }, [selectedCustomerId]);

  async function refreshCustomerData(customerId) {
    const [dash, orders] = await Promise.all([
      api(`/customers/${customerId}/dashboard`),
      api(`/customers/${customerId}/orders`),
    ]);
    setDashboard(dash);
    setHistory(orders);
  }

  function updateOrderItem(index, key, value) {
    setOrderForm((current) => {
      const items = current.items.map((item, i) =>
        i === index ? { ...item, [key]: value } : item
      );
      return { ...current, items };
    });
  }

  function addItemRow() {
    setOrderForm((current) => ({
      ...current,
      items: [...current.items, { productId: "", quantity: 1 }],
    }));
  }

  function removeItemRow(index) {
    setOrderForm((current) => ({
      ...current,
      items: current.items.filter((_, i) => i !== index),
    }));
  }

  async function submitOrder(e) {
    e.preventDefault();
    setSaveStatus("");
    setIsLoading(true);
    try {
      const payload = {
        customerId: Number(selectedCustomerId),
        ...orderForm,
        promoUsed: Boolean(orderForm.promoUsed),
        items: orderForm.items.map((item) => ({
          productId: Number(item.productId),
          quantity: Number(item.quantity),
        })),
      };
      const created = await api("/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setSaveStatus(`Order #${created.orderId} saved. Total $${created.orderTotal.toFixed(2)}.`);
      await refreshCustomerData(selectedCustomerId);
    } catch (err) {
      setSaveStatus(err.message);
    } finally {
      setIsLoading(false);
    }
  }

  async function runScoring() {
    setRunStatus("Running scoring...");
    try {
      const result = await api("/scoring/run", { method: "POST" });
      setQueue(result.queue);
      setRunStatus(`Scored ${result.scored} shipments and refreshed top 50.`);
    } catch (err) {
      setRunStatus(err.message);
    }
  }

  return (
    <div className="app">
      <header>
        <h1>Shop Ops Console</h1>
        <p>Customer analytics, order entry, and warehouse prioritization.</p>
      </header>

      {page !== "home" && (
        <section className="page-header">
          <h2>{page === "customer" ? "Customer Workspace" : "Warehouse Workspace"}</h2>
          <button className="secondary" onClick={() => setPage("home")}>
            Back to Menu
          </button>
        </section>
      )}

      {page === "home" && (
        <section className="card home-menu">
          <p className="menu-kicker">Operations Workspace</p>
          <h2>Choose where you want to work</h2>
          <p className="hint">Select a section to manage customers or warehouse priorities.</p>
          <div className="menu-grid">
            <button className="menu-tile" onClick={() => setPage("customer")}>
              <span className="menu-title">Select Customer</span>
              <span className="menu-subtitle">Dashboard, order history, and new order flow.</span>
            </button>
            <button className="menu-tile" onClick={() => setPage("warehouse")}>
              <span className="menu-title">Warehouse</span>
              <span className="menu-subtitle">Late delivery queue and scoring workflow.</span>
            </button>
          </div>
        </section>
      )}

      {page === "customer" && (
        <>
          <section className="card">
            <h2>Select Customer</h2>
            <select
              value={selectedCustomerId}
              onChange={(e) => setSelectedCustomerId(e.target.value)}
            >
              <option value="">Choose a customer...</option>
              {customers.map((c) => (
                <option key={c.customer_id} value={c.customer_id}>
                  {c.full_name} ({c.email})
                </option>
              ))}
            </select>
            {selectedCustomer && (
              <p className="hint">
                {selectedCustomer.city}, {selectedCustomer.state} | Tier: {selectedCustomer.loyalty_tier}
              </p>
            )}
          </section>

          <nav className="tabs">
            {customerTabs.map((t) => (
              <button
                key={t}
                className={tab === t ? "active" : ""}
                onClick={() => setTab(t)}
              >
                {t}
              </button>
            ))}
          </nav>

          {tab === "dashboard" && dashboard && (
            <section className="card">
              <h2>Customer Dashboard</h2>
              <div className="grid4">
                <div>Total Orders: {dashboard.total_orders}</div>
                <div>Lifetime Spend: ${Number(dashboard.lifetime_spend).toFixed(2)}</div>
                <div>Avg Order Value: ${Number(dashboard.avg_order_value).toFixed(2)}</div>
                <div>Late Deliveries: {dashboard.late_count}</div>
              </div>

              <h3>Recent Orders</h3>
              <table>
                <thead>
                  <tr>
                    <th>Order</th>
                    <th>Date</th>
                    <th>Total</th>
                    <th>Payment</th>
                    <th>Late?</th>
                  </tr>
                </thead>
                <tbody>
                  {dashboard.recent_orders.map((row) => (
                    <tr key={row.order_id}>
                      <td>{row.order_id}</td>
                      <td>{new Date(row.order_datetime).toLocaleString()}</td>
                      <td>${Number(row.order_total).toFixed(2)}</td>
                      <td>{row.payment_method}</td>
                      <td>{row.late_delivery ? "Yes" : "No"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {tab === "new-order" && (
            <section className="card">
              <h2>Place New Order</h2>
              <form onSubmit={submitOrder}>
                <div className="grid2">
                  <label>
                    Payment Method
                    <select
                      value={orderForm.paymentMethod}
                      onChange={(e) =>
                        setOrderForm((f) => ({ ...f, paymentMethod: e.target.value }))
                      }
                    >
                      <option value="card">card</option>
                      <option value="paypal">paypal</option>
                      <option value="bank">bank</option>
                      <option value="crypto">crypto</option>
                    </select>
                  </label>
                  <label>
                    Device
                    <select
                      value={orderForm.deviceType}
                      onChange={(e) =>
                        setOrderForm((f) => ({ ...f, deviceType: e.target.value }))
                      }
                    >
                      <option value="desktop">desktop</option>
                      <option value="mobile">mobile</option>
                      <option value="tablet">tablet</option>
                    </select>
                  </label>
                  <label>
                    Shipping Method
                    <select
                      value={orderForm.shippingMethod}
                      onChange={(e) =>
                        setOrderForm((f) => ({ ...f, shippingMethod: e.target.value }))
                      }
                    >
                      <option value="standard">standard</option>
                      <option value="expedited">expedited</option>
                      <option value="overnight">overnight</option>
                    </select>
                  </label>
                  <label>
                    Distance Band
                    <select
                      value={orderForm.distanceBand}
                      onChange={(e) =>
                        setOrderForm((f) => ({ ...f, distanceBand: e.target.value }))
                      }
                    >
                      <option value="local">local</option>
                      <option value="regional">regional</option>
                      <option value="national">national</option>
                    </select>
                  </label>
                  <label>
                    Shipping State
                    <input
                      value={orderForm.shippingState}
                      onChange={(e) =>
                        setOrderForm((f) => ({ ...f, shippingState: e.target.value }))
                      }
                    />
                  </label>
                  <label>
                    Shipping ZIP
                    <input
                      value={orderForm.shippingZip}
                      onChange={(e) =>
                        setOrderForm((f) => ({ ...f, shippingZip: e.target.value }))
                      }
                    />
                  </label>
                  <label>
                    IP Country
                    <input
                      value={orderForm.ipCountry}
                      onChange={(e) =>
                        setOrderForm((f) => ({ ...f, ipCountry: e.target.value.toUpperCase() }))
                      }
                    />
                  </label>
                  <label>
                    Promo Code
                    <input
                      value={orderForm.promoCode}
                      onChange={(e) =>
                        setOrderForm((f) => ({ ...f, promoCode: e.target.value }))
                      }
                    />
                  </label>
                </div>

                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={orderForm.promoUsed}
                    onChange={(e) => setOrderForm((f) => ({ ...f, promoUsed: e.target.checked }))}
                  />
                  Promo Applied
                </label>

                <h3>Items</h3>
                {orderForm.items.map((item, index) => (
                  <div className="row" key={index}>
                    <select
                      value={item.productId}
                      onChange={(e) => updateOrderItem(index, "productId", e.target.value)}
                    >
                      <option value="">Select product</option>
                      {products.map((p) => (
                        <option key={p.product_id} value={p.product_id}>
                          {p.product_name} (${Number(p.price).toFixed(2)})
                        </option>
                      ))}
                    </select>
                    <input
                      type="number"
                      min="1"
                      value={item.quantity}
                      onChange={(e) => updateOrderItem(index, "quantity", e.target.value)}
                    />
                    <button type="button" onClick={() => removeItemRow(index)}>
                      Remove
                    </button>
                  </div>
                ))}
                <button type="button" onClick={addItemRow}>
                  Add Item
                </button>

                <div className="actions">
                  <button disabled={isLoading} type="submit">
                    {isLoading ? "Saving..." : "Save Order"}
                  </button>
                </div>
                {saveStatus && <p className="hint">{saveStatus}</p>}
              </form>
            </section>
          )}

          {tab === "order-history" && (
            <section className="card">
              <h2>Order History</h2>
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Date</th>
                    <th>Total</th>
                    <th>Ship Method</th>
                    <th>Promised</th>
                    <th>Actual</th>
                    <th>Late?</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((row) => (
                    <tr key={row.order_id}>
                      <td>{row.order_id}</td>
                      <td>{new Date(row.order_datetime).toLocaleString()}</td>
                      <td>${Number(row.order_total).toFixed(2)}</td>
                      <td>{row.shipping_method}</td>
                      <td>{row.promised_days}</td>
                      <td>{row.actual_days}</td>
                      <td>{row.late_delivery ? "Yes" : "No"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
        </>
      )}

      {page === "warehouse" && (
        <>
          <section className="card">
            <h2>Late Delivery Priority Queue (Top 50)</h2>
            <button onClick={runScoring}>Run Scoring</button>
            {runStatus && <p className="hint">{runStatus}</p>}
            <table>
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Customer</th>
                  <th>Total</th>
                  <th>Method</th>
                  <th>Distance</th>
                  <th>Promised</th>
                  <th>Actual</th>
                  <th>Predicted Late Probability</th>
                </tr>
              </thead>
              <tbody>
                {queue.map((row) => (
                  <tr key={row.order_id}>
                    <td>{row.order_id}</td>
                    <td>{row.customer_name}</td>
                    <td>${Number(row.order_total).toFixed(2)}</td>
                    <td>{row.shipping_method}</td>
                    <td>{row.distance_band}</td>
                    <td>{row.promised_days}</td>
                    <td>{row.actual_days}</td>
                    <td>{(Number(row.predicted_late_probability) * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}

export default App;
