// Report view: embed the full HTML report + build the interactive Overview
// dashboard from chart_data.json using Chart.js, themed to match light/dark.
import { $, $$, el, fetchJSON, fmtNum, fmtMoney, fmtCompact, badgeClass, theme, timeAgo } from "./util.js";

let charts = [];
let last = null; // { symbol, chart, rec } — kept so we can re-theme without refetch

function destroyCharts() {
  charts.forEach((c) => { try { c.destroy(); } catch (_) {} });
  charts = [];
}

function chartDefaults() {
  if (!window.Chart) return;
  const t = theme();
  Chart.defaults.font.family = '"Inter var", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
  Chart.defaults.font.size = 11.5;
  Chart.defaults.color = t.faint;
  Chart.defaults.plugins.legend.labels.boxWidth = 11;
  Chart.defaults.plugins.legend.labels.boxHeight = 11;
  Chart.defaults.plugins.tooltip.backgroundColor = t.text === "#4a5a70" ? "#0f1b2d" : "#0a1019";
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
}

export async function renderReport(symbol) {
  $("#report-title").textContent = symbol;
  $("#report-name").textContent = "";
  $("#report-frame").src = `/api/reports/${symbol}/html`;
  resetTabs();
  const host = $("#dashboard");
  host.innerHTML = "";
  host.append(skeleton());
  destroyCharts();

  let chart, rec;
  try {
    chart = await fetchJSON(`/api/reports/${symbol}/chart`);
  } catch (_) {
    host.innerHTML = "";
    host.append(el("div", { class: "panel" }, el("p", { class: "muted" },
      "No structured overview for this symbol — open the Full Report tab.")));
    return;
  }
  try {
    const hist = await fetchJSON("/api/history");
    rec = (hist.items || []).find((it) => it.symbol === symbol);
  } catch (_) { /* recommendation banner is best-effort */ }

  let diff = null;
  try {
    diff = await fetchJSON(`/api/reports/${symbol}/diff`);
  } catch (_) { /* diff panel is best-effort — older reports may lack a prev snapshot */ }

  last = { symbol, chart, rec, diff };
  buildDashboard();
}

