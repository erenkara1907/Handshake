from handshake.backoff import backoff_total_s


def test_backoff_total_default_is_62_seconds() -> None:
    assert backoff_total_s(5, 2.0) == 62.0
