import { $, el } from "./dom.js";
import { ALL, state } from "./state.js";

export function fillSelect(select, values, current) {
  select.replaceChildren();
  [ALL].concat(values).forEach((value) => {
    const option = el("option", "", value === ALL ? "All" : value);
    option.value = value;
    select.append(option);
  });
  select.value = current;
}

function filteredRuns() {
  return state.runs.filter(
    (run) =>
      (state.scenario === ALL || run.scenario_id === state.scenario) &&
      (state.outcome === ALL || run.verdict.outcome === state.outcome)
  );
}

// Marks the selected run in place so the focused run button is never rebuilt.
export function markSelected() {
  $("run-list").querySelectorAll("button").forEach((button) => {
    if (button.runRef === state.selected) button.setAttribute("aria-current", "true");
    else button.removeAttribute("aria-current");
  });
}

export function renderRuns(onSelect) {
  const list = $("run-list");
  list.replaceChildren();
  const runs = filteredRuns();
  $("run-count").textContent = runs.length + " of " + state.runs.length + " runs";
  runs.forEach((run) => {
    const item = el("li");
    const button = el("button");
    button.type = "button";
    button.runRef = run;
    button.append(
      el("span", "run-title", run.scenario_id + " | repeat " + run.repeat + " | " + run.verdict.outcome),
      el("span", "run-sub", run.buyer_model + " (buyer) vs " + run.seller_model + " (seller)")
    );
    button.addEventListener("click", () => onSelect(run));
    item.append(button);
    list.append(item);
  });
  markSelected();
}