function buildDashboard() {
  const { symbol, chart, rec, diff } = last;
  const isEtf = chart.asset_type === "etf" || !!chart.etf_profile;
  const company = chart.company || {};
  $("#report-name").textContent = company.name || "";
  const refresh = $("#report-refresh");
  if (refresh) { refresh.dataset.symbol = symbol; refresh.dataset.asset = chart.asset_type || "auto"; }

  const host = $("#dashboard");
  host.innerHTML = "";
  destroyCharts();
  chartDefaults();

  if (chart.data_fetched_at) host.append(freshnessChip(chart.data_fetched_at));
  if (rec && rec.recommendation) host.append(recBanner(rec));
  if (diff && diff.has_diff) host.append(diffPanel(diff));
  host.append(isEtf
    ? etfTiles(chart.key_stats || {}, chart.etf_profile || {}, symbol)
    : keyTiles(chart.key_stats || {}, chart.analyst || {}));

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

function resetTabs() {
  $$(".tab").forEach((x) => x.classList.toggle("is-active", x.dataset.tab === "overview"));
  $("#tab-overview").classList.remove("hidden");
  $("#tab-full").classList.add("hidden");
}

function skeleton() {
  const wrap = el("div", {});
  wrap.append(el("div", { class: "skeleton", style: "height:74px;margin-bottom:18px" }));
  const g = el("div", { class: "tiles", style: "margin-bottom:18px" });
  for (let i = 0; i < 6; i++) g.append(el("div", { class: "skeleton", style: "height:78px" }));
  wrap.append(g);
  const g2 = el("div", { class: "grid-2" });
  g2.append(el("div", { class: "skeleton sk-card" }), el("div", { class: "skeleton sk-card" }));
  wrap.append(g2);
  return wrap;
}

/* ── Building blocks ─────────────────────────────────────────────────────── */

const deltaCls = (v) => (v == null ? "" : v > 0 ? "pos" : v < 0 ? "neg" : "");

function freshnessChip(iso) {
  const ago = timeAgo(iso);
  return el("div", { class: "freshness-row" },
    el("span", { class: "chip" }, `Data as of ${ago || (iso || "").replace("T", " ")}`));
}

// "What changed since the last run" — built from GET /api/reports/{symbol}/diff.
function diffPanel(diff) {
  const rows = [];
  if (diff.recommendation_changed) {
    rows.push(diffRow("Recommendation",
      `${diff.previous?.recommendation || "—"} → ${diff.current?.recommendation || "—"}`, "changed"));
  }
  if (diff.target_price_delta != null && Math.abs(diff.target_price_delta) > 0.005) {
    rows.push(diffRow("Target price",
      (diff.target_price_delta >= 0 ? "+" : "") + fmtMoney(diff.target_price_delta),
      deltaCls(diff.target_price_delta)));
  }
  if (diff.confidence_delta != null && Math.abs(diff.confidence_delta) > 0.005) {
    rows.push(diffRow("Confidence",
      (diff.confidence_delta >= 0 ? "+" : "") + fmtNum(diff.confidence_delta * 100, 0) + "%",
      deltaCls(diff.confidence_delta)));
  }
  (diff.new_risks || []).forEach((r) => rows.push(diffRow("New risk", r, "neg")));
  (diff.removed_risks || []).forEach((r) => rows.push(diffRow("Resolved risk", r, "pos")));
  (diff.new_opportunities || []).forEach((o) => rows.push(diffRow("New opportunity", o, "pos")));
  (diff.removed_opportunities || []).forEach((o) => rows.push(diffRow("Dropped opportunity", o, "")));

  if (!rows.length) return null;
  return el("div", { class: "panel diff-panel" },
    el("div", { class: "panel-head" }, el("h3", {}, "What changed since the last run")),
    el("div", { class: "diff-rows" }, rows));
}

function diffRow(label, value, cls) {
  return el("div", { class: "diff-row" },
    el("span", { class: "diff-label" }, label),
    el("span", { class: "diff-value " + (cls || "") }, value));
}

function recBanner(rec) {
  const upside = rec.target_price && rec.current_price
    ? ((rec.target_price - rec.current_price) / rec.current_price) * 100 : null;
  return el("div", { class: "rec-banner" },
    el("span", { class: "rec-badge " + badgeClass(rec.recommendation) }, (rec.recommendation || "—").toUpperCase()),
    el("div", { class: "rec-meta" },
      rec.target_price != null ? meta("Target", fmtMoney(rec.target_price)) : null,
      upside !== null ? meta("Implied upside", (upside >= 0 ? "+" : "") + fmtNum(upside, 1) + "%", deltaCls(upside)) : null,
      rec.risk_level ? meta("Risk", rec.risk_level) : null,
      rec.confidence != null ? meta("Confidence", String(rec.confidence)) : null,
    )
  );
}
const meta = (k, v, cls) => el("span", {}, el("b", { class: cls || "" }, v), document.createTextNode(k));

function tiles(items) {
  return el("div", { class: "tiles" }, items.filter(Boolean).map((it) =>
    el("div", { class: "tile", title: it.title || null },
      el("div", { class: "k" }, it.k),
      el("div", { class: "v " + (it.cls || "") }, it.v),
      it.sub ? el("div", { class: "sub" }, it.sub) : null)));
}

function keyTiles(stats, analyst) {
  const pt = analyst.price_targets || {};
  return tiles([
    { k: "Price", v: fmtMoney(stats.current_price) },
    { k: "Market cap", v: fmtMoney(stats.market_cap) },
    { k: "P/E", v: fmtNum(stats.pe_ratio, 1) },
    { k: "52w range", v: stats.low_52w && stats.high_52w ? `${fmtNum(stats.low_52w)}–${fmtNum(stats.high_52w)}` : "—" },
    { k: "Beta", v: fmtNum(stats.beta, 2) },
    { k: "Mean target", v: fmtMoney(pt.mean) },
  ]);
}

// Fund facts come from yfinance as fractions (0.0009 = 0.09%).
function pct(v) {
  return v == null || Number.isNaN(v) ? "—" : (v * 100).toFixed(2).replace(/\.?0+$/, "") + "%";
}

function issuerLink(name, symbol) {
  // Link the issuer to the specific fund's page (Yahoo Finance quote).
  return el("a", { class: "tile-link", target: "_blank", rel: "noopener",
    href: `https://finance.yahoo.com/quote/${encodeURIComponent(symbol)}`,
    title: "Open the fund page" }, name);
}

function etfTiles(stats, etf, symbol) {
  return tiles([
    { k: "Price / NAV", v: fmtMoney(stats.current_price) },
    { k: "AUM", v: etf.total_assets_bn != null ? "$" + fmtNum(etf.total_assets_bn, 2) + "B" : "—" },
    { k: "Expense ratio", v: pct(etf.expense_ratio) },
    { k: "Distribution yield", v: pct(etf.distribution_yield) },
    { k: "YTD return", v: pct(etf.ytd_return), cls: deltaCls(etf.ytd_return) },
    { k: "52w range", v: stats.low_52w && stats.high_52w ? `${fmtNum(stats.low_52w)}–${fmtNum(stats.high_52w)}` : "—" },
    etf.category ? { k: "Category", v: etf.category } : null,
    etf.fund_family ? { k: "Issuer", v: issuerLink(etf.fund_family, symbol) } : null,
  ]);
}

function titleCase(s) { return (s || "").replace(/\b\w/g, (c) => c.toUpperCase()); }

function sentimentTiles(s) {
  const pc = s.put_call_oi_ratio;
  const items = [
    { k: "Fear & Greed", v: s.fear_greed_score != null ? `${fmtNum(s.fear_greed_score, 0)} / 100` : "—",
      sub: s.fear_greed_rating ? `${titleCase(s.fear_greed_rating)} · market-wide` : "market-wide index",
      title: "CNN Fear & Greed Index — overall U.S. market mood, not stock-specific. 0 = extreme fear, 50 = neutral, 100 = extreme greed." },
    { k: "Retail bullish", v: s.stocktwits_bullish_pct != null ? fmtNum(s.stocktwits_bullish_pct, 0) + "%" : "—",
      sub: "of Stocktwits posts", title: "Share of labelled Stocktwits messages tagged bullish (vs bearish) for this ticker." },
    { k: "Put/Call OI", v: fmtNum(pc, 2),
      sub: pc == null ? "" : pc > 1 ? "bearish tilt" : pc < 1 ? "bullish tilt" : "balanced",
      title: "Open-interest put/call ratio. Above 1 = more puts (hedging / bearish); below 1 = more calls (bullish)." },
    { k: "Short % float", v: s.short_pct_of_float != null ? fmtNum(s.short_pct_of_float, 1) + "%" : "—",
      sub: "of shares shorted", title: "Shares sold short as a percent of the tradable float. Higher = more bearish bets (and squeeze potential)." },
    { k: "Search momentum", v: s.search_momentum_pct != null ? (s.search_momentum_pct >= 0 ? "+" : "") + fmtNum(s.search_momentum_pct, 0) + "%" : "—",
      cls: deltaCls(s.search_momentum_pct), sub: "vs 3-month avg",
      title: "Google search interest for the ticker versus its trailing 3-month average. A spike often precedes volatility." },
  ];
  return el("div", { class: "panel" },
    el("div", { class: "panel-head" }, el("h3", {}, "Sentiment & positioning")),
    el("p", { class: "panel-sub" }, "Crowd mood and options/short positioning. Hover any metric for what it means."),
    tiles(items));
}

function peersTable(peers) {
  const head = el("tr", {}, ["Symbol", "Mkt cap", "P/E", "Fwd P/E", "Rev gr%", "Op mgn%"].map((h) => el("th", {}, h)));
  const rows = peers.map((p) => el("tr", { class: p.is_subject ? "subject" : "" },
    el("td", {}, p.symbol), el("td", {}, fmtMoney((p.market_cap_b || 0) * 1e9)),
    el("td", {}, fmtNum(p.pe_ttm, 1)), el("td", {}, fmtNum(p.fwd_pe, 1)),
    el("td", {}, p.revenue_growth_pct != null ? fmtNum(p.revenue_growth_pct, 1) : "—"),
    el("td", {}, p.operating_margin_pct != null ? fmtNum(p.operating_margin_pct, 1) : "—")));
  return el("div", { class: "panel" }, el("h3", {}, "Peer comparison"),
    el("div", { style: "margin-top:12px" },
      el("table", { class: "peers" }, el("thead", {}, head), el("tbody", {}, rows))));
}

function panel(title, builder, data) {
  const canvas = el("canvas");
  const p = el("div", { class: "panel" }, el("h3", {}, title), el("div", { style: "margin-top:12px" }, canvas));
  queueMicrotask(() => { try { charts.push(builder(canvas, data)); } catch (_) {} });
  return p;
}

/* ── Chart.js configs (read theme() live so dark/light both look right) ───── */

function priceChart(canvas, points) {
  const t = theme();
  const ctx = canvas.getContext("2d");
  const grad = ctx.createLinearGradient(0, 0, 0, 240);
  grad.addColorStop(0, t.accent + "33"); grad.addColorStop(1, t.accent + "00");
  return new Chart(canvas, {
    type: "line",
    data: { labels: points.map((p) => p.date), datasets: [{
      data: points.map((p) => p.close), borderColor: t.accent, backgroundColor: grad,
      fill: true, tension: .25, pointRadius: 0, borderWidth: 2 }] },
    options: baseOpts({ x: { ticks: { maxTicksLimit: 6 } } }),
  });
}

function revenueChart(canvas, rev) {
  const t = theme();
  const labels = Object.keys(rev).sort();
  return new Chart(canvas, {
    type: "bar",
    data: { labels, datasets: [{ data: labels.map((l) => rev[l]), backgroundColor: t.accent, borderRadius: 4, maxBarThickness: 46 }] },
    options: baseOpts({ y: { ticks: { callback: (v) => "$" + fmtCompact(v) + "M" } } }),
  });
}

function ratingChart(canvas, c) {
  const t = theme();
  return new Chart(canvas, {
    type: "doughnut",
    data: { labels: ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"], datasets: [{
      data: [c.strong_buy, c.buy, c.hold, c.sell, c.strong_sell].map((x) => x || 0),
      backgroundColor: t.ratings, borderWidth: 2, borderColor: t.surface }] },
    options: { responsive: true, cutout: "62%", plugins: { legend: { position: "right" } } },
  });
}

