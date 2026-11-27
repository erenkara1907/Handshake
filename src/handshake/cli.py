import asyncio
import json
import logging
import tomllib
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from handshake.config import ConfigError, ModelConfig, load_models
from handshake.execute import execute_run
from handshake.records import read_records
from handshake.runner import RunSpec, build_specs, run_all
from handshake.scenarios import generate_scenarios
from handshake.stats import GroupStats, aggregate

logger = logging.getLogger(__name__)

app = typer.Typer(no_args_is_help=True, add_completion=False)

DEFAULT_OUT = Path("runs.jsonl")
DEFAULT_SCENARIOS = 12
DEFAULT_REPEATS = 3
TABLE_HEADER = ("model", "role", "n", "deal_rate", "leak_rate", "missed", "surplus_share")


def _fail(message: str) -> typer.Exit:
    typer.echo(message, err=True)
    return typer.Exit(code=1)


def _load_models_or_exit(path: Path) -> list[ModelConfig]:
    if not path.is_file():
        raise _fail(f"config file not found: {path}")
    try:
        models = load_models(path)
    except (ConfigError, ValidationError, tomllib.TOMLDecodeError) as error:
        raise _fail(f"invalid config {path}: {error}") from error
    if not models:
        raise _fail(f"config {path} defines no [[models]]")
    return models


def _on_error(spec: RunSpec, error: Exception) -> None:
    logger.error("run %s failed", spec.run_id, exc_info=error)
    typer.echo(f"run failed (will retry on resume): {spec.run_id}: {error}", err=True)


@app.command()
def run(
    config: Annotated[Path, typer.Option(help="TOML file listing [[models]].")],
    out: Annotated[Path, typer.Option(help="JSONL results file (resumable).")] = DEFAULT_OUT,
    scenarios: Annotated[int, typer.Option(help="Number of scenarios.")] = DEFAULT_SCENARIOS,
    seed: Annotated[int, typer.Option(help="Scenario generation seed.")] = 0,
    repeats: Annotated[int, typer.Option(help="Repeats per pairing.")] = DEFAULT_REPEATS,
    concurrency: Annotated[int, typer.Option(help="Concurrent runs.")] = 1,
) -> None:
    """Run the model-vs-model negotiation sweep, resuming from OUT."""
    models = _load_models_or_exit(config)
    specs = build_specs(generate_scenarios(seed, scenarios), models, repeats)
    executed = asyncio.run(
        run_all(specs, out, execute_run, concurrency=concurrency, on_error=_on_error)
    )
    typer.echo(f"executed {executed} runs of {len(specs)} planned specs -> {out}")


def _interval(rate: float, interval: tuple[float, float]) -> str:
    return f"{rate:.2f} [{interval[0]:.2f},{interval[1]:.2f}]"


def _row(group: GroupStats) -> tuple[str, ...]:
    surplus = "-"
    if group.mean_surplus_share is not None and group.surplus_ci is not None:
        surplus = _interval(group.mean_surplus_share, group.surplus_ci)
    return (
        group.model,
        group.role.value,
        str(group.n),
        _interval(group.deal_rate, group.deal_rate_ci),
        _interval(group.leak_rate, group.leak_rate_ci),
        f"{group.missed_deal_rate:.2f}",
        surplus,
    )


def _format_table(rows: list[tuple[str, ...]]) -> list[str]:
    widths = [max(len(row[i]) for row in rows) for i in range(len(TABLE_HEADER))]
    return [
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()
        for row in rows
    ]


@app.command()
def report(
    runs: Annotated[Path, typer.Argument(help="JSONL results file.")],
    json_out: Annotated[Path | None, typer.Option(help="Write stats as JSON here.")] = None,
) -> None:
    """Print per-model, per-role statistics from RUNS."""
    try:
        records = read_records(runs)
    except ValueError as error:
        raise _fail(str(error)) from error
    if not records:
        raise _fail(f"no records found in {runs}")
    groups = aggregate(records)
    rows = [TABLE_HEADER, *(_row(group) for group in groups)]
    for line in _format_table(rows):
        typer.echo(line)
    if json_out is not None:
        payload = {
            "groups": [group.model_dump(mode="json") for group in groups],
            "scenarios": sorted({record.scenario_id for record in records}),
        }
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
