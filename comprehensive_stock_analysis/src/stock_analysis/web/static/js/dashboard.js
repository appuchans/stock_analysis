// Report view: embed the full HTML report + build an interactive Overview
// dashboard from chart_data.json using Chart.js (loaded from CDN as `Chart`).
import { $, el, fetchJSON, fmtNum, fmtMoney, fmtCompact, badgeClass, PALETTE } from "./util.js";

let charts = [];

function destroyCharts() {
  charts.forEach((c) => { try { c.destroy(); } catch (_) {} });
  charts = [];
}

function chartDefaults() {
  if (!window.Chart) return;
  Chart.defaults.font.family =
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
  Chart.defaults.color = PALETTE.inkSoft;
  Chart.defaults.plugins.legend.labels.boxWidth = 12;
}

export async function renderReport(symbol) {
  $("#report-title").textContent = symbol;
  $("#report-frame").src = `/api/reports/${symbol}/html`;
  // default to overview tab
  $$_resetTabs();
  const host = $("#dashboard");
  host.innerHTML = "";
  destroyCharts();
  chartDefaults();

  let chart, rec;
  try {
    chart = await fetchJSON(`/api/reports/${symbol}/chart`);
  } catch (_) {
    host.append(el("p", { class: "muted" }, "No structured chart data for this symbol — see Full Report."));
    return;
  }
  try {
    const hist = await fetchJSON("/api/history");
    rec = (hist.items || []).find((it) => it.symbol === symbol);
  } catch (_) { /* recommendation banner is best-effort */ }

  if (rec && rec.recommendation) host.append(recBanner(rec));
  host.append(keyTiles(chart.key_stats || {}, chart.analyst || {}));
  const grid = el("div", { class: "grid-2" });
  host.append(grid);

  if ((chart.price_history || []).length) grid.append(panel("Price (1-year weekly)", priceChart, chart.price_history));
  const rev = chart.quarterly_revenue_m || {};
  if (Object.keys(rev).length) grid.append(panel("Quarterly revenue", revenueChart, rev));
  const counts = (chart.analyst || {}).rating_counts || {};
  if (sumCounts(counts) > 0) grid.append(panel("Analyst ratings", ratingChart, counts));
  if ((chart.valuation_scenarios || []).length) grid.append(panel("Valuation scenarios (DCF)", valuationChart, chart.valuation_scenarios));
  const sectors = chart.sector_weightings_pct || {};
  if (Object.keys(sectors).length) grid.append(panel("Sector weightings", sectorChart, sectors));

  const sent = chart.sentiment_snapshot || {};
  if (Object.values(sent).some((v) => v !== null && v !== undefined)) host.append(sentimentTiles(sent));
  if ((chart.peers || []).length) host.append(peersTable(chart.peers));
}

function $$_resetTabs() {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("is-active", x.dataset.tab === "overview"));
  $("#tab-overview").classList.remove("hidden");
  $("#tab-full").classList.add("hidden");
}

/* ── Building blocks ─────────────────────────────────────────────────────── */

function recBanner(rec) {
  const upside = rec.target_price && rec.current_price
    ? ((rec.target_price - rec.current_price) / rec.current_price) * 100 : null;
  return el("div", { class: "rec-banner" },
    el("span", { class: "rec-badge " + badgeClass(rec.recommendation) }, (rec.recommendation || "—").toUpperCase()),
    el("div", { class: "rec-meta" },
      meta("Target", fmtMoney(rec.target_price)),
      upside !== null ? meta("Implied upside", (upside >= 0 ? "+" : "") + fmtNum(upside, 1) + "%") : null,
      meta("Risk", rec.risk_level || "—"),
      meta("Confidence", rec.confidence != null ? String(rec.confidence) : "—"),
    )
  );
}
const meta = (k, v) => el("span", {}, el("b", {}, v + " "), document.createTextNode(k.toLowerCase()));

function keyTiles(stats, analyst) {
  const pt = analyst.price_targets || {};
  const tiles = [
    ["Price", fmtMoney(stats.current_price)],
    ["Market cap", fmtMoney(stats.market_cap)],
    ["P/E", fmtNum(stats.pe_ratio, 1)],
    ["52w range", stats.low_52w && stats.high_52w ? `${fmtNum(stats.low_52w)}–${fmtNum(stats.high_52w)}` : "—"],
    ["Beta", fmtNum(stats.beta, 2)],
    ["Mean target", fmtMoney(pt.mean)],
  ];
  return el("div", { class: "tiles" }, tiles.map(([k, v]) =>
    el("div", { class: "tile" }, el("div", { class: "k" }, k), el("div", { class: "v" }, v))));
}

