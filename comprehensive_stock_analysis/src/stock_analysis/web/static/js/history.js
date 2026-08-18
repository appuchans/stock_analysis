// History gallery: cards with sparkline + refresh, click → report view.
import { $, el, fetchJSON, fmtNum, fmtCompact, fmtMoney, badgeClass, navigate, sparkline, theme } from "./util.js";
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
  $("#history-sort").onchange = render;
  render();
  empty.classList.toggle("hidden", items.length > 0);
}

const SORTERS = {
  newest: (a, b) => (b.mtime || "").localeCompare(a.mtime || ""),
  oldest: (a, b) => (a.mtime || "").localeCompare(b.mtime || ""),
  symbol: (a, b) => a.symbol.localeCompare(b.symbol),
  recommendation: (a, b) => (a.recommendation || "").localeCompare(b.recommendation || ""),
};

function render() {
  const grid = $("#history-grid");
  const q = ($("#history-filter").value || "").toLowerCase();
  const sortKey = $("#history-sort").value || "newest";
  grid.innerHTML = "";
  items
    .filter((it) => !q || it.symbol.toLowerCase().includes(q) || (it.sector || "").toLowerCase().includes(q))
    .slice()
    .sort(SORTERS[sortKey] || SORTERS.newest)
    .forEach((it) => grid.append(card(it)));
}

const STATUS_LABEL = { aborted: "Cancelled", failed: "Failed", incomplete: "Incomplete" };

function statusBadge(status) {
  const cls = status === "failed" ? "badge-sell" : status === "aborted" ? "badge-hold" : "badge-neutral";
  return el("span", { class: "rec-badge " + cls }, STATUS_LABEL[status] || status);
}

/** Hover text naming every stage and artifact the run failed to produce. */
function incompleteDetail(degradations, review) {
  const lines = [];
  for (const d of degradations || []) lines.push("• " + d);
  for (const i of (review && review.issues) || []) {
    if (i.severity === "error") lines.push("• " + i.detail);
  }
  return lines.length ? "Not produced by this run:\n" + lines.join("\n") : "";
}

function recClass(rec) {
  const r = (rec || "").toLowerCase();
  return r.includes("buy") ? "buy" : r.includes("sell") ? "sell" : r.includes("hold") ? "hold" : "";
}

