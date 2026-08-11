// Portfolio view: transactions ledger, live-priced positions, value/benchmark
// charts, allocation donut, and an "advisor vs position" panel.
import { $, el, fetchJSON, fmtNum, fmtMoney, badgeClass, theme, navigate, makeSortable } from "./util.js";

let charts = [];
let recBySymbol = {};

function destroyCharts() {
  charts.forEach((c) => { try { c.destroy(); } catch (_) {} });
  charts = [];
}

export async function loadPortfolio() {
  $("#tx-form").onsubmit = onAddTransaction;
  $("#tx-import-form").onsubmit = onImportCsv;
  $("#portfolio-refresh").onclick = onRefresh;
  await Promise.all([loadTransactions(), loadDashboard()]);
}

async function onRefresh() {
  const btn = $("#portfolio-refresh");
  btn.disabled = true;
  try {
    await loadDashboard();
  } finally {
    btn.disabled = false;
  }
}

/* ── Transactions ──────────────────────────────────────────────────────── */

async function loadTransactions() {
  let items = [];
  try {
    items = await fetchJSON("/api/portfolio/transactions");
  } catch (_) { items = []; }
  $("#tx-empty").classList.toggle("hidden", items.length > 0);
  const thead = $("#tx-body").closest("table").querySelector("thead");
  makeSortable(thead, $("#tx-body"), items.slice().reverse(), txRow, [
    (t) => t.date, (t) => t.symbol, (t) => t.side, (t) => t.qty, (t) => t.price, (t) => t.fees, null,
  ]);
}

function txRow(t) {
  const tr = el("tr", {});
  tr.append(el("td", {}, t.date));
  tr.append(el("td", {}, el("div", { class: "wl-sym" }, t.symbol)));
  tr.append(el("td", {}, el("span", { class: "rec-badge " + (t.side === "buy" ? "badge-buy" : "badge-sell") }, t.side.toUpperCase())));
  tr.append(el("td", { class: "num" }, fmtNum(t.qty, 4)));
  tr.append(el("td", { class: "num" }, fmtMoney(t.price)));
  tr.append(el("td", { class: "num" }, fmtMoney(t.fees)));
  tr.append(el("td", { class: "wl-actions" },
    el("button", { class: "btn btn-ghost btn-sm btn-danger", onclick: () => onDeleteTransaction(t.id) }, "Delete")));
  return tr;
}

async function onAddTransaction(ev) {
  ev.preventDefault();
  const payload = {
    symbol: $("#tx-symbol").value.trim().toUpperCase(),
    side: $("#tx-side").value,
    qty: Number($("#tx-qty").value),
    price: Number($("#tx-price").value),
    fees: Number($("#tx-fees").value) || 0,
    date: $("#tx-date").value,
    note: $("#tx-note").value.trim(),
  };
  try {
    await fetchJSON("/api/portfolio/transactions", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    $("#tx-symbol").value = ""; $("#tx-qty").value = ""; $("#tx-price").value = "";
    $("#tx-fees").value = ""; $("#tx-note").value = "";
    await Promise.all([loadTransactions(), loadDashboard()]);
  } catch (err) {
    alert(err.message);
  }
}

async function onDeleteTransaction(id) {
  try {
    await fetchJSON(`/api/portfolio/transactions/${id}`, { method: "DELETE" });
  } catch (_) { /* 204 has no body */ }
  await Promise.all([loadTransactions(), loadDashboard()]);
}

async function onImportCsv(ev) {
  ev.preventDefault();
  const status = $("#tx-import-status");
  const csv = $("#tx-import-text").value;
  if (!csv.trim()) return;
  try {
    const result = await fetchJSON("/api/portfolio/transactions/import", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ csv }),
    });
    status.textContent = `Imported ${result.imported} transaction(s).`;
    status.className = "muted pos";
    $("#tx-import-text").value = "";
    await Promise.all([loadTransactions(), loadDashboard()]);
  } catch (err) {
    status.textContent = err.message;
    status.className = "muted neg";
  }
}

/* ── Dashboard: positions, totals, charts ─────────────────────────────────── */

