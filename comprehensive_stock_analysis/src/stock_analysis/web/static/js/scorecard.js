// Scorecard: recommendations graded against realized forward returns.
import { $, el, fetchJSON } from "./util.js";

function fmtRet(v) {
  return typeof v === "number" ? `${v > 0 ? "+" : ""}${v.toFixed(1)}%` : "—";
}

export async function loadScorecard() {
  const body = $("#scorecard-body");
  const empty = $("#scorecard-empty");
  empty.classList.add("hidden");
  body.innerHTML = "";
  let data;
  try { data = await fetchJSON("/api/scorecard"); } catch (_) { data = null; }
  const s = data?.summary;
  if (!data || !s.total) { empty.classList.remove("hidden"); return; }

  const sum = $("#scorecard-summary");
  sum.innerHTML = "";
  sum.append(
    el("div", { class: "stat" },
      el("div", { class: "label" }, "Graded calls"),
      el("div", { class: "value" }, `${s.graded}/${s.total}`)),
    el("div", { class: "stat" },
      el("div", { class: "label" }, "Directionally correct"),
      el("div", { class: "value" }, String(s.correct))),
    el("div", { class: "stat" },
      el("div", { class: "label" }, "Accuracy"),
      el("div", { class: "value" }, s.accuracy_pct === null ? "—" : `${s.accuracy_pct}%`)),
  );

  const tbl = el("table");
  tbl.append(el("tr", {},
    el("th", {}, "Symbol"), el("th", {}, "Date"), el("th", {}, "Call"),
    el("th", {}, "+30d"), el("th", {}, "+60d"), el("th", {}, "+90d"),
    el("th", {}, "Verdict")));
  for (const it of data.items) {
    const ret = (h) => it.returns?.[String(h)];
    const verdict = it.grade === "correct" ? "✓"
      : it.grade === "wrong" ? "✗" : "pending";
    tbl.append(el("tr", {},
      el("td", {}, el("a", { href: `#/report/${it.symbol}` }, it.symbol)),
      el("td", {}, (it.recorded_at || "").slice(0, 10)),
      el("td", {}, it.recommendation || "—"),
      el("td", {}, fmtRet(ret(30))),
      el("td", {}, fmtRet(ret(60))),
      el("td", {}, fmtRet(ret(90))),
      el("td", {}, verdict),
    ));
  }
  body.append(tbl);
}
