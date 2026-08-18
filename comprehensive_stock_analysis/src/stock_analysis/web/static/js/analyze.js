// New Analysis: form submit + refresh, then poll job status and drive progress.
//
// Runs are serialized server-side by a single-worker JobManager: a second
// submission while one is active is QUEUED (FIFO), never rejected and never
// cancelling the run in flight. This module must reflect that — submitting a
// refresh while an analysis is running previously wiped the progress card and
// dropped the in-flight job's polling, which read as "the first analysis was
// cancelled" even though it was still running. So the card follows the job the
// server is ACTUALLY running, and everything else the user queued is listed
// beside it. Cancellation happens only when the user clicks Cancel.
import { $, $$, fetchJSON, fmtNum, navigate } from "./util.js";

let polling = null;
// Jobs submitted in this session, in submission order: id → {symbol, state}.
const watched = new Map();
// The job whose report we auto-open on completion (the user's latest intent).
let lastSubmittedId = null;
// The job currently rendered in the progress card (what Cancel targets).
let displayId = null;

export function initAnalyzeForm() {
  const form = $("#analyze-form");
  if (!form) return;
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    startAnalysis({
      symbol: $("#symbol").value.trim().toUpperCase(),
      depth: $("#depth").value,
      asset_type: $("#asset_type").value,
      use_cache: $("#use_cache").checked,
    });
  });
  $("#cancel-btn").addEventListener("click", onCancel);
}

// Re-run an existing report with fresh data (used by History + Report refresh).
// `resume` reuses the specialist stages that already succeeded and re-runs only
// the missing ones — the right behaviour when the previous run died partway,
// since re-paying for finished stages is pure waste.
export function refreshSymbol(symbol, assetType, resume = false) {
  navigate("#/new");
  // let the view switch before showing progress
  setTimeout(() => startAnalysis({
    symbol, depth: "standard", asset_type: assetType || "auto",
    use_cache: false, resume,
  }), 60);
}

