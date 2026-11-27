import asyncio
from collections.abc import Awaitable, Callable

RATE_LIMIT_STATUS = 429
DEFAULT_RETRIES = 5
DEFAULT_BASE_DELAY_S = 2.0
BACKOFF_FACTOR = 2


def _is_rate_limited(error: Exception) -> bool:
    return getattr(error, "status_code", None) == RATE_LIMIT_STATUS


def backoff_total_s(
    retries: int = DEFAULT_RETRIES, base_delay_s: float = DEFAULT_BASE_DELAY_S
) -> float:
    return sum(base_delay_s * BACKOFF_FACTOR**attempt for attempt in range(retries))


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
