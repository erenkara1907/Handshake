import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from handshake import cli
from handshake.cli import app
from handshake.metrics import RunMetrics
from handshake.models import Outcome, Scenario
from handshake.records import RunRecord, append_record
from handshake.referee import Verdict

runner = CliRunner()

SCENARIO = Scenario(
    id="s",
    item="car",
    public_listing_price=100,
    buyer_max=95,
    seller_min=80,
    max_rounds=5,
    currency="EUR",
)

CONFIG_TEXT = """
[[models]]
provider = "ollama"
model = "m1"

[[models]]
provider = "ollama"
model = "m2"
"""


def _record(buyer: str, seller: str, scenario_id: str, repeat: int = 0) -> RunRecord:
    return RunRecord(
        run_id=f"{scenario_id}|{buyer}|{seller}|{repeat}",
        scenario_id=scenario_id,
        scenario=SCENARIO,
        buyer_model=buyer,
        seller_model=seller,
        repeat=repeat,
        verdict=Verdict(outcome=Outcome.DEAL, price=None, reason="r"),
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
        turns=[],
    )


@pytest.fixture
def runs_file(tmp_path: Path) -> Path:
    path = tmp_path / "runs.jsonl"
    append_record(path, _record("a", "b", "s2"))
    append_record(path, _record("a", "b", "s1", repeat=1))
    return path


def test_report_prints_each_model_role_with_n(runs_file: Path) -> None:
    result = runner.invoke(app, ["report", str(runs_file)])

    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert any(line.split()[:3] == ["a", "buyer", "2"] for line in lines)
    assert any(line.split()[:3] == ["b", "seller", "2"] for line in lines)


def test_report_json_out_has_groups_key(runs_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "nested" / "report.json"

    result = runner.invoke(app, ["report", str(runs_file), "--json-out", str(out)])

    assert result.exit_code == 0
    data = json.loads(out.read_text())
    assert {group["model"] for group in data["groups"]} == {"a", "b"}
    assert data["scenarios"] == ["s1", "s2"]


def test_report_empty_file_exits_nonzero_with_message(tmp_path: Path) -> None:
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")

    result = runner.invoke(app, ["report", str(empty)])

    assert result.exit_code != 0
    assert "no records" in result.output.lower()


def test_run_requires_existing_config(tmp_path: Path) -> None:
    missing = tmp_path / "nope.toml"

    result = runner.invoke(app, ["run", "--config", str(missing)])

    assert result.exit_code != 0
    assert "config" in result.output.lower()


def test_run_invalid_config_exits_cleanly(tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text('[[models]]\nprovider = "nope"\nmodel = "x"\n')

    result = runner.invoke(app, ["run", "--config", str(bad)])

    assert result.exit_code != 0
    assert result.exception is None or isinstance(result.exception, SystemExit)


def _patch_run_all(monkeypatch: pytest.MonkeyPatch) -> dict:
    captured: dict = {}

    async def fake_run_all(specs, out_path, execute, concurrency=1, on_error=None) -> int:
        captured.update(specs=list(specs), concurrency=concurrency, on_error=on_error)
        return 3

    monkeypatch.setattr(cli, "run_all", fake_run_all)
    return captured


def test_run_wires_on_error_and_spec_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "c.toml"
    config.write_text(CONFIG_TEXT)
    captured = _patch_run_all(monkeypatch)

    result = runner.invoke(
        app,
        [
            "run",
            "--config",
            str(config),
            "--out",
            str(tmp_path / "o.jsonl"),
            "--scenarios",
            "2",
            "--repeats",
            "2",
            "--concurrency",
            "4",
        ],
    )

    assert result.exit_code == 0
    assert callable(captured["on_error"])
    assert len(captured["specs"]) == 2 * 4 * 2
    assert captured["concurrency"] == 4
    assert "3" in result.output and "16" in result.output


def test_on_error_handler_does_not_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "c.toml"
    config.write_text(CONFIG_TEXT)
    captured = _patch_run_all(monkeypatch)
    runner.invoke(app, ["run", "--config", str(config), "--scenarios", "1", "--repeats", "1"])

    captured["on_error"](captured["specs"][0], RuntimeError("x"))
