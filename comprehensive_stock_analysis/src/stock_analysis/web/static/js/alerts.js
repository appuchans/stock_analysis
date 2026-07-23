// Alerts view: notification settings form + recent alert log.
import { $, el, fetchJSON } from "./util.js";

export async function loadAlerts() {
  $("#alert-settings-form").onsubmit = onSaveSettings;
  await Promise.all([loadSettings(), loadLog()]);
}

async function loadSettings() {
  let cfg;
  try {
    cfg = await fetchJSON("/api/settings/alerts");
  } catch (_) { return; }
  $("#alert-email").value = cfg.alert_email || "";
  $("#alert-smtp-host").value = cfg.alert_smtp_host || "";
  $("#alert-smtp-port").value = cfg.alert_smtp_port || "";
  $("#alert-smtp-user").value = cfg.alert_smtp_user || "";
  $("#alert-smtp-password").placeholder = cfg.alert_smtp_password_set
    ? "•••••••• (set — leave blank to keep)" : "Not set";
  $("#alert-webhook").value = cfg.alert_webhook_url || "";
}

async function onSaveSettings(ev) {
  ev.preventDefault();
  const status = $("#alert-settings-status");
  status.textContent = "Saving…";
  const payload = {
    alert_email: $("#alert-email").value.trim() || null,
    alert_smtp_host: $("#alert-smtp-host").value.trim() || null,
    alert_smtp_port: $("#alert-smtp-port").value ? Number($("#alert-smtp-port").value) : null,
    alert_smtp_user: $("#alert-smtp-user").value.trim() || null,
    // Blank password field means "don't change" — omit it entirely.
    alert_smtp_password: $("#alert-smtp-password").value || null,
    alert_webhook_url: $("#alert-webhook").value.trim() || null,
  };
  try {
    await fetchJSON("/api/settings/alerts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    status.textContent = "Saved.";
    $("#alert-smtp-password").value = "";
    await loadSettings();
  } catch (err) {
    status.textContent = "Error: " + err.message;
  }
  setTimeout(() => { if (status.textContent !== "Saving…") status.textContent = ""; }, 3000);
}

async function loadLog() {
  const box = $("#alerts-log");
  const empty = $("#alerts-empty");
  box.innerHTML = "";
  let items = [];
  try {
    items = await fetchJSON("/api/alerts?limit=100");
  } catch (_) { items = []; }
  empty.classList.toggle("hidden", items.length > 0);
  items.forEach((it) => box.append(logItem(it)));
}

function logItem(it) {
  return el("div", { class: "alert-log-item" },
    el("span", { class: "alert-log-dot" }),
    el("div", { class: "alert-log-body" },
      el("div", { class: "alert-log-reason" }, `${it.symbol}: ${it.reason}`),
      el("div", { class: "alert-log-meta" }, (it.timestamp || "").replace("T", " "))));
}
