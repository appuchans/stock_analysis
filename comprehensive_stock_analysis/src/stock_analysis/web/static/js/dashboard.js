// Report view: embed the full HTML report + build the interactive Overview
// dashboard from chart_data.json using Chart.js, themed to match light/dark.
import { $, $$, el, fetchJSON, fmtNum, fmtMoney, fmtCompact, badgeClass, theme, timeAgo, makeSortable } from "./util.js";
import { renderPriceChart } from "./priceChart.js";
import { periodSelector, symbolChipInput } from "./chartControls.js";

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
  // What the company is and where the stock stands, before any chart. Reading
  // six numeric tiles and a price line should not be the only way to find out
  // what you are looking at.
  const summary = summaryPanel(company, chart, isEtf, rec);
  if (summary) host.append(summary);
  host.append(isEtf
    ? etfTiles(chart.key_stats || {}, chart.etf_profile || {}, symbol)
    : keyTiles(chart.key_stats || {}, chart.analyst || {}));

  const grid = el("div", { class: "grid-2" });
  host.append(grid);
  if ((chart.price_history || []).length) grid.append(priceChartPanel(symbol, chart.price_history));
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

// ── Summary ────────────────────────────────────────────────────────────────
// Company identity + a plain-language read on where the stock stands, above
// the charts. Every part is conditional: with no description or no analyst
// coverage the panel shrinks rather than showing empty scaffolding, and it is
// omitted entirely when there is nothing worth saying.
function summaryPanel(company, chart, isEtf, rec) {
  const facts = companyFacts(company, chart, isEtf);
  // Prefer the advisor's own two sentences — it can say *why* a stock moved
  // ("stumbled after a Q2 miss and softer guidance"), which no amount of
  // string assembly over price series can. The generated sentences stay as
  // the fallback so a run whose recommendation stage failed still opens with
  // something readable rather than nothing.
  const written = (rec && typeof rec.summary === "string" && rec.summary.trim())
    ? [{ a: rec.summary.trim() }]
    : null;
  const points = written || stockSummaryPoints(chart, isEtf);
  const description = (company.description || "").trim();
  if (!description && !facts.length && !points.length) return null;

  const body = el("div", { class: "summary-body" });

  if (description) {
    // Long yfinance summaries run several hundred words; clamp with CSS and
    // let the user expand, so the charts stay above the fold.
    const p = el("p", { class: "summary-desc is-clamped" }, description);
    body.append(p);
    if (description.length > 320) {
      const toggle = el("button", { class: "btn btn-ghost btn-sm summary-more" }, "Show more");
      toggle.addEventListener("click", () => {
        const clamped = p.classList.toggle("is-clamped");
        toggle.textContent = clamped ? "Show more" : "Show less";
      });
      body.append(toggle);
    }
  }

  if (facts.length) {
    body.append(el("div", { class: "summary-facts" },
      facts.map(([k, v]) => el("div", { class: "summary-fact" },
        el("span", { class: "k" }, k),
        v && v.nodeType ? v : el("span", { class: "v" }, v)))));
  }

  if (points.length) {
    // The two questions these paragraphs answer ("how is it doing", "anything
    // to keep in mind") shape the content but are not shown — the prose reads
    // as the answer, not as a FAQ.
    body.append(el("div", { class: "summary-read" },
      points.map(({ a }) => el("p", { class: "summary-para" }, a))));
  }

  return el("div", { class: "panel summary-panel" },
    el("h3", {}, isEtf ? "About this fund" : "About the company"),
    body);
}

