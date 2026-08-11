// Compare page: pick up to 4 symbols (analyzed or not), see price performance
// and key metrics side by side. Metrics are fetched live — no prior analysis
// required, though an already-analyzed symbol's row links to its full report.
import { $, el, fetchJSON, fmtNum, fmtMoney, makeSortable } from "./util.js";
import { renderPriceChart } from "./priceChart.js";
import { periodSelector, symbolChipInput } from "./chartControls.js";

let symbols = [];
let period = "1y";
let chartInstance = null;

export async function loadCompare() {
  const host = $("#compare-input-host");
  host.innerHTML = "";
  host.append(symbolChipInput({
    getSymbols: () => symbols,
    onChange: (syms) => { symbols = syms; refresh(); },
    placeholder: "Add symbol (e.g. AAPL)",
    maxSymbols: 4,
  }));
  await refresh();
}

async function refresh() {
  const results = $("#compare-results");
  const empty = $("#compare-empty");
  if (!symbols.length) {
    results.innerHTML = "";
    if (chartInstance) { try { chartInstance.destroy(); } catch (_) { /* noop */ } chartInstance = null; }
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");
  results.innerHTML = "";
  results.append(loadingPanel());

  const symbolsParam = symbols.join(",");
  let pricesData, metricsData;
  try {
    [pricesData, metricsData] = await Promise.all([
      fetchJSON(`/api/compare/prices?symbols=${symbolsParam}&period=${period}`),
      fetchJSON(`/api/compare/metrics?symbols=${symbolsParam}`),
    ]);
  } catch (err) {
    results.innerHTML = "";
    results.append(el("div", { class: "panel" }, el("p", { class: "muted" }, "Could not load comparison data.")));
    return;
  }

  results.innerHTML = "";
  results.append(priceChartPanel(pricesData));
  if (metricsData.symbols.length) {
    results.append(metricsTable(metricsData.symbols));
  }
  if (metricsData.omitted && metricsData.omitted.length) {
    results.append(el("p", { class: "muted", style: "margin-top:10px" },
      `Could not load: ${metricsData.omitted.join(", ")}`));
  }
}

function loadingPanel() {
  return el("div", { class: "panel" }, el("div", { class: "skeleton sk-card" }));
}

function priceChartPanel(pricesData) {
  const canvas = el("canvas");
  const controls = el("div", { class: "panel-toolbar" },
    periodSelector(period, (p) => { period = p; refresh(); }));
  queueMicrotask(() => {
    if (chartInstance) { try { chartInstance.destroy(); } catch (_) { /* noop */ } }
    chartInstance = renderPriceChart(canvas, pricesData.series);
  });
  return el("div", { class: "panel" }, el("h3", {}, "Price performance"), controls,
    el("div", { style: "margin-top:12px" }, canvas));
}

function metricRow(row) {
  const ks = row.key_stats || {};
  const pt = (row.analyst || {}).price_targets || {};
  const symCell = row.has_report
    ? el("a", { href: `#/report/${row.symbol}` }, row.symbol)
    : row.symbol;
  return el("tr", {},
    el("td", {}, symCell),
    el("td", {}, fmtMoney(ks.current_price)),
    el("td", {}, ks.market_cap_b != null ? fmtMoney(ks.market_cap_b * 1e9) : "—"),
    el("td", {}, fmtNum(ks.pe_ttm, 1)),
    el("td", {}, fmtNum(ks.fwd_pe, 1)),
    el("td", {}, fmtNum(ks.beta, 2)),
    el("td", {}, ks.low_52w != null && ks.high_52w != null ? `${fmtNum(ks.low_52w)}–${fmtNum(ks.high_52w)}` : "—"),
    el("td", {}, ks.revenue_growth_pct != null ? fmtNum(ks.revenue_growth_pct, 1) + "%" : "—"),
    el("td", {}, ks.operating_margin_pct != null ? fmtNum(ks.operating_margin_pct, 1) + "%" : "—"),
    el("td", {}, fmtMoney(pt.mean)),
    el("td", { class: pt.implied_upside_pct >= 0 ? "pos" : "neg" },
      pt.implied_upside_pct != null ? (pt.implied_upside_pct >= 0 ? "+" : "") + fmtNum(pt.implied_upside_pct, 1) + "%" : "—"));
}

function metricsTable(rows) {
  const labels = ["Symbol", "Price", "Mkt cap", "P/E", "Fwd P/E", "Beta", "52w range", "Rev gr%", "Op mgn%", "Analyst target", "Upside"];
  const head = el("tr", {}, labels.map((h) => el("th", {}, h)));
  const thead = el("thead", {}, head);
  const tbody = el("tbody", {});
  const table = el("table", { class: "peers" }, thead, tbody);
  makeSortable(thead, tbody, rows, metricRow, [
    (r) => r.symbol,
    (r) => (r.key_stats || {}).current_price,
    (r) => (r.key_stats || {}).market_cap_b,
    (r) => (r.key_stats || {}).pe_ttm,
    (r) => (r.key_stats || {}).fwd_pe,
    (r) => (r.key_stats || {}).beta,
    null,
    (r) => (r.key_stats || {}).revenue_growth_pct,
    (r) => (r.key_stats || {}).operating_margin_pct,
    (r) => ((r.analyst || {}).price_targets || {}).mean,
    (r) => ((r.analyst || {}).price_targets || {}).implied_upside_pct,
  ]);
  return el("div", { class: "panel", style: "margin-top:18px" }, el("h3", {}, "Key metrics"),
    el("div", { style: "margin-top:12px;overflow-x:auto" }, table));
}
