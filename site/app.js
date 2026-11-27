const SUMMARY_TOP_KEYS = ["groups", "scenarios"];
const GROUP_KEYS = ["model","role","n","feasible_n","deal_rate","deal_rate_ci","leak_rate","leak_rate_ci","giveaway_rate","giveaway_rate_ci","missed_deal_rate","mean_surplus_share","surplus_ci"];
const RUN_KEYS = ["run_id","scenario_id","scenario","buyer_model","seller_model","repeat","verdict","metrics","turns"];

// Entry point. Constants stay here and are passed into modules (no import cycle).
import { $, showStatus } from "./dom.js";
import { ALL, state } from "./state.js";
import { loadText, parseJsonl, isValidSummary, validGroups } from "./data.js";
import { initHead, renderBoard } from "./board.js";
import { fillSelect, renderRuns } from "./runs.js";
import { selectRun, wirePlayer } from "./player.js";

function wireFilters() {
  $("f-scenario").addEventListener("change", (event) => {
    state.scenario = event.target.value;
    renderRuns(selectRun);
  });
  $("f-outcome").addEventListener("change", (event) => {
    state.outcome = event.target.value;
    renderRuns(selectRun);
  });
}

async function loadSummary(problems) {
  try {
    const summary = JSON.parse(await loadText("data/summary.json"));
    if (!isValidSummary(summary, SUMMARY_TOP_KEYS)) throw new Error("data/summary.json has unexpected shape");
    state.groups = validGroups(summary.groups, GROUP_KEYS);
    return summary.scenarios;
  } catch (error) {
    problems.push("Could not load data/summary.json (" + error.message + ").");
    return [];
  }
}

async function loadRuns(problems) {
  try {
    state.runs = parseJsonl(await loadText("data/runs.jsonl"), RUN_KEYS);
  } catch (error) {
    problems.push("Could not load data/runs.jsonl (" + error.message + ").");
  }
}

async function main() {
  wirePlayer();
  wireFilters();
  initHead();
  renderBoard();
  const problems = [];
  let scenarios = await loadSummary(problems);
  await loadRuns(problems);
  if (problems.length > 0) {
    showStatus(problems.join(" ") + " Generate them with the report command (--json-out) and copy runs.jsonl into site/data/, and serve over http.");
  } else if (state.runs.length === 0) {
    showStatus("data/runs.jsonl contains no runs.");
  }
  if (scenarios.length === 0) {
    scenarios = Array.from(new Set(state.runs.map((run) => run.scenario_id))).sort();
  }
  const outcomes = Array.from(new Set(state.runs.map((run) => run.verdict.outcome))).sort();
  fillSelect($("f-scenario"), scenarios, ALL);
  fillSelect($("f-outcome"), outcomes, ALL);
  renderBoard();
  renderRuns(selectRun);
}

main();