function companyFacts(company, chart, isEtf) {
  const out = [];
  const line = [company.sector, company.industry].filter(Boolean).join(" · ");
  if (line) out.push(["Sector", line]);
  if (company.headquarters || company.country) {
    out.push(["Headquarters", [company.headquarters, company.country].filter(Boolean).join(", ")]);
  }
  if (company.employees) out.push(["Employees", fmtCompact(company.employees)]);
  if (company.ceo) out.push(["CEO", company.ceo]);
  if (company.exchange) out.push(["Listed on", company.exchange]);
  if (company.website) {
    // rel=noopener: the report is user-supplied content reached from a fetch.
    out.push(["Website", el("a", {
      class: "v", href: company.website, target: "_blank", rel: "noopener noreferrer",
    }, company.website.replace(/^https?:\/\//, ""))]);
  }
  return out;
}

// Qualitative characterisations, not a re-reading of the tiles and charts —
// those already show the numbers. Each line says what the data *means*: where
// the stock sits in its own recent range, how one-sided analyst coverage is,
// whether the price sits inside or outside the DCF band, how positioning
// leans. Figures appear only where no chart carries them (e.g. earnings
// timing). Deterministic and LLM-free, so it survives a failed recommendation
// stage.
// Plain-English opening: what the stock has actually done, whether that was
// the company or just the market, and what has been in the news. Written the
// way you would answer "how's it doing?" out loud.
//
// Explicitly NOT here: DCF bands, short interest, put/call ratios, target
// dispersion. Those are analysis, and they belong further down the report
// where a reader has asked for them — not as the first thing on the page.
function stockSummaryPoints(chart, isEtf) {
  const stats = chart.key_stats || {};
  const noun = isEtf ? "The fund" : "The stock";
  const price = stats.current_price;
  const out = [];

  const first = [];
  const move = marketRelativePhrase(chart, price, noun);
  if (move) first.push(move);
  const range = rangeSentence(price, stats.low_52w, stats.high_52w, noun);
  if (range) first.push(range);
  if (first.length) out.push({ a: first.join(" ") });

  const news = newsSentence(chart.news || [], chart.symbol, (chart.company || {}).name);
  const weeks = weeksUntil((chart.catalysts || {}).next_earnings_date);
  const second = [];
  if (news) second.push(news);
  if (weeks != null && weeks >= 0) {
    second.push(weeks <= 1 ? "Earnings are due within the week."
      : weeks <= 4 ? `Earnings are due in about ${weeks} weeks.`
      : `Earnings are not due for another ${weeks} weeks.`);
  }
  if (second.length) out.push({ a: second.join(" ") });
  return out;
}

// The whole point of a benchmark: "down 8%" means nothing until you know the
// market was down 10%.
function marketRelativePhrase(chart, price, noun) {
  const closes = (chart.price_history || []).map((p) => p && p.close).filter((c) => typeof c === "number");
  if (closes.length < 8 || !price) return "";
  const chg = (series, n) => {
    const a = series[Math.max(0, series.length - 1 - n)];
    const last = series[series.length - 1];
    return a && last ? ((last - a) / a) * 100 : null;
  };
  const withPrice = closes.slice(0, -1).concat(price);
  const m6 = chg(withPrice, 26);
  if (m6 == null) return "";

  const dir = m6 > 15 ? "risen strongly" : m6 > 3 ? "risen" : m6 < -15 ? "fallen sharply" : m6 < -3 ? "fallen" : "been broadly flat";
  let s = `${noun} has ${dir} over the past six months`;

  const bench = ((chart.benchmark || {}).history || []).map((p) => p && p.close).filter((c) => typeof c === "number");
  const b6 = bench.length >= 27 ? chg(bench, 26) : null;
  if (b6 != null) {
    const gap = m6 - b6;
    const raw = (chart.benchmark || {}).symbol || "the market";
    const name = raw === "the market" ? raw : `the ${raw}`;
    s += Math.abs(gap) < 3 ? `, broadly in line with ${name}`
      : gap > 0 ? `, doing better than ${name}`
      : `, lagging ${name}`;
  }
  return s + ".";
}

function rangeSentence(price, low, high, noun) {
  if (!price || !low || !high || high <= low) return "";
  const pos = (price - low) / (high - low);
  const where = pos >= 0.9 ? "close to its highest point of the past year"
    : pos >= 0.66 ? "nearer the top of its range for the past year"
    : pos >= 0.33 ? "around the middle of its range for the past year"
    : pos >= 0.1 ? "nearer the bottom of its range for the past year"
    : "close to its lowest point of the past year";
  return `That leaves it ${where}.`;
}

// The actual reason a reader opens a report: what happened.
//
// Yahoo's feed mixes company stories with market-wide wire copy ("Stock Market
// Today: Dow Falls…"). Taking the newest item surfaced that generic noise over
// the company's own $240M deal, so prefer headlines that actually name the
// company and fall back to the raw feed only when none do.
function newsSentence(news, symbol, companyName) {
  const items = news.filter((n) => n && n.title);
  if (!items.length) return "";

  const needles = [String(symbol || "").toLowerCase()];
  const firstWord = String(companyName || "").split(/[\s,]+/)[0];
  if (firstWord && firstWord.length > 3) needles.push(firstWord.toLowerCase());
  const aboutCompany = items.filter((n) =>
    needles.some((w) => w && n.title.toLowerCase().includes(w)));

  const chosen = (aboutCompany.length ? aboutCompany : items).slice(0, 2);
  const cite = (n) => `“${n.title}”` + (n.publisher ? ` (${n.publisher})` : "");
  let s = `In the news: ${cite(chosen[0])}.`;
  if (chosen[1]) s += ` Also: ${cite(chosen[1])}.`;
  return s;
}

function weeksUntil(iso) {
  if (!iso) return null;
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return null;
  return Math.round((then - Date.now()) / (7 * 24 * 3600 * 1000));
}

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

function peerRow(p) {
  return el("tr", { class: p.is_subject ? "subject" : "" },
    el("td", {}, p.symbol), el("td", {}, fmtMoney((p.market_cap_b || 0) * 1e9)),
    el("td", {}, fmtNum(p.pe_ttm, 1)), el("td", {}, fmtNum(p.fwd_pe, 1)),
    el("td", {}, p.revenue_growth_pct != null ? fmtNum(p.revenue_growth_pct, 1) : "—"),
    el("td", {}, p.operating_margin_pct != null ? fmtNum(p.operating_margin_pct, 1) : "—"));
}

function peersTable(peers) {
  const head = el("tr", {}, ["Symbol", "Mkt cap", "P/E", "Fwd P/E", "Rev gr%", "Op mgn%"].map((h) => el("th", {}, h)));
  const thead = el("thead", {}, head);
  const tbody = el("tbody", {});
  const table = el("table", { class: "peers" }, thead, tbody);
  makeSortable(thead, tbody, peers, peerRow, [
    (p) => p.symbol, (p) => p.market_cap_b, (p) => p.pe_ttm, (p) => p.fwd_pe,
    (p) => p.revenue_growth_pct, (p) => p.operating_margin_pct,
  ]);
  return el("div", { class: "panel" }, el("h3", {}, "Peer comparison"),
    el("div", { style: "margin-top:12px" }, table));
}

// Live-fetched, period + comparison-symbol price chart. Falls back to the
// pre-baked chart_data.json series (single line, 1y weekly) if the live
// endpoint is unreachable, so the panel never renders empty.
function priceChartPanel(symbol, fallbackHistory) {
  const state = { period: "1y", compareSymbols: [] };
  const canvas = el("canvas");
  const chartHost = el("div", { style: "margin-top:12px" }, canvas);
  let chartInstance = null;

  function setChart(seriesList) {
    if (chartInstance) {
      try { chartInstance.destroy(); } catch (_) { /* noop */ }
      const idx = charts.indexOf(chartInstance);
      if (idx >= 0) charts.splice(idx, 1);
    }
    chartInstance = renderPriceChart(canvas, seriesList);
    charts.push(chartInstance);
  }

  async function refetch() {
    const compareParam = state.compareSymbols.length ? `&compare=${state.compareSymbols.join(",")}` : "";
    try {
      const data = await fetchJSON(`/api/reports/${symbol}/prices?period=${state.period}${compareParam}`);
      setChart(data.series.length ? data.series : [{ symbol, bars: fallbackHistory }]);
    } catch (_) {
      setChart([{ symbol, bars: fallbackHistory }]);
    }
  }

  const controls = el("div", { class: "panel-toolbar" },
    periodSelector(state.period, (p) => { state.period = p; refetch(); }),
    symbolChipInput({
      getSymbols: () => state.compareSymbols,
      onChange: (syms) => { state.compareSymbols = syms; refetch(); },
      placeholder: "Compare (e.g. MSFT)",
    }));

  queueMicrotask(refetch);
  return el("div", { class: "panel" }, el("h3", {}, "Price"), controls, chartHost);
}

function panel(title, builder, data) {
  const canvas = el("canvas");
  const p = el("div", { class: "panel" }, el("h3", {}, title), el("div", { style: "margin-top:12px" }, canvas));
  queueMicrotask(() => { try { charts.push(builder(canvas, data)); } catch (_) {} });
  return p;
}

/* ── Chart.js configs (read theme() live so dark/light both look right) ───── */

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
