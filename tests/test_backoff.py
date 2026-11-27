import pytest

from handshake.backoff import backoff_total_s, retry_after_s, with_backoff

GROQ_MESSAGE = (
    "Rate limit reached for model `openai/gpt-oss-20b` on tokens per minute (TPM): "
    "Limit 8000, Used 7428, Requested 1021. Please try again in 3.3675s. Need more tokens?"
)


class RateLimited(Exception):
    status_code = 429


def _failing_then_ok(message: str, failures: int):
    calls = {"n": 0}

    async def call() -> str:
        calls["n"] += 1
        if calls["n"] <= failures:
            raise RateLimited(message)
        return "ok"

    return call


def test_backoff_total_default_is_62_seconds() -> None:
    assert backoff_total_s(5, 2.0) == 62.0


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (GROQ_MESSAGE, 3.3675),
        ("Please try again in 450ms.", 0.45),
        ("try again in 12s", 12.0),
        ("quota exhausted", None),
        ("", None),
    ],
)
def test_retry_after_is_read_from_the_provider_message(message: str, expected) -> None:
    assert retry_after_s(RateLimited(message)) == expected


async def test_backoff_waits_exactly_as_long_as_the_provider_asks() -> None:
    delays: list[float] = []

    async def sleep(seconds: float) -> None:
        delays.append(seconds)

    result = await with_backoff(_failing_then_ok(GROQ_MESSAGE, 2), sleep=sleep)

    assert result == "ok"
    assert delays == [pytest.approx(3.3675 + 0.5), pytest.approx(3.3675 + 0.5)]


async def test_backoff_without_a_hint_keeps_the_exponential_schedule() -> None:
    delays: list[float] = []

    async def sleep(seconds: float) -> None:
        delays.append(seconds)

    await with_backoff(_failing_then_ok("slow down", 3), sleep=sleep)

    assert delays == [2.0, 4.0, 8.0]


async def test_backoff_never_waits_longer_than_its_total_budget() -> None:
    delays: list[float] = []

    async def sleep(seconds: float) -> None:
        delays.append(seconds)

    huge = "Please try again in 500s."
    with pytest.raises(RateLimited):
        await with_backoff(_failing_then_ok(huge, 99), sleep=sleep)

    assert sum(delays) <= backoff_total_s(5, 2.0)


async def test_backoff_reports_each_wait_through_on_retry() -> None:
    seen: list[tuple[float, str]] = []

    async def sleep(seconds: float) -> None:
        return None

    def on_retry(delay: float, error: BaseException) -> None:
        seen.append((delay, str(error)))

    await with_backoff(_failing_then_ok("slow down", 1), sleep=sleep, on_retry=on_retry)

    assert seen == [(2.0, "slow down")]
