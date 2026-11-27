export async function loadText(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(path + " returned " + response.status);
  return response.text();
}

export function parseJsonl(text, runKeys) {
  const runs = [];
  text.split("\n").forEach((line, index) => {
    if (!line.trim()) return;
    try {
      runs.push(JSON.parse(line));
    } catch (error) {
      console.warn("skipping unparseable line " + (index + 1));
    }
  });
  return runs.filter((run) => run && runKeys.every((key) => key in run) && Array.isArray(run.turns));
}

export function isValidSummary(summary, topKeys) {
  return Boolean(summary) && topKeys.every((key) => Array.isArray(summary[key]));
}

export function validGroups(groups, groupKeys) {
  return groups.filter((group) => group && groupKeys.every((key) => key in group));
}
