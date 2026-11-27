"""Quiet the expected provider rate-limit noise; keep every real error and our own notices."""

import logging
import sys
import warnings
from collections.abc import Iterator

ADK_EXPERIMENTAL = r".*\[EXPERIMENTAL\].*"
OWN_LOGGER_PREFIX = "handshake"
RATE_LIMIT_STATUS = 429
RATE_LIMIT_MARKERS = ("RateLimitError", "Rate limit reached", "rate_limit_exceeded")
MAX_CHAIN_DEPTH = 10


def _exception_chain(error: BaseException | None) -> Iterator[BaseException]:
    seen = 0
    while error is not None and seen < MAX_CHAIN_DEPTH:
        yield error
        error = error.__cause__ or error.__context__
        seen += 1


def _is_rate_limit(error: BaseException) -> bool:
    text = str(error)
    return getattr(error, "status_code", None) == RATE_LIMIT_STATUS or any(
        marker in text or marker in type(error).__name__ for marker in RATE_LIMIT_MARKERS
    )


class RateLimitNoiseFilter(logging.Filter):
    """Drops third-party records about 429s (ADK and litellm log each retried attempt as an
    error with a traceback). Our own records always pass, and so does every other error."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith(OWN_LOGGER_PREFIX):
            return True
        if any(marker in record.getMessage() for marker in RATE_LIMIT_MARKERS):
            return False
        error = record.exc_info[1] if record.exc_info else None
        return not any(_is_rate_limit(link) for link in _exception_chain(error))


class _StderrHandler(logging.Handler):
    """Writes to whatever sys.stderr is at emit time (stays valid under test runners)."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            sys.stderr.write(self.format(record) + "\n")
        except Exception:
            self.handleError(record)


def configure_logging() -> None:
    # ADK flags its A2A client as experimental on every import/use; it is not actionable here.
    warnings.filterwarnings("ignore", message=ADK_EXPERIMENTAL, category=UserWarning)
    root = logging.getLogger()
    if any(isinstance(handler, _StderrHandler) for handler in root.handlers):
        return
    handler = _StderrHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(RateLimitNoiseFilter())
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    _silence_litellm_banner()


def _silence_litellm_banner() -> None:
    try:
        import litellm
    except ImportError:  # litellm is a declared dependency; tolerate odd installs
        return
    litellm.suppress_debug_info = True
