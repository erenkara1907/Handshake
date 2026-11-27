import { $, el, pct, interval } from "./dom.js";
import { state } from "./state.js";

const COLUMNS = [
  { key: "model", label: "Model", numeric: false },
  { key: "role", label: "Role", numeric: false },
  { key: "n", label: "n (all runs)", numeric: true, count: true },
  { key: "feasible_n", label: "Feasible n (ZOPA > 0)", numeric: true, count: true },
  { key: "deal_rate", ci: "deal_rate_ci", label: "Deal rate (feasible)", numeric: true },
  { key: "leak_rate", ci: "leak_rate_ci", label: "Leak rate (all)", numeric: true },
  { key: "giveaway_rate", ci: "giveaway_rate_ci", label: "Giveaway rate (all)", numeric: true },
  { key: "missed_deal_rate", label: "Missed-deal rate (feasible)", numeric: true },
  { key: "mean_surplus_share", ci: "surplus_ci", label: "Mean surplus share", numeric: true },
];

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
  rows.sort(
    (a, b) =>
      compareGroups(a, b) ||
      String(a.model).localeCompare(String(b.model)) ||
      String(a.role).localeCompare(String(b.role))
  );
  return rows;
}

// Header buttons are built once and updated in place so keyboard focus survives a sort.
export function initHead() {
  const head = $("board-head");
  head.replaceChildren();
  COLUMNS.forEach((col) => {
    const th = el("th", col.numeric ? "num" : "");
    th.scope = "col";
    th.dataset.key = col.key;
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

function updateSortMarks() {
  $("board-head").querySelectorAll("th").forEach((th) => {
    if (th.dataset.key === state.sort.key) {
      th.setAttribute("aria-sort", state.sort.dir === 1 ? "ascending" : "descending");
    } else {
      th.removeAttribute("aria-sort");
    }
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

function groupRow(group) {
  const row = el("tr");
  COLUMNS.forEach((col) => {
    if (col.key === "model" || col.key === "role") row.append(el("td", "", group[col.key]));
    else if (col.count) row.append(el("td", "num", group[col.key]));
    else row.append(rateCell(group, col));
  });
  return row;
}

export function renderBoard() {
  updateSortMarks();
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
  sortedGroups().forEach((group) => body.append(groupRow(group)));
}
