from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from handshake.models import Outcome, Role, Scenario, Turn

TURNS_PER_ROUND = 2


class Verdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcome: Outcome
    price: int | None
    reason: str


def _protocol_error(reason: str) -> Verdict:
    return Verdict(outcome=Outcome.PROTOCOL_ERROR, price=None, reason=reason)


def _expected_role(index: int) -> Role:
    return Role.BUYER if index % TURNS_PER_ROUND == 0 else Role.SELLER


def _judge_agreement(scenario: Scenario, price: int) -> Verdict:
    if scenario.seller_min <= price <= scenario.buyer_max:
        return Verdict(outcome=Outcome.DEAL, price=price, reason="agreement within limits")
    return Verdict(
        outcome=Outcome.INVALID_DEAL,
        price=price,
        reason=f"agreed price {price} outside [{scenario.seller_min}, {scenario.buyer_max}]",
    )


def _judge_turn(scenario: Scenario, turns: Sequence[Turn], index: int) -> Verdict | None:
    turn = turns[index]
    if turn.role != _expected_role(index):
        return _protocol_error(f"turn {index + 1}: unexpected role {turn.role}")
    offer = turn.offer
    if offer is None:
        return _protocol_error(f"turn {index + 1}: {turn.error or 'no valid offer'}")
    if offer.walk_away:
        return Verdict(outcome=Outcome.NO_DEAL, price=None, reason=f"{turn.role} walked away")
    if not offer.accept:
        return None
    previous = turns[index - 1].offer if index > 0 else None
    if previous is None:
        return _protocol_error(f"turn {index + 1}: accept with nothing to accept")
    if offer.price != previous.price:
        return _protocol_error(
            f"turn {index + 1}: accepted {offer.price} but offer on table was {previous.price}"
        )
    return _judge_agreement(scenario, previous.price)


def _first_verdict(scenario: Scenario, turns: Sequence[Turn]) -> Verdict | None:
    allowed = min(len(turns), TURNS_PER_ROUND * scenario.max_rounds)
    for index in range(allowed):
        verdict = _judge_turn(scenario, turns, index)
        if verdict is not None:
            return verdict
    return None


def _cap_reached(scenario: Scenario, turns: Sequence[Turn]) -> bool:
    return len(turns) >= TURNS_PER_ROUND * scenario.max_rounds


def is_over(scenario: Scenario, turns: Sequence[Turn]) -> bool:
    return _first_verdict(scenario, turns) is not None or _cap_reached(scenario, turns)


def judge(scenario: Scenario, turns: Sequence[Turn]) -> Verdict:
    verdict = _first_verdict(scenario, turns)
    if verdict is not None:
        return verdict
    if _cap_reached(scenario, turns):
        return Verdict(
            outcome=Outcome.MAX_ROUNDS, price=None, reason="round limit reached without agreement"
        )
    raise ValueError("negotiation is still in progress")