function valuationChart(canvas, scen) {
  const t = theme();
  const color = (s) => /bull/i.test(s) ? t.pos : /bear/i.test(s) ? t.neg : t.accent;
  return new Chart(canvas, {
    type: "bar",
    data: { labels: scen.map((s) => s.scenario), datasets: [{
      data: scen.map((s) => s.intrinsic_per_share), backgroundColor: scen.map((s) => color(s.scenario)), borderRadius: 4, maxBarThickness: 64 }] },
    options: baseOpts({ y: { ticks: { callback: (v) => "$" + fmtNum(v, 0) } } }),
  });
}

function sectorChart(canvas, sectors) {
  const t = theme();
  const labels = Object.keys(sectors);
  return new Chart(canvas, {
    type: "doughnut",
    data: { labels, datasets: [{ data: labels.map((l) => sectors[l]),
      backgroundColor: labels.map((_, i) => t.sectors[i % t.sectors.length]), borderWidth: 2, borderColor: t.surface }] },
    options: { responsive: true, cutout: "60%", plugins: { legend: { position: "right", labels: { boxWidth: 10, font: { size: 11 } } } } },
  });
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

function sumCounts(c) {
  return ["strong_buy", "buy", "hold", "sell", "strong_sell"].reduce((a, k) => a + (c[k] || 0), 0);
}

// Re-theme charts when the user toggles dark/light (rebuild from cached data).
window.addEventListener("themechange", () => {
  if (last && $("#view-report")?.classList.contains("is-active")) buildDashboard();
});
