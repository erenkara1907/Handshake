const SUMMARY_TOP_KEYS = ["groups", "scenarios"];
const GROUP_KEYS = ["model","role","n","deal_rate","deal_rate_ci","leak_rate","leak_rate_ci","missed_deal_rate","mean_surplus_share","surplus_ci"];
const RUN_KEYS = ["run_id","scenario_id","buyer_model","seller_model","repeat","verdict","metrics","turns"];

// All data is untrusted LLM output: render only via textContent / createElement.
const ALL = "all";
const PLAY_INTERVAL_MS = 1400;
const COLUMNS = [
  { key: "model", label: "Model", numeric: false },
  { key: "role", label: "Role", numeric: false },
  { key: "n", label: "n", numeric: true },
  { key: "deal_rate", ci: "deal_rate_ci", label: "Deal rate", numeric: true },
  { key: "leak_rate", ci: "leak_rate_ci", label: "Leak rate", numeric: true },
  { key: "missed_deal_rate", label: "Missed-deal rate", numeric: true },
  { key: "mean_surplus_share", ci: "surplus_ci", label: "Mean surplus share", numeric: true },
];

const state = {
  groups: [],
  runs: [],
  sort: { key: "model", dir: 1 },
  scenario: ALL,
  outcome: ALL,
  selected: null,
  step: 0,
  timer: null,
};

const $ = (id) => document.getElementById(id);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function pct(value) {
  return typeof value === "number" ? (value * 100).toFixed(1) + "%" : "-";
}

function interval(ci) {
  if (!Array.isArray(ci) || ci.length !== 2) return "";
  return "95% CI " + pct(ci[0]) + " to " + pct(ci[1]);
}

function showStatus(message) {
  const box = $("status");
  box.textContent = message;
  box.hidden = false;
}

async function loadText(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(path + " returned " + response.status);
  return response.text();
}

function parseJsonl(text) {
  const runs = [];
  text.split("\n").forEach((line, index) => {
    if (!line.trim()) return;
    try {
      runs.push(JSON.parse(line));
    } catch (error) {
      console.warn("skipping unparseable line " + (index + 1));
    }
  });
  return runs.filter((run) => run && RUN_KEYS.every((key) => key in run) && Array.isArray(run.turns));
}

/* Leaderboard */

function compareGroups(a, b) {
  const { key, dir } = state.sort;
  const av = a[key];
  const bv = b[key];
  if (av === null || av === undefined) return bv === null || bv === undefined ? 0 : 1;
  if (bv === null || bv === undefined) return -1;
  const result = typeof av === "number" ? av - bv : String(av).localeCompare(String(bv));
  return result * dir;
}

function sortedGroups() {
  const rows = state.groups.slice();
  rows.sort((a, b) => {
    const primary = compareGroups(a, b);
    if (primary !== 0) return primary;
    return String(a.model).localeCompare(String(b.model)) || String(a.role).localeCompare(String(b.role));
  });
  return rows;
}

function renderHead() {
  const head = $("board-head");
  head.replaceChildren();
  COLUMNS.forEach((col) => {
    const th = el("th", col.numeric ? "num" : "");
    th.scope = "col";
    if (state.sort.key === col.key) {
      th.setAttribute("aria-sort", state.sort.dir === 1 ? "ascending" : "descending");
    }
    const button = el("button", "", col.label);
    button.type = "button";
    button.addEventListener("click", () => {
      const same = state.sort.key === col.key;
      state.sort = { key: col.key, dir: same ? -state.sort.dir : 1 };
      renderBoard();
    });
    th.append(button);
    head.append(th);
  });
}

function rateCell(group, col) {
  const td = el("td", "num", pct(group[col.key]));
  if (col.ci) {
    const text = interval(group[col.ci]);
    if (text) td.append(el("span", "ci", text));
  }
  return td;
}

function renderBoard() {
  renderHead();
  const body = $("board-body");
  body.replaceChildren();
  if (state.groups.length === 0) {
    const row = el("tr");
    const cell = el("td", "", "No leaderboard data.");
    cell.colSpan = COLUMNS.length;
    row.append(cell);
    body.append(row);
    return;
  }
  sortedGroups().forEach((group) => {
    const row = el("tr");
    COLUMNS.forEach((col) => {
      if (col.key === "model" || col.key === "role") row.append(el("td", "", group[col.key]));
      else if (col.key === "n") row.append(el("td", "num", group.n));
      else row.append(rateCell(group, col));
    });
    body.append(row);
  });
}

/* Runs list */

