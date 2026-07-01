// Shared helpers: DOM, fetch, formatting, theme-aware colors, sparklines.

export function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// Colors pulled live from the active theme so charts re-theme on dark/light.
export function theme() {
  return {
    text: cssVar("--text-2") || "#4a5a70",
    faint: cssVar("--text-3") || "#8a98ab",
    grid: cssVar("--border") || "#e6eaf1",
    accent: cssVar("--accent") || "#2563eb",
    accent2: cssVar("--accent-2") || "#3b82f6",
    pos: cssVar("--pos") || "#15803d",
    neg: cssVar("--neg") || "#b91c1c",
    warn: cssVar("--warn") || "#b45309",
    surface: cssVar("--surface") || "#ffffff",
    ratings: ["#15803d", "#22c55e", cssVar("--warn") || "#d97706", "#ef4444", "#991b1b"],
    sectors: ["#2563eb", "#16a34a", "#d97706", "#7c3aed", "#dc2626", "#0891b2", "#db2777", "#65a30d", "#ea580c", "#475569"],
  };
}

export function isDark() {
  return document.documentElement.getAttribute("data-theme") === "dark";
}

// Tiny axis-less sparkline drawn straight to a canvas (history cards).
export function sparkline(canvas, values, color) {
  const vals = (values || []).filter((v) => v !== null && v !== undefined);
  if (vals.length < 2) return;
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 240, h = canvas.clientHeight || 34;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
  const x = (i) => (i / (vals.length - 1)) * (w - 2) + 1;
  const y = (v) => h - 3 - ((v - min) / span) * (h - 6);
  ctx.beginPath();
  vals.forEach((v, i) => (i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v))));
  // area fill
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, color + "33"); grad.addColorStop(1, color + "00");
  ctx.lineTo(x(vals.length - 1), h); ctx.lineTo(x(0), h); ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();
  // line
  ctx.beginPath();
  vals.forEach((v, i) => (i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v))));
  ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.lineJoin = "round"; ctx.stroke();
}

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