async function loadDashboard() {
  const host = $("#portfolio-dashboard");
  destroyCharts();
  let data;
  try {
    data = await fetchJSON("/api/portfolio/dashboard");
  } catch (_) {
    host.innerHTML = "";
    host.append(el("div", { class: "panel" }, el("p", { class: "muted" }, "Could not load portfolio data.")));
    return;
  }

  $("#portfolio-empty").classList.toggle("hidden", data.positions.length > 0);
  host.innerHTML = "";
  if (!data.positions.length) return;

  // Recommendations for the "advisor vs position" panel — best-effort.
  try {
    const hist = await fetchJSON("/api/history");
    recBySymbol = Object.fromEntries((hist.items || []).map((it) => [it.symbol, it]));
  } catch (_) { recBySymbol = {}; }

  host.append(totalsRow(data));
  const grid = el("div", { class: "grid-2" });
  host.append(grid);
  if (data.value_series.length > 1) grid.append(chartPanel("Portfolio value", valueChart, data.value_series));
  if (data.benchmark_comparison) grid.append(chartPanel(`vs ${data.benchmark_symbol}`, benchmarkChart, data.benchmark_comparison));
  host.append(allocationAndTable(data));
  host.append(advisorVsPositionPanel(data.positions));
}

function totalsRow(data) {
  const items = [
    { k: "Market value", v: fmtMoney(data.total_market_value) },
    { k: "Cost basis", v: fmtMoney(data.total_cost_basis) },
    { k: "Unrealized P&L", v: fmtMoney(data.total_unrealized_pnl), cls: deltaCls(data.total_unrealized_pnl) },
    { k: "Realized P&L", v: fmtMoney(data.total_realized_pnl), cls: deltaCls(data.total_realized_pnl) },
  ];
  if (data.benchmark_comparison) {
    items.push({ k: "Alpha (ann.)", v: fmtNum(data.benchmark_comparison.alpha_annualized_pct, 1) + "%",
      cls: deltaCls(data.benchmark_comparison.alpha_annualized_pct) });
    items.push({ k: "Beta", v: fmtNum(data.benchmark_comparison.beta, 2) });
  }
  return el("div", { class: "tiles" }, items.map((it) =>
    el("div", { class: "tile" }, el("div", { class: "k" }, it.k), el("div", { class: "v " + (it.cls || "") }, it.v))));
}

const deltaCls = (v) => (v == null ? "" : v > 0 ? "pos" : v < 0 ? "neg" : "");

function allocationAndTable(data) {
  const wrap = el("div", { class: "grid-2" });
  wrap.append(chartPanel("Allocation", allocationChart, data.positions));
  wrap.append(positionsTable(data.positions));
  return wrap;
}

function positionRow(p) {
  return el("tr", { class: "clickable", onclick: () => navigate(`#/report/${p.symbol}`) },
    el("td", {}, p.symbol),
    el("td", {}, fmtNum(p.qty, 4)),
    el("td", {}, fmtMoney(p.avg_cost)),
    el("td", {}, fmtMoney(p.current_price)),
    el("td", {}, fmtMoney(p.market_value)),
    el("td", { class: deltaCls(p.unrealized_pnl) }, fmtMoney(p.unrealized_pnl)),
    el("td", {}, p.weight != null ? fmtNum(p.weight * 100, 1) + "%" : "—"));
}

function positionsTable(positions) {
  const head = el("tr", {}, ["Symbol", "Qty", "Avg cost", "Price", "Value", "Unrl. P&L", "Weight"].map((h) => el("th", {}, h)));
  const thead = el("thead", {}, head);
  const tbody = el("tbody", {});
  const table = el("table", { class: "peers" }, thead, tbody);
  makeSortable(thead, tbody, positions, positionRow, [
    (p) => p.symbol, (p) => p.qty, (p) => p.avg_cost, (p) => p.current_price,
    (p) => p.market_value, (p) => p.unrealized_pnl, (p) => p.weight,
  ]);
  return el("div", { class: "panel" }, el("h3", {}, "Positions"),
    el("div", { style: "margin-top:12px;overflow-x:auto" }, table));
}