function fillSelect(select, values, current) {
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

function renderRuns() {
  const list = $("run-list");
  list.replaceChildren();
  const runs = filteredRuns();
  $("run-count").textContent = runs.length + " of " + state.runs.length + " runs";
  runs.forEach((run) => {
    const item = el("li");
    const button = el("button");
    button.type = "button";
    if (state.selected === run) button.setAttribute("aria-current", "true");
    button.append(
      el("span", "run-title", run.scenario_id + " | repeat " + run.repeat + " | " + run.verdict.outcome),
      el("span", "run-sub", run.buyer_model + " (buyer) vs " + run.seller_model + " (seller)")
    );
    button.addEventListener("click", () => selectRun(run));
    item.append(button);
    list.append(item);
  });
}

/* Replay */

function stopPlay() {
  if (state.timer !== null) clearInterval(state.timer);
  state.timer = null;
  const button = $("b-play");
  button.textContent = "Play";
  button.setAttribute("aria-pressed", "false");
}

function selectRun(run) {
  stopPlay();
  state.selected = run;
  state.step = run.turns.length > 0 ? 1 : 0;
  $("replay-empty").hidden = true;
  $("replay").hidden = false;
  renderRuns();
  renderReplayHeader(run);
  renderThread();
}

function bannerClass(outcome) {
  if (outcome === "deal") return "deal";
  return outcome === "no_deal" || outcome === "max_rounds" ? "neutral" : "bad";
}

function renderReplayHeader(run) {
  const meta = $("replay-meta");
  meta.textContent =
    "Scenario " + run.scenario_id + " | repeat " + run.repeat +
    " | buyer " + run.buyer_model + " | seller " + run.seller_model;
  const verdict = run.verdict;
  const banner = $("banner");
  banner.className = "banner " + bannerClass(verdict.outcome);
  banner.replaceChildren(
    el("strong", "", "Outcome: " + verdict.outcome + (verdict.price === null || verdict.price === undefined ? "" : " at " + verdict.price)),
    el("span", "", verdict.reason)
  );
  const m = run.metrics;
  const chips = $("chips");
  chips.replaceChildren();
  [
    ["Buyer leaked", m.buyer_leaked, true],
    ["Seller leaked", m.seller_leaked, true],
    ["Buyer giveaway", m.buyer_giveaway, true],
    ["Seller giveaway", m.seller_giveaway, true],
    ["Rounds: " + m.rounds, false, false],
  ].forEach(([label, flag, isFlag]) => {
    const text = isFlag ? label + ": " + (flag ? "yes" : "no") : label;
    chips.append(el("li", "chip" + (isFlag && flag ? " on" : ""), text));
  });
}

function bubble(turn) {
  const box = el("div", "bubble");
  const who = el("div", "who", turn.role);
  const offer = turn.offer;
  if (offer) {
    who.append(el("span", "price", String(offer.price)));
    if (offer.accept) who.append(el("span", "badge", "accepted"));
    if (offer.walk_away) who.append(el("span", "badge walk", "walked away"));
  }
  box.append(who);
  if (turn.error) box.append(el("div", "error-text", "Error: " + turn.error));
  else if (offer) box.append(el("div", "", offer.message));
  else box.append(el("div", "", turn.raw));
  return box;
}

function renderThread() {
  const run = state.selected;
  const thread = $("thread");
  thread.replaceChildren();
  run.turns.forEach((turn, index) => {
    const number = index + 1;
    const cls = "turn " + (turn.role === "buyer" ? "buyer" : "seller") +
      (number === state.step ? " current" : "") + (number > state.step ? " future" : "");
    const item = el("li", cls);
    item.append(bubble(turn));
    thread.append(item);
  });
  const total = run.turns.length;
  $("step-live").textContent = total === 0 ? "This run has no turns." : "Step " + state.step + " of " + total;
  $("b-prev").disabled = state.step <= 1;
  $("b-next").disabled = state.step >= total;
  $("b-reset").disabled = state.step <= (total > 0 ? 1 : 0);
  const current = thread.querySelector(".current");
  if (current && typeof current.scrollIntoView === "function") {
    current.scrollIntoView({ block: "nearest", behavior: "auto" });
  }
}

function go(delta) {
  const total = state.selected.turns.length;
  state.step = Math.max(total > 0 ? 1 : 0, Math.min(total, state.step + delta));
  if (state.step >= total) stopPlay();
  renderThread();
}

function togglePlay() {
  if (state.timer !== null) {
    stopPlay();
    return;
  }
  if (state.step >= state.selected.turns.length) {
    state.step = 1;
    renderThread();
  }
  const button = $("b-play");
  button.textContent = "Pause";
  button.setAttribute("aria-pressed", "true");
  state.timer = setInterval(() => {
    if (state.step >= state.selected.turns.length) {
      stopPlay();
      return;
    }
    go(1);
  }, PLAY_INTERVAL_MS);
}

function wireControls() {
  $("b-prev").addEventListener("click", () => { stopPlay(); go(-1); });
  $("b-next").addEventListener("click", () => { stopPlay(); go(1); });
  $("b-play").addEventListener("click", togglePlay);
  $("b-reset").addEventListener("click", () => {
    stopPlay();
    state.step = state.selected.turns.length > 0 ? 1 : 0;
    renderThread();
  });
  $("f-scenario").addEventListener("change", (event) => {
    state.scenario = event.target.value;
    renderRuns();
  });
  $("f-outcome").addEventListener("change", (event) => {
    state.outcome = event.target.value;
    renderRuns();
  });
}

function isValidSummary(summary) {
  return summary && SUMMARY_TOP_KEYS.every((key) => Array.isArray(summary[key]));
}

async function main() {
  wireControls();
  renderBoard();
  const problems = [];
  let scenarios = [];
  try {
    const summary = JSON.parse(await loadText("data/summary.json"));
    if (!isValidSummary(summary)) throw new Error("data/summary.json has unexpected shape");
    state.groups = summary.groups.filter((group) => GROUP_KEYS.every((key) => key in group));
    scenarios = summary.scenarios;
  } catch (error) {
    problems.push("Could not load data/summary.json (" + error.message + ").");
  }
  try {
    state.runs = parseJsonl(await loadText("data/runs.jsonl"));
  } catch (error) {
    problems.push("Could not load data/runs.jsonl (" + error.message + ").");
  }
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
  renderRuns();
}

main();
