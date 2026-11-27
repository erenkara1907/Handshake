import pytest

from handshake.metrics import score_run
from handshake.models import Offer, Outcome, Role, Scenario, Turn
from handshake.referee import Verdict


def _scenario(buyer_max: int = 9000, seller_min: int = 8000) -> Scenario:
    return Scenario(
        id="s",
        item="bike",
        public_listing_price=10000,
        buyer_max=buyer_max,
        seller_min=seller_min,
        max_rounds=5,
        currency="USD",
    )


def _turn(role: Role, price: int, message: str = "ok", **flags: bool) -> Turn:
    offer = Offer(price=price, message=message, **flags)
    return Turn(role=role, raw=message, offer=offer)


def _verdict(outcome: Outcome, price: int | None = None) -> Verdict:
    return Verdict(outcome=outcome, price=price, reason="r")


def test_deal_surplus_shares_sum_to_one() -> None:
    metrics = score_run(_scenario(), _verdict(Outcome.DEAL, 8400), [])
    assert metrics.buyer_surplus_share == pytest.approx(0.6)
    assert metrics.seller_surplus_share == pytest.approx(0.4)
    assert not metrics.missed_deal


def test_rounds_rounds_up() -> None:
    turns = [_turn(Role.BUYER, 8100), _turn(Role.SELLER, 8900), _turn(Role.BUYER, 8500)]
    metrics = score_run(_scenario(), _verdict(Outcome.NO_DEAL), turns)
    assert metrics.rounds == 2


def test_missed_deal_when_zopa_positive_and_no_deal() -> None:
    for outcome in (Outcome.NO_DEAL, Outcome.MAX_ROUNDS):
        metrics = score_run(_scenario(), _verdict(outcome), [])
        assert metrics.missed_deal
        assert metrics.buyer_surplus_share is None


def test_no_missed_deal_when_zopa_nonpositive() -> None:
    metrics = score_run(_scenario(7000, 8000), _verdict(Outcome.NO_DEAL), [])
    assert not metrics.missed_deal


def test_no_surplus_when_zopa_nonpositive_even_with_deal() -> None:
    metrics = score_run(_scenario(8000, 8000), _verdict(Outcome.DEAL, 8000), [])
    assert metrics.buyer_surplus_share is None
    assert metrics.seller_surplus_share is None


def test_leak_flags_own_secret_in_own_message() -> None:
    turns = [
        _turn(Role.BUYER, 8100, "Is 8000 your floor?"),
        _turn(Role.SELLER, 8900, "I can't go below 8,000"),
    ]
    metrics = score_run(_scenario(), _verdict(Outcome.NO_DEAL), turns)
    assert metrics.seller_leaked
    assert not metrics.buyer_leaked


def test_opponent_mentioning_number_does_not_flag_other_side() -> None:
    turns = [_turn(Role.BUYER, 8100, "I know you need 8000"), _turn(Role.SELLER, 8900)]
    metrics = score_run(_scenario(), _verdict(Outcome.NO_DEAL), turns)
    assert not metrics.seller_leaked


def test_buyer_leak_detected() -> None:
    turns = [_turn(Role.BUYER, 8100, "my budget is 9k")]
    metrics = score_run(_scenario(), _verdict(Outcome.NO_DEAL), turns)
    assert metrics.buyer_leaked


def test_price_field_alone_is_not_a_leak() -> None:
    turns = [_turn(Role.BUYER, 9000, "take it"), _turn(Role.SELLER, 8000, "fine")]
    metrics = score_run(_scenario(), _verdict(Outcome.NO_DEAL), turns)
    assert not metrics.buyer_leaked
    assert not metrics.seller_leaked


def test_turn_without_offer_is_skipped() -> None:
    turns = [Turn(role=Role.BUYER, raw="8000 9000", offer=None, error="bad")]
    metrics = score_run(_scenario(), _verdict(Outcome.PROTOCOL_ERROR), turns)
    assert not metrics.buyer_leaked


def test_giveaway_when_price_equals_own_limit() -> None:
    turns = [_turn(Role.BUYER, 9000), _turn(Role.SELLER, 8000)]
    metrics = score_run(_scenario(), _verdict(Outcome.NO_DEAL), turns)
    assert metrics.buyer_giveaway
    assert metrics.seller_giveaway
    quiet = score_run(_scenario(), _verdict(Outcome.NO_DEAL), [_turn(Role.BUYER, 8500)])
    assert not quiet.buyer_giveaway
