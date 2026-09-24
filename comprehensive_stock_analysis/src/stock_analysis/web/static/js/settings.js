// LLM configuration view. Choices are local to this browser and apply to new runs.
import { $, fetchJSON } from "./util.js";

const STORAGE_KEY = "llm-selection";
let options = null;

function savedSelection() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") || {};
  } catch (_) {
    return {};
  }
}

export function getLLMSelection() {
  const saved = savedSelection();
  return {
    llm_provider: saved.llm_provider || null,
    model: saved.model || null,
  };
}

export async function initSettings() {
  const providerSelect = $("#settings-llm-provider");
  if (!providerSelect) return;
  try {
    options = await fetchJSON("/api/llm/options");
    for (const provider of options.providers || []) {
      const option = document.createElement("option");
      option.value = provider.id;
      option.textContent = provider.label;
      providerSelect.appendChild(option);
    }
    const saved = savedSelection();
    providerSelect.value = saved.llm_provider || "";
    $("#settings-llm-model").value = saved.model || "";
    updateModelSuggestions(false);
    $("#settings-llm-provider").addEventListener("change", () => updateModelSuggestions(true));
    $("#settings-form").addEventListener("submit", saveSettings);
    $("#settings-reset").addEventListener("click", resetSettings);
  } catch (err) {
    showSettingsStatus(err.message || "Could not load model configuration", true);
  }
}

function updateModelSuggestions(resetModel) {
  if (!options) return;
  const provider = $("#settings-llm-provider").value;
  const selected = (options.providers || []).find((item) => item.id === provider);
  const models = selected?.models || [];
  const datalist = $("#settings-llm-models");
  datalist.replaceChildren(...models.map((model) => {
    const option = document.createElement("option");
    option.value = model;
    return option;
  }));
  const modelInput = $("#settings-llm-model");
  if (resetModel) modelInput.value = models[0] || "";
  modelInput.placeholder = provider ? (models[0] || "Enter a model ID") : (options.default_model || "Configured default");
}

function saveSettings(event) {
  event.preventDefault();
  const selection = {
    llm_provider: $("#settings-llm-provider").value,
    model: $("#settings-llm-model").value.trim(),
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(selection));
  showSettingsStatus("Saved for new analyses");
}

function resetSettings() {
  localStorage.removeItem(STORAGE_KEY);
  $("#settings-llm-provider").value = "";
  $("#settings-llm-model").value = "";
  updateModelSuggestions(false);
  showSettingsStatus("Using configured defaults");
}

function showSettingsStatus(message, error = false) {
  const status = $("#settings-status");
  if (!status) return;
  status.textContent = message;
  status.classList.toggle("error", error);
  status.classList.remove("hidden");
}
