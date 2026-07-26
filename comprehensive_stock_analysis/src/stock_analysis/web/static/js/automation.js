// Automation view: scheduled re-analysis + alert rules CRUD.
import { $, el, fetchJSON } from "./util.js";

const CRON_PRESETS = [
  { label: "Daily at 6pm (weekdays)", value: "0 18 * * 1-5" },
  { label: "Every hour", value: "0 * * * *" },
  { label: "Every 15 minutes", value: "*/15 * * * *" },
  { label: "Weekly (Monday 8am)", value: "0 8 * * 1" },
  { label: "Custom…", value: "" },
];

const RULE_TYPES = [
  { value: "price_above", label: "Price rises above", needsThreshold: true, unit: "$" },
  { value: "price_below", label: "Price falls below", needsThreshold: true, unit: "$" },
  { value: "pct_move_day", label: "Day move exceeds", needsThreshold: true, unit: "%" },
  { value: "target_price_hit", label: "Price reaches analyst target", needsThreshold: false },
  { value: "stop_loss_hit", label: "Price hits stop-loss", needsThreshold: false },
  { value: "recommendation_changed", label: "Recommendation changes", needsThreshold: false },
  { value: "confidence_dropped", label: "Confidence drops by", needsThreshold: true, unit: "(0-1)" },
  { value: "earnings_within_days", label: "Earnings within N days", needsThreshold: true, unit: "days" },
];

export async function loadAutomation() {
  buildScheduleForm();
  buildRuleForm();
  $("#schedule-form").onsubmit = onCreateSchedule;
  $("#rule-form").onsubmit = onCreateRule;
  await Promise.all([loadSchedules(), loadRules()]);
}

/* ── Schedules ─────────────────────────────────────────────────────────── */

function buildScheduleForm() {
  const presetSel = $("#schedule-cron-preset");
  presetSel.innerHTML = "";
  CRON_PRESETS.forEach((p) => presetSel.append(el("option", { value: p.value }, p.label)));
  presetSel.onchange = () => {
    const field = $("#schedule-cron-custom-field");
    const custom = $("#schedule-cron-custom");
    if (presetSel.value === "") {
      field.classList.remove("hidden");
      custom.focus();
    } else {
      field.classList.add("hidden");
      custom.value = presetSel.value;
    }
  };
  presetSel.dispatchEvent(new Event("change"));
}

async function loadSchedules() {
  const body = $("#schedule-body");
  body.innerHTML = "";
  let items = [];
  try {
    items = await fetchJSON("/api/schedules");
  } catch (_) { items = []; }
  $("#schedule-empty").classList.toggle("hidden", items.length > 0);
  items.forEach((s) => body.append(scheduleRow(s)));
}

function scheduleRow(s) {
  const tr = el("tr", {});
  tr.append(el("td", {}, el("div", { class: "wl-sym" }, s.target === "watchlist" ? "Watchlist" : s.target)));
  tr.append(el("td", {}, el("code", {}, s.cron_expr)));
  tr.append(el("td", {}, s.depth + (s.monitor_only ? " · monitor" : "")));
  tr.append(el("td", {}, s.last_run_at ? s.last_run_at.replace("T", " ").slice(0, 19) : "Never run"));
  tr.append(el("td", { class: "muted", style: "max-width:220px;white-space:normal" }, s.last_result || "—"));
  tr.append(el("td", { class: "wl-actions" },
    el("label", { class: "check" },
      el("input", {
        type: "checkbox", checked: s.enabled ? "checked" : null,
        onchange: (e) => onToggleSchedule(s.id, e.target.checked),
      }), "On"),
    el("button", { class: "btn btn-ghost btn-sm btn-danger", onclick: () => onDeleteSchedule(s.id) }, "Delete")));
  return tr;
}

