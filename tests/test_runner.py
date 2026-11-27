from pathlib import Path

import pytest

from handshake.config import ModelConfig
from handshake.metrics import RunMetrics
from handshake.models import Outcome
from handshake.records import RunRecord, append_record, read_records
from handshake.referee import Verdict
from handshake.runner import RunSpec, build_specs, run_all, with_backoff
from handshake.scenarios import generate_scenarios

MODELS = [ModelConfig(provider="ollama", model="a"), ModelConfig(provider="ollama", model="b")]


def _specs(scenarios: int = 2, repeats: int = 2) -> list[RunSpec]:
    return build_specs(generate_scenarios(0, scenarios), MODELS, repeats)


def _record(spec: RunSpec) -> RunRecord:
    return RunRecord(
        run_id=spec.run_id,
        scenario_id=spec.scenario.id,
        scenario=spec.scenario,
        buyer_model=spec.buyer_model.label,
        seller_model=spec.seller_model.label,
        repeat=spec.repeat,
        verdict=Verdict(outcome=Outcome.NO_DEAL, price=None, reason="x"),
        metrics=RunMetrics(
            outcome=Outcome.NO_DEAL,
            rounds=1,
            buyer_surplus_share=None,
            seller_surplus_share=None,
            missed_deal=False,
            buyer_leaked=False,
            seller_leaked=False,
            buyer_giveaway=False,
            seller_giveaway=False,
        ),
        turns=[],
    )


class _Fatal(BaseException):
    pass


class _RateLimited(Exception):
    status_code = 429


def test_build_specs_count() -> None:
    assert len(_specs()) == 16


def test_run_id_unique_per_spec() -> None:
    ids = [spec.run_id for spec in _specs()]
    assert len(set(ids)) == len(ids)


async def test_run_all_skips_completed(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    specs = _specs()
    append_record(path, _record(specs[0]))
    called: list[str] = []

    async def execute(spec: RunSpec) -> RunRecord:
        called.append(spec.run_id)
        return _record(spec)

    assert await run_all(specs, path, execute) == len(specs) - 1
    assert specs[0].run_id not in called
    assert len(read_records(path)) == len(specs)


async def test_run_all_resumes_after_truncated_line(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    specs = _specs(1, 1)
    append_record(path, _record(specs[0]))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_record(specs[1]).model_dump_json()[:40])

    async def execute(spec: RunSpec) -> RunRecord:
        return _record(spec)

    assert await run_all(specs, path, execute) == len(specs) - 1
    assert [r.run_id for r in read_records(path)] == [s.run_id for s in specs]


async def test_run_all_appends_incrementally(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    calls = 0

    async def execute(spec: RunSpec) -> RunRecord:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("boom")
        return _record(spec)

    with pytest.raises(RuntimeError, match="boom"):
        await run_all(_specs(), path, execute)
    assert len(read_records(path)) == 2


async def test_backoff_retries_on_429_then_succeeds() -> None:
    delays: list[float] = []
    attempts = 0

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async def call() -> str:
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise _RateLimited
        return "ok"

    assert await with_backoff(call, sleep=sleep) == "ok"
    assert delays == [2.0, 4.0]


async def test_backoff_does_not_retry_other_errors() -> None:
    attempts = 0

    async def sleep(delay: float) -> None:
        raise AssertionError("must not sleep")

    async def call() -> str:
        nonlocal attempts
        attempts += 1
        raise ValueError("bad")

    with pytest.raises(ValueError, match="bad"):
        await with_backoff(call, sleep=sleep)
    assert attempts == 1


async def test_backoff_gives_up_after_retries() -> None:
    delays: list[float] = []
    attempts = 0

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async def call() -> str:
        nonlocal attempts
        attempts += 1
        raise _RateLimited(f"attempt {attempts}")

    with pytest.raises(_RateLimited, match="attempt 6"):
        await with_backoff(call, retries=5, sleep=sleep)
    assert delays == [2.0, 4.0, 8.0, 16.0, 32.0]


async def test_run_all_on_error_isolates_failing_run(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    specs = _specs(1, 1)
    errors: list[tuple[str, str]] = []

    async def execute(spec: RunSpec) -> RunRecord:
        if spec is specs[1]:
            raise RuntimeError("boom")
        return _record(spec)

    count = await run_all(
        specs, path, execute, on_error=lambda spec, exc: errors.append((spec.run_id, str(exc)))
    )
    assert errors == [(specs[1].run_id, "boom")]
    assert count == len(specs) - 1
    assert [r.run_id for r in read_records(path)] == [s.run_id for s in specs if s is not specs[1]]


async def test_run_all_on_error_does_not_swallow_base_exceptions(tmp_path: Path) -> None:
    async def execute(spec: RunSpec) -> RunRecord:
        raise _Fatal

    with pytest.raises(_Fatal):
        await run_all(_specs(1, 1), tmp_path / "r.jsonl", execute, on_error=lambda s, e: None)


async def test_run_all_without_on_error_propagates(tmp_path: Path) -> None:
    async def execute(spec: RunSpec) -> RunRecord:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await run_all(_specs(1, 1), tmp_path / "r.jsonl", execute)


async def test_run_all_dedupes_duplicate_specs(tmp_path: Path) -> None:
    specs = _specs(1, 1)
    called: list[str] = []

    async def execute(spec: RunSpec) -> RunRecord:
        called.append(spec.run_id)
        return _record(spec)

    assert await run_all([*specs, *specs], tmp_path / "r.jsonl", execute) == len(specs)
    assert sorted(called) == sorted(s.run_id for s in specs)