export async function startAnalysis(payload) {
  if (!payload.symbol) return;
  const btn = $("#run-btn");
  btn.disabled = true;
  $("#progress-card").classList.remove("hidden");
  $("#progress-error").classList.add("hidden");
  $("#progress-card").scrollIntoView({ behavior: "smooth", block: "nearest" });
  try {
    const { job_id } = await fetchJSON("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    // The server coalesces a duplicate submission onto the existing job, so
    // job_id may be one we are already watching — Map.set keeps that single.
    watched.set(job_id, { symbol: payload.symbol, state: "queued" });
    lastSubmittedId = job_id;
    ensurePolling();
    tick(); // reconcile immediately rather than waiting a full second
  } catch (err) {
    // A full analysis costs real money, so the server refuses a manual re-run
    // of a symbol analyzed recently. Say how recent it is and let the user
    // decide, rather than either refusing outright or silently spending.
    if (err.status === 409) {
      $("#progress-card").classList.add("hidden");
      if (window.confirm(`${err.message}\n\nRe-run anyway?`)) {
        return startAnalysis({ ...payload, force: true });
      }
      navigate(`#/report/${payload.symbol}`);
      return;
    }
    showError(err.message);
  } finally {
    // Re-enabled straight away: more runs may be queued while one is active.
    btn.disabled = false;
  }
}

async function onCancel() {
  // Cancel targets the job on screen — never "whatever was submitted last".
  if (!displayId) return;
  $("#cancel-btn").disabled = true;
  $("#progress-stage").textContent = "Cancelling…";
  try {
    await fetchJSON(`/api/jobs/${displayId}/cancel`, { method: "POST" });
  } catch (_) { /* 409 if already finished — polling reflects final state */ }
}

function showError(msg) {
  const box = $("#progress-error");
  box.textContent = msg;
  box.classList.remove("hidden");
  $("#progress-stage").textContent = "Stopped";
}

function setStepper(progress, state) {
  // 0 data · 1 specialists · 2 synthesis · 3 report
  let active = 0;
  if (progress >= 0.92) active = 3;
  else if (progress >= 0.8) active = 2;
  else if (progress >= 0.1) active = 1;
  const done = state === "completed";
  $$("#stepper .step").forEach((el, i) => {
    el.classList.toggle("done", done || i < active);
    el.classList.toggle("active", !done && i === active);
  });
}

const TERMINAL = ["completed", "failed", "aborted"];

function ensurePolling() {
  if (!polling) polling = setInterval(tick, 1000);
}

function stopPolling() {
  if (polling) { clearInterval(polling); polling = null; }
}

/** Which watched job the card should show: prefer the one actually running. */
function pickDisplayId(activeId) {
  if (activeId && watched.has(activeId)) return activeId;
  // Otherwise the newest watched job that has not finished yet…
  const live = [...watched.entries()].filter(([, j]) => !TERMINAL.includes(j.state));
  if (live.length) return live[live.length - 1][0];
  // …else keep showing the last thing the user asked for.
  return lastSubmittedId;
}

async function tick() {
  if (!watched.size) { stopPolling(); return; }

  // Queue endpoint tells us what the server is really running vs. holding.
  let activeId = null;
  try {
    const q = await fetchJSON("/api/jobs");
    activeId = q.active_id || null;
  } catch (_) { /* transient — fall back to per-job state below */ }

  displayId = pickDisplayId(activeId);
  if (!displayId) { stopPolling(); return; }

  let job;
  try {
    job = await fetchJSON(`/api/jobs/${displayId}`);
  } catch (_) { return; }

  const entry = watched.get(displayId);
  if (entry) entry.state = job.state;
  renderCard(job);

  // Refresh the recorded state of every OTHER watched job so the queue strip
  // and the "is anything still live" checks stay honest.
  await Promise.all([...watched.keys()].filter((id) => id !== displayId).map(async (id) => {
    try {
      const other = await fetchJSON(`/api/jobs/${id}`);
      const w = watched.get(id);
      if (w) { w.state = other.state; w.symbol = other.symbol || w.symbol; }
    } catch (_) { /* leave last known state */ }
  }));

  renderQueue();

  if (TERMINAL.includes(job.state)) {
    $("#cancel-btn").classList.add("hidden");
    $("#progress-activity").classList.add("hidden");
    // Only auto-open the report for the run the user asked for most recently —
    // otherwise an earlier job finishing would yank them off a live run.
    if (job.state === "completed" && job.id === lastSubmittedId) {
      $("#progress-bar").style.width = "100%";
      navigate(`#/report/${job.symbol}`);
    } else if (job.state === "aborted" && job.id === lastSubmittedId) {
      $("#progress-stage").textContent = "Aborted";
      showError("Analysis was cancelled before completing.");
    } else if (job.state === "failed" && job.id === lastSubmittedId) {
      showError(job.error || "Analysis failed.");
    }
    // Drop finished jobs once nothing live remains, so the strip clears.
    const anyLive = [...watched.values()].some((j) => !TERMINAL.includes(j.state));
    if (!anyLive) { stopPolling(); }
  }
}

function renderCard(job) {
  const pct = Math.round((job.progress || 0) * 100);
  $("#progress-symbol").textContent = job.symbol || "";
  $("#progress-name").textContent = job.company_name || "";
  $("#progress-bar").style.width = Math.max(pct, 3) + "%";
  $("#progress-pct").textContent = pct + "%";
  $("#progress-stage").textContent = job.state === "queued" && job.queue_position > 0
    ? `Queued — ${job.queue_position} ahead`
    : (job.stage || job.state);
  $("#progress-tokens").textContent = fmtNum((job.token_usage || {}).total_tokens || 0, 0);
  $("#progress-calls").textContent = job.llm_calls || 0;
  setStepper(job.progress || 0, job.state);

  const act = $("#progress-activity");
  if (job.activity) {
    act.querySelector(".txt").textContent = job.activity;
    act.classList.remove("hidden");
  } else {
    act.classList.add("hidden");
  }

  const cancel = $("#cancel-btn");
  if (TERMINAL.includes(job.state)) {
    cancel.classList.add("hidden");
  } else {
    cancel.classList.remove("hidden");
    cancel.disabled = false;
    // Name the target so Cancel can't be mistaken for "cancel everything".
    cancel.title = `Cancel the ${job.symbol} analysis`;
  }
}

/** Everything the user queued that is not the job on screen. */
function renderQueue() {
  const box = $("#progress-queue");
  if (!box) return;
  const others = [...watched.entries()].filter(([id]) => id !== displayId);
  if (!others.length) { box.classList.add("hidden"); box.innerHTML = ""; return; }

  box.innerHTML = "";
  for (const [id, j] of others) {
    const chip = document.createElement("span");
    chip.className = "queue-chip is-" + j.state;
    if (j.state === "completed") {
      const a = document.createElement("a");
      a.href = `#/report/${j.symbol}`;
      a.textContent = `${j.symbol} ✓ ready`;
      chip.appendChild(a);
    } else if (j.state === "failed" || j.state === "aborted") {
      chip.textContent = `${j.symbol} — ${j.state}`;
    } else {
      chip.textContent = `${j.symbol} — ${j.state}`;
      chip.dataset.jobId = id;
    }
    box.appendChild(chip);
  }
  box.classList.remove("hidden");
}
