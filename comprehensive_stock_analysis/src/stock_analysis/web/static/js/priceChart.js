// Shared multi-symbol price chart — used by the report Overview panel and the
// Compare page. A single series renders as a plain price line (unchanged
// look from before); two or more render indexed to "% change from the first
// bar" so symbols at different price levels are comparable on one axis,
// primary solid + comparisons dashed, with a legend (mirrors portfolio.js's
// benchmarkChart styling).
import { theme } from "./util.js";

const COMPARE_COLORS = ["faint", "warn", "pos", "neg"];

function baseOpts(t, extraScales = {}) {
  return {
    responsive: true,
    scales: {
      x: { grid: { display: false }, border: { color: t.grid }, ticks: { maxTicksLimit: 6 }, ...(extraScales.x || {}) },
      y: { grid: { color: t.grid }, border: { display: false }, ...(extraScales.y || {}) },
    },
  };
}

export function renderPriceChart(canvas, seriesList) {
  const t = theme();
  const ctx = canvas.getContext("2d");

  if (seriesList.length <= 1) {
    const s = seriesList[0] || { bars: [] };
    const grad = ctx.createLinearGradient(0, 0, 0, 240);
    grad.addColorStop(0, t.accent + "33");
    grad.addColorStop(1, t.accent + "00");
    return new Chart(canvas, {
      type: "line",
      data: {
        labels: s.bars.map((b) => b.date),
        datasets: [{
          data: s.bars.map((b) => b.close), borderColor: t.accent, backgroundColor: grad,
          fill: true, tension: .25, pointRadius: 0, borderWidth: 2,
        }],
      },
      options: { ...baseOpts(t), plugins: { legend: { display: false } } },
    });
  }

  const labels = seriesList[0].bars.map((b) => b.date);
  const datasets = seriesList.map((s, i) => {
    const first = s.bars[0] ? s.bars[0].close : null;
    const indexed = s.bars.map((b) => (first ? ((b.close - first) / first) * 100 : 0));
    return {
      label: s.symbol,
      data: indexed,
      borderColor: i === 0 ? t.accent : t[COMPARE_COLORS[(i - 1) % COMPARE_COLORS.length]],
      borderDash: i === 0 ? [] : [4, 3],
      pointRadius: 0, borderWidth: 2, tension: .2,
    };
  });
  return new Chart(canvas, {
    type: "line",
    data: { labels, datasets },
    options: {
      ...baseOpts(t, { y: { ticks: { callback: (v) => v + "%" } } }),
      plugins: { legend: { display: true, position: "top", labels: { boxWidth: 10 } } },
    },
  });
}
