import asyncio
import logging
import re
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

RATE_LIMIT_STATUS = 429
DEFAULT_RETRIES = 5
DEFAULT_BASE_DELAY_S = 2.0
BACKOFF_FACTOR = 2
# Providers such as Groq say how long to wait ("Please try again in 3.3675s" / "450ms").
RETRY_HINT = re.compile(r"try again in (\d+(?:\.\d+)?)\s*(ms|s)\b", re.IGNORECASE)
MS_PER_S = 1000
# The hint is the exact refill time; a little extra avoids retrying a hair too early.
RETRY_MARGIN_S = 0.5


def _is_rate_limited(error: Exception) -> bool:
    return getattr(error, "status_code", None) == RATE_LIMIT_STATUS


def retry_after_s(error: BaseException) -> float | None:
    """Seconds the provider asked us to wait, read from its error message, if it said."""
    match = RETRY_HINT.search(str(error))
    if match is None:
        return None
    seconds = float(match.group(1))
    return seconds / MS_PER_S if match.group(2).lower() == "ms" else seconds


def backoff_total_s(
    retries: int = DEFAULT_RETRIES, base_delay_s: float = DEFAULT_BASE_DELAY_S
) -> float:
    return sum(base_delay_s * BACKOFF_FACTOR**attempt for attempt in range(retries))


def announce_rate_limit_wait(delay_s: float, error: BaseException) -> None:
    logger.warning("provider rate limit: waiting %.1fs, then retrying", delay_s)


def _next_delay_s(error: Exception, attempt: int, base_delay_s: float) -> float:
    hint = retry_after_s(error)
    if hint is not None:
        return hint + RETRY_MARGIN_S
    return base_delay_s * BACKOFF_FACTOR**attempt


async def with_backoff[T](
    call: Callable[[], Awaitable[T]],
    retries: int = DEFAULT_RETRIES,
    base_delay_s: float = DEFAULT_BASE_DELAY_S,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    on_retry: Callable[[float, BaseException], None] | None = None,
) -> T:
    # Total waiting never exceeds backoff_total_s: the caller sizes its turn timeout from it,
    # so a rate-limit wait must never be mistaken for a model timeout.
    budget_s = backoff_total_s(retries, base_delay_s)
    waited_s = 0.0
    for attempt in range(retries):
        try:
            return await call()
        except Exception as error:
            if not _is_rate_limited(error):
                raise
            delay_s = min(_next_delay_s(error, attempt, base_delay_s), budget_s - waited_s)
            waited_s += delay_s
            if on_retry is not None:
                on_retry(delay_s, error)
        await sleep(delay_s)
    return await call()
