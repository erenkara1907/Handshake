import logging
import warnings
from collections.abc import Iterator

import pytest

from handshake.logging_setup import RateLimitNoiseFilter, configure_logging


class RateLimited(Exception):
    status_code = 429


def _record(name: str, message: str = "boom", error: BaseException | None = None):
    exc_info = (type(error), error, None) if error is not None else None
    return logging.LogRecord(name, logging.ERROR, __file__, 1, message, None, exc_info)


def test_drops_a_third_party_record_whose_exception_is_a_429() -> None:
    record = _record("google_adk.agents", error=RateLimited("slow down"))

    assert RateLimitNoiseFilter().filter(record) is False


def test_drops_a_record_that_wraps_a_429_through_the_cause_chain() -> None:
    wrapper = RuntimeError("Node execution failed")
    wrapper.__cause__ = RateLimited("slow down")

    assert RateLimitNoiseFilter().filter(_record("google_adk.agents", error=wrapper)) is False


def test_drops_litellm_rate_limit_text_even_without_exception_info() -> None:
    message = "litellm.RateLimitError: RateLimitError: GroqException - Rate limit reached"

    assert RateLimitNoiseFilter().filter(_record("LiteLLM", message)) is False


def test_keeps_other_third_party_errors() -> None:
    record = _record("google_adk.agents", error=ValueError("bad input"))

    assert RateLimitNoiseFilter().filter(record) is True


def test_keeps_our_own_messages_even_when_they_mention_rate_limits() -> None:
    record = _record("handshake.backoff", "RateLimitError: waiting 3.4s")

    assert RateLimitNoiseFilter().filter(record) is True


@pytest.fixture
def clean_root_logging() -> Iterator[logging.Logger]:
    # Earlier tests (the CLI `run` command) leave our handler installed; start from none and
    # restore the root logger afterwards so nothing leaks either way.
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    root.handlers = [h for h in root.handlers if type(h).__name__ != "_StderrHandler"]
    yield root
    root.handlers = saved_handlers
    root.setLevel(saved_level)


def test_configure_logging_installs_one_filtered_handler(clean_root_logging) -> None:
    before = list(clean_root_logging.handlers)

    configure_logging()
    configure_logging()
    added = [h for h in clean_root_logging.handlers if h not in before]

    assert len(added) == 1
    assert any(isinstance(f, RateLimitNoiseFilter) for f in added[0].filters)


def test_configured_handler_prints_our_notice_but_not_a_provider_429(
    clean_root_logging, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging()

    logging.getLogger("handshake.backoff").warning("provider rate limit: waiting 3.4s")
    logging.getLogger("google_adk.agents").error("failed", exc_info=RateLimited("slow down"))

    captured = capsys.readouterr().err
    assert "provider rate limit: waiting 3.4s" in captured
    assert "failed" not in captured


def test_configure_logging_silences_adk_experimental_warnings(clean_root_logging) -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        configure_logging()
        warnings.warn("[EXPERIMENTAL] RemoteA2aAgent is experimental", UserWarning, stacklevel=1)
        warnings.warn("something else entirely", UserWarning, stacklevel=1)

    assert [str(w.message) for w in caught] == ["something else entirely"]
