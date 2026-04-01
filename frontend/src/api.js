/**
 * API base: leave unset to use Vite dev proxy (/api → localhost:8000).
 * If you see proxy errors, create frontend/.env.local with:
 *   VITE_API_BASE=http://127.0.0.1:8000
 */
const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

export function apiUrl(path) {
  const p = path.startsWith("/") ? path : `/${path}`;
  const rel = p.startsWith("/api") ? p : `/api${p}`;
  if (API_BASE) {
    return `${API_BASE}${rel}`;
  }
  return rel;
}

function messageFromErrorPayload(payload) {
  if (payload.detail != null) {
    const d = payload.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      return d.map((x) => (typeof x === "object" && x.msg ? x.msg : JSON.stringify(x))).join("; ");
    }
    return String(d);
  }
  if (payload.error) return String(payload.error);
  return "Request failed";
}

export async function api(path, opts) {
  let response;
  try {
    response = await fetch(apiUrl(path), opts);
  } catch (e) {
    throw new Error(
      `Cannot reach API (${apiUrl(path)}). Is the backend running on port 8000? ${e.message || ""}`
    );
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(messageFromErrorPayload(payload));
  }
  const ct = response.headers.get("content-type");
  if (ct && ct.includes("application/json")) {
    return response.json();
  }
  return response.text();
}
