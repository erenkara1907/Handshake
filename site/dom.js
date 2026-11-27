// All data is untrusted LLM output: render only via textContent / createElement.
export const $ = (id) => document.getElementById(id);

export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

export function pct(value) {
  return typeof value === "number" ? (value * 100).toFixed(1) + "%" : "-";
}

export function interval(ci) {
  if (!Array.isArray(ci) || ci.length !== 2) return "";
  return "95% CI " + pct(ci[0]) + " to " + pct(ci[1]);
}

export function showStatus(message) {
  const box = $("status");
  box.textContent = message;
  box.hidden = false;
}
