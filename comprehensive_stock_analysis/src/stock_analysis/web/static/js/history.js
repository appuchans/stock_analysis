// History gallery: cards for every past report, click → report view.
import { $, el, fetchJSON, fmtNum, fmtMoney, badgeClass, navigate } from "./util.js";

let items = [];

export async function loadHistory() {
  const grid = $("#history-grid");
  const empty = $("#history-empty");
  grid.innerHTML = "";
  try {
    const data = await fetchJSON("/api/history");
    items = data.items || [];
  } catch (_) {
    items = [];
  }
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

function card(it) {
  const upside = it.target_price && it.current_price
    ? ((it.target_price - it.current_price) / it.current_price) * 100 : null;
  return el("div", { class: "report-card", onclick: () => navigate(`#/report/${it.symbol}`) },
    el("div", { class: "rc-head" },
      el("span", { class: "rc-sym" }, it.symbol),
      it.recommendation
        ? el("span", { class: "rec-badge " + badgeClass(it.recommendation) }, it.recommendation.toUpperCase())
        : null,
    ),
    el("div", { class: "rc-name" }, it.name || it.sector || "—"),
    row("Price", fmtMoney(it.current_price)),
    row("Target", fmtMoney(it.target_price)),
    upside !== null ? row("Upside", (upside >= 0 ? "+" : "") + fmtNum(upside, 1) + "%") : null,
    row("P/E", fmtNum(it.pe_ratio, 1)),
    el("div", { class: "rc-foot" }, "Updated " + (it.mtime ? it.mtime.replace("T", " ") : "—")),
  );
}

const row = (lbl, val) =>
  el("div", { class: "rc-row" }, el("span", { class: "lbl" }, lbl), el("span", {}, val));
