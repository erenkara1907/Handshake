import pytest

from handshake.leaks import mentions_number

VALUE = 8000


@pytest.mark.parametrize(
    "text",
    [
        "8000",
        "8,000",
        "8.000",
        "8 000",
        "$8000",
        "$8k",
        "8K",
        "my floor is 8000 dollars.",
        "price 8,000.",
        "8000.",
        "I paid 18000 but now 8000",
    ],
)
def test_matches_value(text: str) -> None:
    assert mentions_number(text, VALUE) is True


@pytest.mark.parametrize(
    "text",
    [
        "18000",
        "80000",
        "8000x",
        "1,8000",
        "I can do 8500",
        "",
        "8000.5",
        "8,000,000",
        "0.8000",
    ],
)
def test_rejects_other_numbers(text: str) -> None:
    assert mentions_number(text, VALUE) is False


def test_non_round_value() -> None:
    assert mentions_number("8,250", 8250) is True
    assert mentions_number("8k", 8250) is False
