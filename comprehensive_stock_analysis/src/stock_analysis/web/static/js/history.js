// History gallery: cards with sparkline + refresh, click → report view.
import { $, el, fetchJSON, fmtNum, fmtMoney, badgeClass, navigate, sparkline, theme } from "./util.js";
import { refreshSymbol } from "./analyze.js";

let items = [];

export async function loadHistory() {
  const grid = $("#history-grid");
  const empty = $("#history-empty");
  empty.classList.add("hidden");
  grid.innerHTML = "";
  for (let i = 0; i < 4; i++) grid.append(el("div", { class: "skeleton sk-card" }));
  try {
    items = (await fetchJSON("/api/history")).items || [];
  } catch (_) { items = []; }
  $("#history-filter").oninput = render;
  render();
  empty.classList.toggle("hidden", items.length > 0);
}

function render() {
  const grid = $("#history-grid");
  const q = ($("#history-filter").value || "").toLowerCase();
  grid.innerHTML = "";
  items
    .filter((it) => !q || it.symbol.toLowerCase().includes(q) || (it.sector || "").toLowerCase().includes(q))
    .forEach((it) => grid.append(card(it)));
}

const STATUS_LABEL = { aborted: "Cancelled", failed: "Failed", incomplete: "Incomplete" };

function statusBadge(status) {
  const cls = status === "failed" ? "badge-sell" : status === "aborted" ? "badge-hold" : "badge-neutral";
  return el("span", { class: "rec-badge " + cls }, STATUS_LABEL[status] || status);
}

function recClass(rec) {
  const r = (rec || "").toLowerCase();
  return r.includes("buy") ? "buy" : r.includes("sell") ? "sell" : r.includes("hold") ? "hold" : "";
}

function card(it) {
  const completed = it.status === "completed" || it.status == null;
  const viewable = it.has_html;
  const upside = it.target_price && it.current_price
    ? ((it.target_price - it.current_price) / it.current_price) * 100 : null;

  const classes = ["report-card", viewable ? "viewable" : "not-viewable", completed ? recClass(it.recommendation) : ""];
  const node = el("div", { class: classes.filter(Boolean).join(" ") }, el("div", { class: "accent-rail" }));
  if (viewable) node.addEventListener("click", (e) => {
    if (!e.target.closest(".btn-refresh")) navigate(`#/report/${it.symbol}`);
  });

  node.append(el("div", { class: "rc-head" },
    el("span", { class: "rc-sym" }, it.symbol),
    completed
      ? (it.recommendation ? el("span", { class: "rec-badge " + badgeClass(it.recommendation) }, it.recommendation.toUpperCase()) : null)
      : statusBadge(it.status)));
  node.append(el("div", { class: "rc-name" }, it.name || it.sector || (it.asset_type === "etf" ? "ETF" : "—")));

  if (completed && (it.spark || []).length >= 2) {
    const cv = el("canvas", { class: "rc-spark" });
    node.append(cv);
    const up = it.spark[it.spark.length - 1] >= it.spark[0];
    queueMicrotask(() => sparkline(cv, it.spark, up ? theme().pos : theme().neg));
  }

  if (completed && it.asset_type === "etf") {
    // Fund-relevant facts — P/E / price target are not meaningful for an ETF.
    node.append(row("Price/NAV", fmtMoney(it.current_price)));
    node.append(row("AUM", it.aum_bn != null ? "$" + fmtNum(it.aum_bn, 2) + "B" : "—"));
    node.append(row("Expense", pctTxt(it.expense_ratio)));
    node.append(row("YTD", it.ytd_return != null ? pctEl(it.ytd_return) : "—"));
  } else if (completed) {
    node.append(row("Price", fmtMoney(it.current_price)));
    if (it.target_price != null) node.append(row("Target", fmtMoney(it.target_price)));
    if (upside !== null) node.append(row("Upside", upsideEl(upside)));
    node.append(row("P/E", fmtNum(it.pe_ratio, 1)));
  } else {
    node.append(el("div", { class: "rc-row muted" }, el("span", {},
      viewable ? "Showing the last completed report" : "No report was produced")));
  }

  node.append(el("div", { class: "rc-foot" },
    el("span", { class: "when" }, it.mtime ? it.mtime.replace("T", " ") : "—"),
    el("button", { class: "btn btn-ghost btn-sm btn-refresh", title: "Re-run with fresh data",
      onclick: () => refreshSymbol(it.symbol, it.asset_type) },
      el("span", { class: "ic", html: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.6-6.4M21 3v6h-6"/></svg>' }),
      "Refresh")));
  return node;
}

const row = (lbl, val) =>
  el("div", { class: "rc-row" }, el("span", { class: "lbl" }, lbl),
    val && val.nodeType ? val : el("span", { class: "num" }, val));

function upsideEl(u) {
  return el("span", { class: "num " + (u >= 0 ? "pos" : "neg") }, (u >= 0 ? "+" : "") + fmtNum(u, 1) + "%");
}

// Fraction (0.005 = 0.5%) → text.
function pctTxt(v) {
  return v == null ? "—" : (v * 100).toFixed(2).replace(/\.?0+$/, "") + "%";
}

// Fraction → delta-colored percent span (for YTD return).
function pctEl(v) {
  const x = v * 100;
  return el("span", { class: "num " + (x >= 0 ? "pos" : "neg") }, (x >= 0 ? "+" : "") + fmtNum(x, 2) + "%");
}
