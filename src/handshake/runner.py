import asyncio
import itertools
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from handshake.config import ModelConfig
from handshake.models import Scenario
from handshake.records import RunRecord, append_record, read_records

RATE_LIMIT_STATUS = 429
DEFAULT_RETRIES = 5
DEFAULT_BASE_DELAY_S = 2.0
BACKOFF_FACTOR = 2


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


def _is_rate_limited(error: Exception) -> bool:
    return getattr(error, "status_code", None) == RATE_LIMIT_STATUS


async def with_backoff[T](
    call: Callable[[], Awaitable[T]],
    retries: int = DEFAULT_RETRIES,
    base_delay_s: float = DEFAULT_BASE_DELAY_S,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    for attempt in range(retries):
        try:
            return await call()
        except Exception as error:
            if not _is_rate_limited(error):
                raise
        await sleep(base_delay_s * BACKOFF_FACTOR**attempt)
    return await call()


async def run_all(
    specs: Sequence[RunSpec],
    out_path: Path,
    execute: Callable[[RunSpec], Awaitable[RunRecord]],
    concurrency: int = 1,
) -> int:
    done = {record.run_id for record in read_records(out_path)}
    pending = [spec for spec in specs if spec.run_id not in done]
    queue = iter(pending)
    failed = False

    async def worker() -> None:
        nonlocal failed
        for spec in queue:
            if failed:
                return
            try:
                append_record(out_path, await execute(spec))
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
    return len(pending)
