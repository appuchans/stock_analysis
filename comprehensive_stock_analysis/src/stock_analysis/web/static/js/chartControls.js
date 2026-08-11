// Shared UI controls for price-comparison charts: a period button group and a
// symbol-chip add/remove input. Used by the report Overview price panel and
// the Compare page — same interaction, different data source underneath.
import { el } from "./util.js";

const PERIODS = [
  { key: "1mo", label: "1M" },
  { key: "3mo", label: "3M" },
  { key: "6mo", label: "6M" },
  { key: "1y", label: "1Y" },
  { key: "5y", label: "5Y" },
];

export function periodSelector(current, onChange) {
  const wrap = el("div", { class: "tabs" });
  function render() {
    wrap.innerHTML = "";
    PERIODS.forEach((p) => {
      wrap.append(el("button", {
        class: "tab" + (p.key === current ? " is-active" : ""),
        type: "button",
        onclick: () => { current = p.key; onChange(p.key); render(); },
      }, p.label));
    });
  }
  render();
  return wrap;
}

const SYMBOL_RE = /^[A-Z0-9.-]{1,10}$/;

export function symbolChipInput({ getSymbols, onChange, placeholder = "Add symbol", maxSymbols = 4 }) {
  const container = el("div", { class: "chip-input" });
  const input = el("input", { type: "text", placeholder, maxlength: "10" });
  const addBtn = el("button", { class: "btn btn-ghost btn-sm", type: "button" }, "+ Add");

  function render() {
    container.innerHTML = "";
    getSymbols().forEach((sym) => {
      container.append(el("span", { class: "symbol-chip" }, sym,
        el("button", {
          type: "button",
          onclick: () => { onChange(getSymbols().filter((s) => s !== sym)); render(); },
        }, "×")));
    });
    container.append(input, addBtn);
  }

  function tryAdd() {
    const val = input.value.trim().toUpperCase();
    input.value = "";
    if (!val || !SYMBOL_RE.test(val)) return;
    const current = getSymbols();
    if (current.includes(val) || current.length >= maxSymbols) return;
    onChange([...current, val]);
    render();
  }

  addBtn.addEventListener("click", tryAdd);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); tryAdd(); }
  });

  render();
  return container;
}
