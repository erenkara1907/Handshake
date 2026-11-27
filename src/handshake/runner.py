import asyncio
import itertools
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from handshake.backoff import with_backoff
from handshake.config import ModelConfig
from handshake.models import Scenario
from handshake.records import RunRecord, append_record, read_records

__all__ = ["RunSpec", "build_specs", "run_all", "with_backoff"]


class RunSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario: Scenario
    buyer_model: ModelConfig
    seller_model: ModelConfig
    repeat: int

    @property
    def run_id(self) -> str:
        return (
            f"{self.scenario.id}|{self.buyer_model.label}|{self.seller_model.label}|{self.repeat}"
        )


def build_specs(
    scenarios: Sequence[Scenario], models: Sequence[ModelConfig], repeats: int
) -> list[RunSpec]:
    pairs = list(itertools.product(models, models))
    return [
        RunSpec(scenario=scenario, buyer_model=buyer, seller_model=seller, repeat=repeat)
        for scenario in scenarios
        for buyer, seller in pairs
        for repeat in range(repeats)
    ]


async def run_all(
    specs: Sequence[RunSpec],
    out_path: Path,
    execute: Callable[[RunSpec], Awaitable[RunRecord]],
    concurrency: int = 1,
    on_error: Callable[[RunSpec, Exception], None] | None = None,
) -> int:
    done = {record.run_id for record in read_records(out_path)}
    first_by_id: dict[str, RunSpec] = {}
    for spec in specs:
        first_by_id.setdefault(spec.run_id, spec)
    pending = [spec for run_id, spec in first_by_id.items() if run_id not in done]
    queue = iter(pending)
    failed = False
    executed = 0

    async def run_one(spec: RunSpec) -> None:
        nonlocal executed
        try:
            record = await execute(spec)
        except Exception as error:
            if on_error is None:
                raise
            on_error(spec, error)
            return
        append_record(out_path, record)
        executed += 1

    async def worker() -> None:
        nonlocal failed
        for spec in queue:
            if failed:
                return
            try:
                await run_one(spec)
            except BaseException:
                failed = True
                raise

    workers = [asyncio.create_task(worker()) for _ in range(max(1, concurrency))]
    try:
        await asyncio.gather(*workers)
    except BaseException:
        for task in workers:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        raise
    return executed
