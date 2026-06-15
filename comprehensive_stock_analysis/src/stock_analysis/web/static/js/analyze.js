// New Analysis: form submit + refresh, then poll job status and drive progress.
import { $, $$, fetchJSON, fmtNum, navigate } from "./util.js";

let polling = null;
let currentJob = null;

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
export function refreshSymbol(symbol, assetType) {
  navigate("#/new");
  // let the view switch before showing progress
  setTimeout(() => startAnalysis({
    symbol, depth: "standard", asset_type: assetType || "auto", use_cache: false,
  }), 60);
}

export async function startAnalysis(payload) {
  if (!payload.symbol) return;
  $("#run-btn").disabled = true;
  showProgress(payload.symbol, payload.use_cache === false);
  try {
    const { job_id } = await fetchJSON("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    currentJob = job_id;
    const cancel = $("#cancel-btn");
    cancel.classList.remove("hidden");
    cancel.disabled = false;
    startPolling(job_id, payload.symbol);
  } catch (err) {
    showError(err.message);
    $("#run-btn").disabled = false;
  }
}

async function onCancel() {
  if (!currentJob) return;
  $("#cancel-btn").disabled = true;
  $("#progress-stage").textContent = "Cancelling…";
  try {
    await fetchJSON(`/api/jobs/${currentJob}/cancel`, { method: "POST" });
  } catch (_) { /* 409 if already finished — polling reflects final state */ }
}

function showProgress(symbol, isRefresh) {
  $("#progress-card").classList.remove("hidden");
  $("#progress-error").classList.add("hidden");
  $("#progress-symbol").textContent = symbol;
  $("#progress-stage").textContent = isRefresh ? "Refreshing — queued…" : "Queued…";
  $("#progress-bar").style.width = "3%";
  $("#progress-pct").textContent = "0%";
  $("#progress-tokens").textContent = "0";
  $("#progress-calls").textContent = "0";
  $("#progress-activity").classList.add("hidden");
  $("#progress-activity").querySelector(".txt").textContent = "";
  setStepper(0, "queued");
  $("#progress-card").scrollIntoView({ behavior: "smooth", block: "nearest" });
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

function startPolling(jobId, symbol) {
  if (polling) clearInterval(polling);
  polling = setInterval(async () => {
    let job;
    try {
      job = await fetchJSON(`/api/jobs/${jobId}`);
    } catch (_) { return; }
    const pct = Math.round((job.progress || 0) * 100);
    $("#progress-bar").style.width = Math.max(pct, 3) + "%";
    $("#progress-pct").textContent = pct + "%";
    $("#progress-stage").textContent = job.stage || job.state;
    $("#progress-tokens").textContent = fmtNum((job.token_usage || {}).total_tokens || 0, 0);
    $("#progress-calls").textContent = job.llm_calls || 0;
    setStepper(job.progress || 0, job.state);
    const act = $("#progress-activity");
    if (job.activity) {
      act.querySelector(".txt").textContent = job.activity;
      act.classList.remove("hidden");
    }

    if (["completed", "failed", "aborted"].includes(job.state)) {
      clearInterval(polling); polling = null; currentJob = null;
      $("#run-btn").disabled = false;
      $("#cancel-btn").classList.add("hidden");
      $("#progress-activity").classList.add("hidden");
    }
    if (job.state === "completed") {
      $("#progress-bar").style.width = "100%";
      navigate(`#/report/${symbol}`);
    } else if (job.state === "aborted") {
      $("#progress-stage").textContent = "Aborted";
      showError("Analysis was cancelled before completing.");
    } else if (job.state === "failed") {
      showError(job.error || "Analysis failed.");
    }
  }, 1000);
}
