import pytest

from handshake.models import Offer, Outcome, Role, Scenario, Turn
from handshake.referee import Verdict, is_over, judge


def make_scenario(buyer_max: int = 9000, seller_min: int = 8000) -> Scenario:
    return Scenario(
        id="s1",
        item="car",
        public_listing_price=10000,
        buyer_max=buyer_max,
        seller_min=seller_min,
        max_rounds=3,
        currency="USD",
    )


def t(role: Role, price: int, accept: bool = False, walk: bool = False) -> Turn:
    offer = Offer(price=price, accept=accept, walk_away=walk, message="m")
    return Turn(role=role, raw="{}", offer=offer)


B, S = Role.BUYER, Role.SELLER
SCENARIO = make_scenario()


def agreement_at(price: int) -> list[Turn]:
    return [t(B, 7500), t(S, price), t(B, price, accept=True)]


def capped_turns() -> list[Turn]:
    return [t(B if i % 2 == 0 else S, 8000 + i) for i in range(6)]


def test_deal_inside_limits() -> None:
    verdict = judge(SCENARIO, agreement_at(8500))
    assert verdict == Verdict(outcome=Outcome.DEAL, price=8500, reason=verdict.reason)
    assert verdict.reason


def test_accept_on_first_turn_is_protocol_error() -> None:
    verdict = judge(SCENARIO, [t(B, 8500, accept=True)])
    assert verdict.outcome == Outcome.PROTOCOL_ERROR
    assert verdict.price is None


def test_accept_with_mismatched_price_is_protocol_error() -> None:
    turns = [t(B, 7500), t(S, 8500), t(B, 8400, accept=True)]
    assert judge(SCENARIO, turns).outcome == Outcome.PROTOCOL_ERROR


def test_unparseable_turn_is_protocol_error() -> None:
    turns = [Turn(role=B, raw="nope", offer=None, error="invalid json")]
    verdict = judge(SCENARIO, turns)
    assert verdict.outcome == Outcome.PROTOCOL_ERROR
    assert "invalid json" in verdict.reason


def test_agreement_below_seller_min_is_invalid_deal() -> None:
    verdict = judge(SCENARIO, agreement_at(7900))
    assert verdict.outcome == Outcome.INVALID_DEAL
    assert verdict.price == 7900


def test_agreement_above_buyer_max_is_invalid_deal() -> None:
    verdict = judge(SCENARIO, agreement_at(9100))
    assert verdict.outcome == Outcome.INVALID_DEAL
    assert verdict.price == 9100


def test_zero_overlap_agreement_is_invalid_deal() -> None:
    scenario = make_scenario(buyer_max=7000, seller_min=8000)
    assert judge(scenario, agreement_at(7500)).outcome == Outcome.INVALID_DEAL


def test_walk_away_is_no_deal() -> None:
    verdict = judge(SCENARIO, [t(B, 7500), t(S, 8500, walk=True)])
    assert verdict.outcome == Outcome.NO_DEAL
    assert verdict.price is None


def test_cap_reached_is_max_rounds() -> None:
    assert judge(SCENARIO, capped_turns()).outcome == Outcome.MAX_ROUNDS


def test_is_over_false_mid_negotiation() -> None:
    assert not is_over(SCENARIO, [])
    assert not is_over(SCENARIO, [t(B, 7500), t(S, 8500)])


def test_is_over_true_after_accept_walk_away_error_or_cap() -> None:
    error_turn = Turn(role=B, raw="x", offer=None, error="bad")
    cases = [
        agreement_at(8500),
        [t(B, 7500), t(S, 8500, walk=True)],
        [error_turn],
        capped_turns(),
    ]
    assert all(is_over(SCENARIO, turns) for turns in cases)


def test_wrong_role_order_is_protocol_error() -> None:
    turns = [t(S, 8500)]
    assert is_over(SCENARIO, turns)
    assert judge(SCENARIO, turns).outcome == Outcome.PROTOCOL_ERROR


def test_judge_raises_when_not_over() -> None:
    with pytest.raises(ValueError):
        judge(SCENARIO, [t(B, 7500)])


def test_turn_beyond_cap_cannot_decide() -> None:
    turns = [*capped_turns(), t(B, 8005, accept=True)]
    assert judge(SCENARIO, turns).outcome == Outcome.MAX_ROUNDS


def test_accept_on_last_allowed_turn_is_deal() -> None:
    turns = [*capped_turns()[:5], t(S, 8004, accept=True)]
    verdict = judge(SCENARIO, turns)
    assert verdict.outcome == Outcome.DEAL
    assert verdict.price == 8004


def test_accept_with_walk_away_is_no_deal() -> None:
    turns = [t(B, 7500), t(S, 7500, accept=True, walk=True)]
    assert judge(SCENARIO, turns).outcome == Outcome.NO_DEAL