function advisorVsPositionPanel(positions) {
  const rows = positions.map((p) => {
    const rec = recBySymbol[p.symbol];
    if (!rec || !rec.recommendation) {
      return el("div", { class: "diff-row" }, el("span", { class: "diff-label" }, p.symbol), el("span", { class: "muted" }, "Not yet analyzed"));
    }
    const vsTarget = rec.target_price && p.current_price
      ? ((rec.target_price - p.current_price) / p.current_price) * 100 : null;
    return el("div", { class: "diff-row" },
      el("span", { class: "diff-label" }, p.symbol),
      el("span", { class: "rec-badge " + badgeClass(rec.recommendation) }, rec.recommendation.toUpperCase()),
      vsTarget != null ? el("span", { class: deltaCls(vsTarget) }, (vsTarget >= 0 ? "+" : "") + fmtNum(vsTarget, 1) + "% to target") : el("span", {}, ""));
  });
  return el("div", { class: "panel", style: "margin-top:18px" },
    el("div", { class: "panel-head" }, el("h3", {}, "Advisor vs. position")),
    el("p", { class: "panel-sub" }, "Latest recommendation for each holding, and how far the current price sits from the analyst target."),
    el("div", { class: "diff-rows" }, rows));
}

function chartPanel(title, builder, data) {
  const canvas = el("canvas");
  const p = el("div", { class: "panel" }, el("h3", {}, title), el("div", { style: "margin-top:12px" }, canvas));
  queueMicrotask(() => { try { charts.push(builder(canvas, data)); } catch (_) {} });
  return p;
}

function chartDefaults() {
  if (!window.Chart) return;
  const t = theme();
  Chart.defaults.font.family = '"Inter var", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
  Chart.defaults.font.size = 11.5;
  Chart.defaults.color = t.faint;
}

function baseOpts(scales = {}) {
  const t = theme();
  return {
    responsive: true,
    plugins: { legend: { display: false } },
    scales: {
      x: { grid: { display: false }, border: { color: t.grid }, ...(scales.x || {}) },
      y: { grid: { color: t.grid }, border: { display: false }, ...(scales.y || {}) },
    },
  };
}

function valueChart(canvas, series) {
  chartDefaults();
  const t = theme();
  const ctx = canvas.getContext("2d");
  const grad = ctx.createLinearGradient(0, 0, 0, 240);
  grad.addColorStop(0, t.accent + "33"); grad.addColorStop(1, t.accent + "00");
  return new Chart(canvas, {
    type: "line",
    data: { labels: series.map((p) => p.date), datasets: [{
      data: series.map((p) => p.value), borderColor: t.accent, backgroundColor: grad,
      fill: true, tension: .2, pointRadius: 0, borderWidth: 2 }] },
    options: baseOpts({
      x: { ticks: { maxTicksLimit: 6 } },
      y: { ticks: { callback: (v) => "$" + fmtNum(v, 0) } },
    }),
  });
}

function benchmarkChart(canvas, cmp) {
  chartDefaults();
  const t = theme();
  return new Chart(canvas, {
    type: "line",
    data: {
      labels: cmp.portfolio_indexed.map((p) => p.date),
      datasets: [
        { label: "Portfolio", data: cmp.portfolio_indexed.map((p) => p.value), borderColor: t.accent, pointRadius: 0, borderWidth: 2, tension: .2 },
        { label: "Benchmark", data: cmp.benchmark_indexed.map((p) => p.value), borderColor: t.faint, pointRadius: 0, borderWidth: 2, borderDash: [4, 3], tension: .2 },
      ],
    },
    options: {
      ...baseOpts({ x: { ticks: { maxTicksLimit: 6 } } }),
      plugins: { legend: { display: true, position: "top", labels: { boxWidth: 10 } } },
    },
  });
}

function allocationChart(canvas, positions) {
  chartDefaults();
  const t = theme();
  const withWeight = positions.filter((p) => p.weight != null);
  return new Chart(canvas, {
    type: "doughnut",
    data: {
      labels: withWeight.map((p) => p.symbol),
      datasets: [{ data: withWeight.map((p) => p.weight), backgroundColor: withWeight.map((_, i) => t.sectors[i % t.sectors.length]), borderWidth: 2, borderColor: t.surface }],
    },
    options: { responsive: true, cutout: "60%", plugins: { legend: { position: "right", labels: { boxWidth: 10, font: { size: 11 } } } } },
  });
}
