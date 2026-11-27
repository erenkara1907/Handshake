import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from handshake.cli import app
from handshake.metrics import RunMetrics
from handshake.models import Outcome, Role, Turn
from handshake.records import RunRecord, append_record
from handshake.referee import Verdict

SITE = Path(__file__).resolve().parent.parent / "site"
APP_JS = SITE / "app.js"
UNSAFE_SINKS = (
    "innerHTML",
    "insertAdjacentHTML",
    "outerHTML",
    "document.write",
    "eval(",
    "new Function",
    'setAttribute("href"',
    "setAttribute('href'",
)
HONESTY_NOTE = (
    "Small samples: n is shown for every row, and a 95% interval for deal, leak "
    "and surplus figures. This is a measurement of these runs, not a ranking of models."
)
SITE_FILES = sorted(p.name for p in SITE.glob("*.js")) + ["index.html", "style.css"]

runner = CliRunner()


def _parse_constant(name: str) -> list[str]:
    source = APP_JS.read_text(encoding="utf-8")
    match = re.search(rf"^const {name} = \[([^\]]*)\];", source, re.MULTILINE)
    if match is None:
        raise AssertionError(f"constant block {name} missing from app.js")
    return re.findall(r'"([^"]+)"', match.group(1))


def _record(buyer: str, seller: str, scenario_id: str, repeat: int = 0) -> RunRecord:
    return RunRecord(
        run_id=f"{scenario_id}|{buyer}|{seller}|{repeat}",
        scenario_id=scenario_id,
        buyer_model=buyer,
        seller_model=seller,
        repeat=repeat,
        verdict=Verdict(outcome=Outcome.DEAL, price=90, reason="agreed"),
        metrics=RunMetrics(
            outcome=Outcome.DEAL,
            rounds=1,
            buyer_surplus_share=0.6,
            seller_surplus_share=0.4,
            missed_deal=False,
            buyer_leaked=False,
            seller_leaked=True,
            buyer_giveaway=False,
            seller_giveaway=False,
        ),
        turns=[Turn(role=Role.BUYER, raw="x", offer=None, error="bad")],
    )


def test_parse_constant_fails_loudly_when_missing() -> None:
    with pytest.raises(AssertionError, match="NO_SUCH_BLOCK"):
        _parse_constant("NO_SUCH_BLOCK")


def test_summary_json_keys_match_site_expectations(tmp_path: Path) -> None:
    runs = tmp_path / "runs.jsonl"
    append_record(runs, _record("a", "b", "s1"))
    append_record(runs, _record("a", "b", "s2", repeat=1))
    out = tmp_path / "summary.json"

    result = runner.invoke(app, ["report", str(runs), "--json-out", str(out)])

    assert result.exit_code == 0
    data = json.loads(out.read_text())
    assert set(data) == set(_parse_constant("SUMMARY_TOP_KEYS"))
    group_keys = set(_parse_constant("GROUP_KEYS"))
    assert data["groups"]
    for group in data["groups"]:
        assert set(group) == group_keys


def test_run_record_keys_match_site_expectations() -> None:
    dumped = _record("a", "b", "s1").model_dump(mode="json")

    assert set(dumped) == set(_parse_constant("RUN_KEYS"))


def test_site_has_js_modules() -> None:
    assert "app.js" in SITE_FILES
    assert len([n for n in SITE_FILES if n.endswith(".js")]) > 1


@pytest.mark.parametrize("path", sorted(SITE.glob("*.js")), ids=lambda p: p.name)
def test_site_js_has_no_unsafe_sinks(path: Path) -> None:
    source = path.read_text(encoding="utf-8")

    for sink in UNSAFE_SINKS:
        assert sink not in source, f"{path.name} must not use {sink}"


@pytest.mark.parametrize("name", SITE_FILES)
def test_site_makes_no_external_requests(name: str) -> None:
    text = (SITE / name).read_text(encoding="utf-8")

    assert "http://" not in text
    assert "https://" not in text


def test_index_html_has_honesty_note() -> None:
    assert HONESTY_NOTE in (SITE / "index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("button_id", ["b-prev", "b-next", "b-reset"])
def test_player_controls_refuse_when_aria_disabled(button_id: str) -> None:
    source = (SITE / "player.js").read_text(encoding="utf-8")

    assert f'onEnabled("{button_id}"' in source
    guard = 'if (button.getAttribute("aria-disabled") === "true") return;'
    assert guard in source