async function onCreateSchedule(ev) {
  ev.preventDefault();
  const targetMode = $("#schedule-target-mode").value;
  const target = targetMode === "watchlist" ? "watchlist" : $("#schedule-symbol").value.trim().toUpperCase();
  const cronExpr = ($("#schedule-cron-preset").value || $("#schedule-cron-custom").value).trim();
  const payload = {
    target, cron_expr: cronExpr, depth: $("#schedule-depth").value,
    use_cache: $("#schedule-use-cache").checked, monitor_only: $("#schedule-monitor-only").checked,
  };
  try {
    await fetchJSON("/api/schedules", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    $("#schedule-symbol").value = "";
    await loadSchedules();
  } catch (err) {
    alert(err.message);
  }
}

async function onToggleSchedule(id, enabled) {
  try {
    await fetchJSON(`/api/schedules/${id}/toggle?enabled=${enabled}`, { method: "POST" });
  } catch (err) {
    alert(err.message);
  }
  await loadSchedules();
}

async function onDeleteSchedule(id) {
  try {
    await fetchJSON(`/api/schedules/${id}`, { method: "DELETE" });
  } catch (err) { /* 204 has no body — fetchJSON's .json() no-ops safely */ }
  await loadSchedules();
}

/* ── Rules ─────────────────────────────────────────────────────────────── */

function buildRuleForm() {
  const sel = $("#rule-type");
  sel.innerHTML = "";
  RULE_TYPES.forEach((t) => sel.append(el("option", { value: t.value }, t.label)));
  sel.onchange = syncThresholdField;
  syncThresholdField();
}

function syncThresholdField() {
  const type = RULE_TYPES.find((t) => t.value === $("#rule-type").value);
  const field = $("#rule-threshold-field");
  field.classList.toggle("hidden", !type.needsThreshold);
  $("#rule-threshold-unit").textContent = type.unit || "";
}

async function loadRules() {
  const body = $("#rule-body");
  body.innerHTML = "";
  let items = [];
  try {
    items = await fetchJSON("/api/rules");
  } catch (_) { items = []; }
  $("#rule-empty").classList.toggle("hidden", items.length > 0);
  items.forEach((r) => body.append(ruleRow(r)));
}

function ruleRow(r) {
  const typeInfo = RULE_TYPES.find((t) => t.value === r.rule_type);
  const tr = el("tr", {});
  tr.append(el("td", {}, el("div", { class: "wl-sym" }, r.symbol)));
  tr.append(el("td", {}, (typeInfo && typeInfo.label) || r.rule_type));
  tr.append(el("td", { class: "num" }, r.threshold != null ? String(r.threshold) : "—"));
  tr.append(el("td", {}, r.cooldown_min + "m"));
  tr.append(el("td", {}, r.last_fired_at ? r.last_fired_at.replace("T", " ").slice(0, 19) : "Never fired"));
  tr.append(el("td", { class: "wl-actions" },
    el("label", { class: "check" },
      el("input", {
        type: "checkbox", checked: r.enabled ? "checked" : null,
        onchange: (e) => onToggleRule(r.id, e.target.checked),
      }), "On"),
    el("button", { class: "btn btn-ghost btn-sm btn-danger", onclick: () => onDeleteRule(r.id) }, "Delete")));
  return tr;
}

async function onCreateRule(ev) {
  ev.preventDefault();
  const type = RULE_TYPES.find((t) => t.value === $("#rule-type").value);
  const payload = {
    symbol: $("#rule-symbol").value.trim().toUpperCase(),
    rule_type: type.value,
    threshold: type.needsThreshold ? Number($("#rule-threshold").value) : null,
    cooldown_min: Number($("#rule-cooldown").value) || 60,
  };
  try {
    await fetchJSON("/api/rules", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    $("#rule-symbol").value = "";
    $("#rule-threshold").value = "";
    await loadRules();
  } catch (err) {
    alert(err.message);
  }
}

async function onToggleRule(id, enabled) {
  try {
    await fetchJSON(`/api/rules/${id}/toggle?enabled=${enabled}`, { method: "POST" });
  } catch (err) {
    alert(err.message);
  }
  await loadRules();
}

async function onDeleteRule(id) {
  try {
    await fetchJSON(`/api/rules/${id}`, { method: "DELETE" });
  } catch (err) { /* 204 has no body */ }
  await loadRules();
}
