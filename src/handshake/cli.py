import asyncio
import logging
import tempfile
import tomllib
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
from dotenv import find_dotenv, load_dotenv
from pydantic import ValidationError

from handshake.config import ConfigError, ModelConfig, load_models
from handshake.execute import execute_run
from handshake.records import read_records
from handshake.runner import RunSpec, build_specs, run_all
from handshake.scenarios import generate_scenarios
from handshake.site_server import LOCAL_HOST, make_server, prepare_site, summary_json
from handshake.stats import GroupStats, aggregate

logger = logging.getLogger(__name__)

app = typer.Typer(no_args_is_help=True, add_completion=False)

DEFAULT_OUT = Path("runs.jsonl")
DEFAULT_SCENARIOS = 12
DEFAULT_REPEATS = 3
DEFAULT_PORT = 8000
TABLE_HEADER = (
    "model",
    "role",
    "n",
    "feasible_n",
    "deal_rate(feasible)",
    "leak_rate",
    "giveaway_rate",
    "missed(feasible)",
    "surplus_share",
)


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
    # Keys come from the environment; a .env in the working directory fills in what the
    # shell did not set (override=False: an exported variable always wins). The seller
    # subprocess inherits os.environ, so it sees the same key.
    load_dotenv(find_dotenv(usecwd=True), override=False)
    models = _load_models_or_exit(config)
    specs = build_specs(generate_scenarios(seed, scenarios), models, repeats)
    out.parent.mkdir(parents=True, exist_ok=True)
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
        str(group.feasible_n),
        _interval(group.deal_rate, group.deal_rate_ci),
        _interval(group.leak_rate, group.leak_rate_ci),
        _interval(group.giveaway_rate, group.giveaway_rate_ci),
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
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(summary_json(records), encoding="utf-8")


@app.command()
def serve(
    runs: Annotated[Path, typer.Argument(help="JSONL results file.")],
    port: Annotated[int, typer.Option(help="Port to listen on.")] = DEFAULT_PORT,
    open_browser: Annotated[
        bool, typer.Option("--open/--no-open", help="Open the page in a browser.")
    ] = True,
) -> None:
    """Serve the replay site for RUNS at http://127.0.0.1:PORT (Ctrl-C to stop)."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            prepare_site(runs, Path(tmp))
        except (ValueError, FileNotFoundError) as error:
            raise _fail(str(error)) from error
        try:
            server = make_server(Path(tmp), port)
        except OSError as error:
            raise _fail(f"cannot listen on port {port}: {error}") from error
        url = f"http://{LOCAL_HOST}:{server.server_address[1]}/"
        typer.echo(f"serving {runs} at {url}  (Ctrl-C to stop)")
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            typer.echo("stopped")
        finally:
            server.server_close()
