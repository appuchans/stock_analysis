// New Analysis form: submit, then poll job status and drive the progress panel.
import { $, fetchJSON, fmtNum, navigate } from "./util.js";

let polling = null;

export function initAnalyzeForm() {
  const form = $("#analyze-form");
  if (!form) return;
  form.addEventListener("submit", onSubmit);
}

async function onSubmit(ev) {
  ev.preventDefault();
  const btn = $("#run-btn");
  const symbol = $("#symbol").value.trim().toUpperCase();
  if (!symbol) return;

  const payload = {
    symbol,
    depth: $("#depth").value,
    asset_type: $("#asset_type").value,
    use_cache: $("#use_cache").checked,
  };

  btn.disabled = true;
  showProgress(symbol);
  try {
    const { job_id } = await fetchJSON("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    startPolling(job_id, symbol);
  } catch (err) {
    showError(err.message);
    btn.disabled = false;
  }
}

function showProgress(symbol) {
  $("#progress-card").classList.remove("hidden");
  $("#progress-error").classList.add("hidden");
  $("#progress-symbol").textContent = symbol;
  $("#progress-stage").textContent = "Queued…";
  $("#progress-bar").style.width = "3%";
  $("#progress-pct").textContent = "0%";
  $("#progress-tokens").textContent = "0 tokens";
  $("#progress-calls").textContent = "0 LLM calls";
}

function showError(msg) {
  const box = $("#progress-error");
  box.textContent = msg;
  box.classList.remove("hidden");
  $("#progress-stage").textContent = "Failed";
}

function startPolling(jobId, symbol) {
  if (polling) clearInterval(polling);
  polling = setInterval(async () => {
    let job;
    try {
      job = await fetchJSON(`/api/jobs/${jobId}`);
    } catch (err) {
      return; // transient; keep polling
    }
    const pct = Math.round((job.progress || 0) * 100);
    $("#progress-bar").style.width = Math.max(pct, 3) + "%";
    $("#progress-pct").textContent = pct + "%";
    $("#progress-stage").textContent = job.stage || job.state;
    const tu = job.token_usage || {};
    $("#progress-tokens").textContent = `${fmtNum(tu.total_tokens || 0, 0)} tokens`;
    $("#progress-calls").textContent = `${job.llm_calls || 0} LLM calls`;

    if (job.state === "completed") {
      clearInterval(polling);
      polling = null;
      $("#run-btn").disabled = false;
      $("#progress-bar").style.width = "100%";
      navigate(`#/report/${symbol}`);
    } else if (job.state === "failed") {
      clearInterval(polling);
      polling = null;
      $("#run-btn").disabled = false;
      showError(job.error || "Analysis failed.");
    }
  }, 1000);
}
