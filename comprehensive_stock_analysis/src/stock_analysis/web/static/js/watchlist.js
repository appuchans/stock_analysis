// Watchlist: add/remove symbols, see latest rec + freshness, analyze one or all.
import { $, el, fetchJSON, fmtNum, fmtMoney, badgeClass, navigate, sparkline, theme, timeAgo } from "./util.js";

let watchlist = [];
let historyBySymbol = {};
let pollTimer = null;

export async function loadWatchlist() {
  const body = $("#watchlist-body");
  const empty = $("#watchlist-empty");
  empty.classList.add("hidden");
  body.innerHTML = "";
  for (let i = 0; i < 3; i++) body.append(el("tr", {}, el("td", { colspan: "7" }, el("div", { class: "skeleton sk-row" }))));

  const [wl, hist] = await Promise.all([
    fetchJSON("/api/watchlist").catch(() => ({ items: [] })),
    fetchJSON("/api/history").catch(() => ({ items: [] })),
  ]);
  watchlist = wl.items || [];
  historyBySymbol = Object.fromEntries((hist.items || []).map((it) => [it.symbol, it]));

  $("#watchlist-form").onsubmit = onAdd;
  $("#watchlist-analyze-all").onclick = onAnalyzeAll;
  render();
  empty.classList.toggle("hidden", watchlist.length > 0);
  // Only start polling if something is actually in flight — otherwise this
  // would recurse forever (tick finds nothing active -> reloads -> polls again).
  if (await refreshJobChips()) ensurePolling();
}

function render() {
  const body = $("#watchlist-body");
  body.innerHTML = "";
  watchlist.forEach((w) => body.append(row(w)));
}

async function onAdd(ev) {
  ev.preventDefault();
  const symbolInput = $("#watchlist-symbol");
  const notesInput = $("#watchlist-notes");
  const symbol = symbolInput.value.trim().toUpperCase();
  if (!symbol) return;
  const btn = $("#watchlist-add-btn");
  btn.disabled = true;
  try {
    await fetchJSON("/api/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, notes: notesInput.value.trim() }),
    });
    symbolInput.value = "";
    notesInput.value = "";
    await loadWatchlist();
  } catch (err) {
    alert(err.message);
  } finally {
    btn.disabled = false;
  }
}

async function onRemove(symbol) {
  try {
    await fetchJSON(`/api/watchlist/${symbol}`, { method: "DELETE" });
    await loadWatchlist();
  } catch (err) {
    alert(err.message);
  }
}

async function onAnalyzeOne(symbol) {
  try {
    await fetchJSON("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, depth: "standard", asset_type: "auto", use_cache: true }),
    });
    if (await refreshJobChips()) ensurePolling();
  } catch (err) {
    alert(err.message);
  }
}

async function onAnalyzeAll() {
  const btn = $("#watchlist-analyze-all");
  btn.disabled = true;
  try {
    await fetchJSON("/api/watchlist/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ depth: "standard", use_cache: true }),
    });
    if (await refreshJobChips()) ensurePolling();
  } catch (err) {
    alert(err.message);
  } finally {
    btn.disabled = false;
  }
}

// Update each row's status chip from the live queue. Returns whether anything
// is still queued/running, so callers know whether polling is worth starting.
async function refreshJobChips() {
  let queue;
  try {
    queue = await fetchJSON("/api/jobs");
  } catch (_) {
    return false;
  }
  const bySymbol = Object.fromEntries((queue.items || []).map((j) => [j.symbol, j]));
  let anyActive = false;
  watchlist.forEach((w) => {
    const job = bySymbol[w.symbol];
    const chip = $(`.wl-status[data-symbol="${w.symbol}"]`);
    if (!chip) return;
    if (job) {
      anyActive = true;
      chip.textContent = job.state === "running" ? "Running…" : "Queued";
      chip.classList.remove("hidden");
    } else {
      chip.classList.add("hidden");
    }
  });
  return anyActive;
}

// Poll the queue while any watchlist symbol has an in-flight job. Stops
// itself the moment nothing is active, then does exactly one loadWatchlist()
// to pick up new recs/sparklines — that reload does NOT restart polling
// (loadWatchlist only calls ensurePolling when refreshJobChips finds work),
// so this never recurses into an idle refresh loop.
function ensurePolling() {
  if (pollTimer) return; // already running
  pollTimer = setInterval(async () => {
    const stillActive = await refreshJobChips();
    if (!stillActive) {
      clearInterval(pollTimer);
      pollTimer = null;
      loadWatchlist();
    }
  }, 1500);
}

function lastAnalyzedLabel(iso) {
  const ago = timeAgo(iso);
  return ago ? ago.charAt(0).toUpperCase() + ago.slice(1) : "Never analyzed";
}

function freshnessClass(iso) {
  if (!iso) return "stale";
  const hrs = (Date.now() - new Date(iso.replace(" ", "T")).getTime()) / 3600000;
  if (hrs < 24) return "fresh";
  if (hrs < 24 * 3) return "aging";
  return "stale";
}

function row(w) {
  const h = historyBySymbol[w.symbol];
  const tr = el("tr", { class: "wl-row" });
  if (h && h.has_html) {
    tr.classList.add("clickable");
    tr.addEventListener("click", (e) => {
      if (!e.target.closest("button")) navigate(`#/report/${w.symbol}`);
    });
  }

  tr.append(el("td", {}, el("div", { class: "wl-sym" }, w.symbol), w.notes ? el("div", { class: "wl-notes" }, w.notes) : null));

  if (h) {
    tr.append(el("td", {}, h.recommendation
      ? el("span", { class: "rec-badge " + badgeClass(h.recommendation) }, h.recommendation.toUpperCase())
      : el("span", { class: "muted" }, "—")));
    tr.append(el("td", { class: "num" }, h.confidence != null ? fmtNum(h.confidence * 100, 0) + "%" : "—"));
    tr.append(el("td", { class: "num" }, fmtMoney(h.current_price)));
    const sparkCell = el("td", {});
    if ((h.spark || []).length >= 2) {
      const cv = el("canvas", { class: "wl-spark" });
      sparkCell.append(cv);
      const up = h.spark[h.spark.length - 1] >= h.spark[0];
      queueMicrotask(() => sparkline(cv, h.spark, up ? theme().pos : theme().neg));
    } else {
      sparkCell.append(el("span", { class: "muted" }, "—"));
    }
    tr.append(sparkCell);
    tr.append(el("td", {}, el("span", { class: "freshness " + freshnessClass(h.mtime) }, lastAnalyzedLabel(h.mtime))));
  } else {
    tr.append(el("td", { colspan: "4", class: "muted" }, "Not yet analyzed"));
    tr.append(el("td", {}, el("span", { class: "freshness stale" }, "Never analyzed")));
  }

  tr.append(el("td", { class: "wl-actions" },
    el("span", { class: "chip wl-status hidden", "data-symbol": w.symbol }),
    el("button", { class: "btn btn-ghost btn-sm", onclick: () => onAnalyzeOne(w.symbol) }, "Analyze"),
    el("button", { class: "btn btn-ghost btn-sm btn-danger", onclick: () => onRemove(w.symbol) }, "Remove")));

  return tr;
}
