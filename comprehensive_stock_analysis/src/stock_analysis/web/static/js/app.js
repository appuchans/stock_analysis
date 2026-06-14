// Router + view orchestration (hash-based, no build step).
import { $, $$ } from "./util.js";
import { initAnalyzeForm } from "./analyze.js";
import { renderReport } from "./dashboard.js";
import { loadHistory } from "./history.js";

const VIEWS = { new: "view-new", report: "view-report", history: "view-history" };

function showView(name) {
  for (const id of Object.values(VIEWS)) $("#" + id)?.classList.remove("is-active");
  $("#" + (VIEWS[name] || VIEWS.new))?.classList.add("is-active");
  $$(".nav-link").forEach((a) => a.classList.toggle("is-active", a.dataset.nav === name));
}

function route() {
  const parts = (location.hash || "#/new").slice(2).split("/"); // ["report","AAPL"]
  const [view, arg] = parts;
  if (view === "report" && arg) {
    showView("report");
    renderReport(arg);
  } else if (view === "history") {
    showView("history");
    loadHistory();
  } else {
    showView("new");
  }
}

function initChrome() {
  $$("[data-back]").forEach((b) => b.addEventListener("click", () => navigate("#/history")));
  $$(".tab").forEach((t) =>
    t.addEventListener("click", () => {
      $$(".tab").forEach((x) => x.classList.toggle("is-active", x === t));
      $("#tab-overview").classList.toggle("hidden", t.dataset.tab !== "overview");
      $("#tab-full").classList.toggle("hidden", t.dataset.tab !== "full");
    })
  );
}

window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", () => {
  initChrome();
  initAnalyzeForm();
  route();
});
