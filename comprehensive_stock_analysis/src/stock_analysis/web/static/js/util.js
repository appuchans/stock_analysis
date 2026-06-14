// Shared helpers: DOM, fetch, formatting, brand palette.

export const PALETTE = {
  ink: "#1a202c", inkSoft: "#4a5568", inkFaint: "#718096",
  brand: "#1a365d", accent: "#2b6cb0",
  green: "#276749", amber: "#744210", red: "#822727",
  line: "#e2e8f0", bgSoft: "#f7fafc",
  ratings: ["#22543d", "#38a169", "#d69e2e", "#c53030", "#822727"], // strong buy→strong sell
};

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// Hash navigation. Defined here (not app.js) so view modules can import it
// without a circular dependency on the router.
export function navigate(hash) {
  if (location.hash === hash) window.dispatchEvent(new HashChangeEvent("hashchange"));
  else location.hash = hash;
}

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined) continue;
    node.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return node;
}

export async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `${res.status} ${res.statusText}`);
  return body;
}

export function fmtNum(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function fmtCompact(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const a = Math.abs(v);
  for (const [d, s] of [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "K"]]) {
    if (a >= d) return (v / d).toFixed(2).replace(/\.?0+$/, "") + s;
  }
  return fmtNum(v);
}

export function fmtMoney(v) {
  return v === null || v === undefined || Number.isNaN(v) ? "—" : "$" + fmtCompact(v);
}

export function badgeClass(rec) {
  const r = (rec || "").toLowerCase();
  if (r.includes("buy")) return "badge-buy";
  if (r.includes("sell")) return "badge-sell";
  if (r.includes("hold")) return "badge-hold";
  return "badge-neutral";
}