function sentimentTiles(s) {
  const t = [
    ["Fear & Greed", s.fear_greed_score != null ? `${fmtNum(s.fear_greed_score, 0)} ${s.fear_greed_rating || ""}` : "—"],
    ["Retail bullish", s.stocktwits_bullish_pct != null ? fmtNum(s.stocktwits_bullish_pct, 0) + "%" : "—"],
    ["Put/Call OI", fmtNum(s.put_call_oi_ratio, 2)],
    ["Short % float", s.short_pct_of_float != null ? fmtNum(s.short_pct_of_float, 1) + "%" : "—"],
    ["Search momentum", s.search_momentum_pct != null ? (s.search_momentum_pct >= 0 ? "+" : "") + fmtNum(s.search_momentum_pct, 0) + "%" : "—"],
  ];
  const wrap = el("div", { class: "panel" }, el("h3", {}, "Sentiment & positioning"));
  wrap.append(el("div", { class: "tiles" }, t.map(([k, v]) =>
    el("div", { class: "tile" }, el("div", { class: "k" }, k), el("div", { class: "v" }, v)))));
  return wrap;
}

function peersTable(peers) {
  const head = el("tr", {}, ["Symbol", "Mkt cap", "P/E", "Fwd P/E", "Rev gr%", "Op mgn%"].map((h) => el("th", {}, h)));
  const rows = peers.map((p) => el("tr", { class: p.is_subject ? "subject" : "" },
    el("td", {}, p.symbol), el("td", {}, fmtMoney((p.market_cap_b || 0) * 1e9)),
    el("td", {}, fmtNum(p.pe_ttm, 1)), el("td", {}, fmtNum(p.fwd_pe, 1)),
    el("td", {}, p.revenue_growth_pct != null ? fmtNum(p.revenue_growth_pct, 1) : "—"),
    el("td", {}, p.operating_margin_pct != null ? fmtNum(p.operating_margin_pct, 1) : "—")));
  return el("div", { class: "panel" }, el("h3", {}, "Peer comparison"),
    el("table", { class: "peers" }, el("thead", {}, head), el("tbody", {}, rows)));
}

function panel(title, builder, data) {
  const canvas = el("canvas");
  const p = el("div", { class: "panel" }, el("h3", {}, title), canvas);
  // Build the chart after the canvas is in the DOM (next microtask).
  queueMicrotask(() => { try { charts.push(builder(canvas, data)); } catch (_) {} });
  return p;
}

/* ── Chart.js configs ────────────────────────────────────────────────────── */

function priceChart(canvas, points) {
  return new Chart(canvas, {
    type: "line",
    data: {
      labels: points.map((p) => p.date),
      datasets: [{
        data: points.map((p) => p.close), borderColor: PALETTE.accent,
        backgroundColor: "rgba(43,108,176,.12)", fill: true, tension: .25,
        pointRadius: 0, borderWidth: 2,
      }],
    },
    options: baseOpts({ x: { ticks: { maxTicksLimit: 6 } } }),
  });
}

function revenueChart(canvas, rev) {
  const labels = Object.keys(rev).sort();
  return new Chart(canvas, {
    type: "bar",
    data: { labels, datasets: [{ data: labels.map((l) => rev[l]), backgroundColor: PALETTE.accent }] },
    options: baseOpts({ y: { ticks: { callback: (v) => "$" + fmtCompact(v) + "M" } } }),
  });
}

function ratingChart(canvas, c) {
  return new Chart(canvas, {
    type: "doughnut",
    data: {
      labels: ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"],
      datasets: [{
        data: [c.strong_buy, c.buy, c.hold, c.sell, c.strong_sell].map((x) => x || 0),
        backgroundColor: PALETTE.ratings, borderWidth: 1, borderColor: "#fff",
      }],
    },
    options: { responsive: true, plugins: { legend: { position: "right" } } },
  });
}

function valuationChart(canvas, scen) {
  const color = (s) => /bull/i.test(s) ? PALETTE.green : /bear/i.test(s) ? PALETTE.red : PALETTE.accent;
  return new Chart(canvas, {
    type: "bar",
    data: {
      labels: scen.map((s) => s.scenario),
      datasets: [{ data: scen.map((s) => s.intrinsic_per_share), backgroundColor: scen.map((s) => color(s.scenario)) }],
    },
    options: baseOpts({ y: { ticks: { callback: (v) => "$" + fmtNum(v, 0) } } }),
  });
}

function sectorChart(canvas, sectors) {
  const labels = Object.keys(sectors);
  const colors = ["#2b6cb0", "#38a169", "#d69e2e", "#805ad5", "#dd6b20", "#319795", "#c53030", "#718096", "#3182ce", "#d53f8c", "#2f855a"];
  return new Chart(canvas, {
    type: "doughnut",
    data: { labels, datasets: [{ data: labels.map((l) => sectors[l]), backgroundColor: labels.map((_, i) => colors[i % colors.length]), borderWidth: 1, borderColor: "#fff" }] },
    options: { responsive: true, plugins: { legend: { position: "right", labels: { boxWidth: 10, font: { size: 11 } } } } },
  });
}

function baseOpts(scales = {}) {
  return {
    responsive: true,
    plugins: { legend: { display: false } },
    scales: { x: { grid: { display: false }, ...(scales.x || {}) }, y: { grid: { color: PALETTE.line }, ...(scales.y || {}) } },
  };
}

function sumCounts(c) {
  return ["strong_buy", "buy", "hold", "sell", "strong_sell"].reduce((a, k) => a + (c[k] || 0), 0);
}