function card(it) {
  const completed = it.status === "completed" || it.status == null;
  const viewable = it.has_html;
  // A run can report "completed" and still be partial: the flow degrades rather
  // than aborting (so partial output beats none), and run_review.py separately
  // checks the artifacts the tile needs. Either signal means the report on disk
  // is not whole, and the tile must say so instead of looking like a clean run.
  const degradations = it.degradations || [];
  const reviewErrors = it.review && !it.review.ok ? (it.review.error_count || 0) : 0;
  const incomplete = completed && (degradations.length > 0 || reviewErrors > 0);
  const upside = it.target_price && it.current_price
    ? ((it.target_price - it.current_price) / it.current_price) * 100 : null;
  // Negative by construction (price sits at or below the 52w high), so it reads
  // as a drawdown from the peak rather than a gain.
  const offHigh = it.high_52w && it.current_price
    ? ((it.current_price - it.high_52w) / it.high_52w) * 100 : null;

  const classes = ["report-card", viewable ? "viewable" : "not-viewable",
    completed ? recClass(it.recommendation) : "", incomplete ? "is-incomplete" : ""];
  const node = el("div", { class: classes.filter(Boolean).join(" ") }, el("div", { class: "accent-rail" }));
  if (viewable) node.addEventListener("click", (e) => {
    if (!e.target.closest(".btn-refresh")) navigate(`#/report/${it.symbol}`);
  });

  // Why "Incomplete output" replaces the rating badge rather than sitting next
  // to it: a BUY badge on a run whose recommendation stage failed is actively
  // misleading. The rating still shows in a row below when one exists.
  const headBadge = !completed
    ? statusBadge(it.status)
    : incomplete
      ? el("span", { class: "rec-badge badge-neutral badge-incomplete",
          title: incompleteDetail(degradations, it.review) }, "Incomplete output")
      : (it.recommendation ? el("span", { class: "rec-badge " + badgeClass(it.recommendation) }, it.recommendation.toUpperCase()) : null);
  node.append(el("div", { class: "rc-head" },
    el("span", { class: "rc-sym" }, it.symbol),
    headBadge));
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
    if (it.distribution_yield != null) node.append(row("Yield", pctTxt(it.distribution_yield)));
  } else if (completed) {
    // Every row below is rendered only when its datum exists, so a tile is as
    // full as the data allows rather than a fixed short list. Price and YTD are
    // the two constants — YTD is derived from the charted series server-side,
    // so it is present for stocks as well as ETFs.
    node.append(row("Price", fmtMoney(it.current_price)));
    if (it.ytd_return != null) node.append(row("YTD", pctEl(it.ytd_return)));
    if (it.target_price != null) node.append(row("Target", fmtMoney(it.target_price)));
    if (upside !== null) node.append(row("Upside", upsideEl(upside)));
    if (it.pe_ratio != null) node.append(row("P/E", fmtNum(it.pe_ratio, 1)));
    if (it.market_cap != null) node.append(row("Mkt cap", fmtCompact(it.market_cap)));
    if (it.dividend_yield != null) node.append(row("Yield", pctTxt(it.dividend_yield)));
    if (it.beta != null) node.append(row("Beta", fmtNum(it.beta, 2)));
    if (offHigh !== null) node.append(row("Off 52w high", upsideEl(offHigh)));
  } else {
    node.append(el("div", { class: "rc-row muted" }, el("span", {},
      viewable ? "Showing the last completed report" : "No report was produced")));
  }

  // Keep the rating visible even on an incomplete run — it just no longer gets
  // to masquerade as the headline verdict of a whole report.
  if (incomplete && it.recommendation) {
    node.append(row("Rating", it.recommendation.toUpperCase()));
  }

  // Name what is actually missing, so "Incomplete output" is diagnosable
  // without opening the report or reading the logs.
  if (incomplete) {
    const parts = [];
    if (degradations.length) {
      parts.push(degradations.length + (degradations.length === 1 ? " stage" : " stages"));
    }
    if (reviewErrors) {
      parts.push(reviewErrors + (reviewErrors === 1 ? " artifact" : " artifacts"));
    }
    node.append(el("div", { class: "rc-row rc-review", title: incompleteDetail(degradations, it.review) },
      el("span", { class: "lbl warn" }, "⚠ Missing"),
      el("span", { class: "num warn" }, parts.join(" · "))));
  }

  // A run that ended incomplete (or was cancelled / failed) resumes instead of
  // restarting: the stages that already succeeded are reused and only the
  // missing ones re-run, so a partial run costs its remainder, not full price.
  const canResume = incomplete || it.status === "aborted" || it.status === "failed";
  node.append(el("div", { class: "rc-foot" },
    el("span", { class: "when" }, it.mtime ? it.mtime.replace("T", " ") : "—"),
    el("button", { class: "btn btn-ghost btn-sm btn-refresh",
      title: canResume
        ? "Resume — reuse the stages that finished, re-run only what is missing"
        : "Re-run with fresh data",
      onclick: () => refreshSymbol(it.symbol, it.asset_type, canResume) },
      el("span", { class: "ic" }, refreshIcon()),
      canResume ? "Resume" : "Refresh")));
  return node;
}

// Built via createElementNS (not el()'s generic innerHTML sink) — this is the
// only inline icon this module needs.
function refreshIcon() {
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  for (const [k, v] of Object.entries({
    viewBox: "0 0 24 24", width: "14", height: "14", fill: "none",
    stroke: "currentColor", "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round",
  })) svg.setAttribute(k, v);
  const path = document.createElementNS(svgNS, "path");
  path.setAttribute("d", "M21 12a9 9 0 1 1-2.6-6.4M21 3v6h-6");
  svg.append(path);
  return svg;
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
