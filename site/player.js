import { $, el } from "./dom.js";
import { state } from "./state.js";
import { markSelected } from "./runs.js";

const PLAY_INTERVAL_MS = 1400;

function setDisabled(button, isDisabled) {
  if (isDisabled) button.setAttribute("aria-disabled", "true");
  else button.removeAttribute("aria-disabled");
}

export function stopPlay() {
  if (state.timer !== null) clearInterval(state.timer);
  state.timer = null;
  const button = $("b-play");
  button.textContent = "Play";
  button.setAttribute("aria-pressed", "false");
}

function bannerClass(outcome) {
  if (outcome === "deal") return "deal";
  return outcome === "no_deal" || outcome === "max_rounds" ? "neutral" : "bad";
}

function renderChips(m) {
  const chips = $("chips");
  chips.replaceChildren();
  [
    ["Buyer leaked", m.buyer_leaked],
    ["Seller leaked", m.seller_leaked],
    ["Buyer giveaway", m.buyer_giveaway],
    ["Seller giveaway", m.seller_giveaway],
  ].forEach(([label, flag]) => {
    chips.append(el("li", "chip" + (flag ? " on" : ""), label + ": " + (flag ? "yes" : "no")));
  });
  chips.append(el("li", "chip", "Rounds: " + m.rounds));
}

// Post-hoc data so leak, giveaway and invalid_deal flags can be checked by eye.
function renderLimits(scenario) {
  const box = $("limits");
  const isKnown = Boolean(scenario) && typeof scenario.buyer_max === "number" &&
    typeof scenario.seller_min === "number";
  box.textContent = isKnown
    ? "Hidden limits (revealed after the run): buyer_max " + scenario.buyer_max +
      " | seller_min " + scenario.seller_min +
      " | zopa " + (scenario.buyer_max - scenario.seller_min)
    : "";
  box.hidden = !isKnown;
}

function renderReplayHeader(run) {
  $("replay-meta").textContent =
    "Scenario " + run.scenario_id + " | repeat " + run.repeat +
    " | buyer " + run.buyer_model + " | seller " + run.seller_model;
  const verdict = run.verdict;
  const hasPrice = verdict.price !== null && verdict.price !== undefined;
  const banner = $("banner");
  banner.className = "banner " + bannerClass(verdict.outcome);
  banner.replaceChildren(
    el("strong", "", "Outcome: " + verdict.outcome + (hasPrice ? " at " + verdict.price : "")),
    el("span", "", verdict.reason)
  );
  renderLimits(run.scenario);
  renderChips(run.metrics);
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
  setDisabled($("b-prev"), state.step <= 1);
  setDisabled($("b-next"), state.step >= total);
  setDisabled($("b-reset"), state.step <= (total > 0 ? 1 : 0));
  const current = thread.querySelector(".current");
  if (current && typeof current.scrollIntoView === "function") {
    current.scrollIntoView({ block: "nearest", behavior: "auto" });
  }
}

export function selectRun(run) {
  stopPlay();
  state.selected = run;
  state.step = run.turns.length > 0 ? 1 : 0;
  $("replay-empty").hidden = true;
  $("replay").hidden = false;
  markSelected();
  renderReplayHeader(run);
  renderThread();
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
  state.timer = setInterval(() => go(1), PLAY_INTERVAL_MS);
}

// A control marked aria-disabled must refuse to act, not just look inactive.
function onEnabled(id, action) {
  const button = $(id);
  button.addEventListener("click", () => {
    if (button.getAttribute("aria-disabled") === "true") return;
    action();
  });
}

export function wirePlayer() {
  onEnabled("b-prev", () => { stopPlay(); go(-1); });
  onEnabled("b-next", () => { stopPlay(); go(1); });
  onEnabled("b-reset", () => {
    stopPlay();
    state.step = state.selected.turns.length > 0 ? 1 : 0;
    renderThread();
  });
  $("b-play").addEventListener("click", togglePlay);
}
