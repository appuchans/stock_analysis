// Router + shell chrome (theme toggle, mobile drawer, refresh) — no build step.
import { $, $$ } from "./util.js";
import { initAnalyzeForm, refreshSymbol } from "./analyze.js";
import { renderReport } from "./dashboard.js";
import { loadHistory } from "./history.js";

const VIEWS = { new: "view-new", report: "view-report", history: "view-history" };

function showView(name) {
  for (const id of Object.values(VIEWS)) $("#" + id)?.classList.remove("is-active");
  $("#" + (VIEWS[name] || VIEWS.new))?.classList.add("is-active");
  $$(".sb-link").forEach((a) => a.classList.toggle("is-active", a.dataset.nav === name));
  $("#app")?.classList.remove("sb-open"); // close mobile drawer on navigation
}

function route() {
  const [view, arg] = (location.hash || "#/new").slice(2).split("/");
  if (view === "report" && arg) { showView("report"); renderReport(arg); }
  else if (view === "history") { showView("history"); loadHistory(); }
  else showView("new");
}

/* ── Theme ──────────────────────────────────────────────────────────────── */
function syncThemeUI() {
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  $(".ic-sun")?.classList.toggle("hidden", dark);
  $(".ic-moon")?.classList.toggle("hidden", !dark);
  const lbl = $(".tt-label");
  if (lbl) lbl.textContent = dark ? "Light mode" : "Dark mode";
}
function toggleTheme() {
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  const next = dark ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("theme", next);
  syncThemeUI();
  window.dispatchEvent(new CustomEvent("themechange"));
}

function initChrome() {
  $$("[data-back]").forEach((b) => b.addEventListener("click", () => (location.hash = "#/history")));
  $$(".tab").forEach((t) =>
    t.addEventListener("click", () => {
      $$(".tab").forEach((x) => x.classList.toggle("is-active", x === t));
      $("#tab-overview").classList.toggle("hidden", t.dataset.tab !== "overview");
      $("#tab-full").classList.toggle("hidden", t.dataset.tab !== "full");
    })
  );
  $("#theme-toggle")?.addEventListener("click", toggleTheme);
  $("#sb-burger")?.addEventListener("click", () => $("#app").classList.toggle("sb-open"));
  $("#report-refresh")?.addEventListener("click", (e) => {
    const btn = e.currentTarget;
    if (btn.dataset.symbol) refreshSymbol(btn.dataset.symbol, btn.dataset.asset);
  });
  syncThemeUI();
}

window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", () => {
  initChrome();
  initAnalyzeForm();
  route();
});
