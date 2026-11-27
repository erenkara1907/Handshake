import math
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from handshake.leaks import mentions_number
from handshake.models import Outcome, Role, Scenario, Turn
from handshake.referee import TURNS_PER_ROUND, Verdict

MISSED_OUTCOMES = (Outcome.NO_DEAL, Outcome.MAX_ROUNDS)


class RunMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcome: Outcome
    rounds: int
    buyer_surplus_share: float | None
    seller_surplus_share: float | None
    missed_deal: bool
    buyer_leaked: bool
    seller_leaked: bool
    buyer_giveaway: bool
    seller_giveaway: bool


def _surplus_shares(scenario: Scenario, verdict: Verdict) -> tuple[float | None, float | None]:
    if verdict.outcome != Outcome.DEAL or verdict.price is None or scenario.zopa <= 0:
        return None, None
    buyer = (scenario.buyer_max - verdict.price) / scenario.zopa
    seller = (verdict.price - scenario.seller_min) / scenario.zopa
    return buyer, seller


def _leaked(turns: Sequence[Turn], role: Role, secret: int) -> bool:
    return any(
        mentions_number(turn.offer.message, secret)
        for turn in turns
        if turn.role == role and turn.offer is not None
    )


def _gave_away(turns: Sequence[Turn], role: Role, limit: int) -> bool:
    return any(
        turn.offer.price == limit for turn in turns if turn.role == role and turn.offer is not None
    )


def score_run(scenario: Scenario, verdict: Verdict, turns: Sequence[Turn]) -> RunMetrics:
    buyer_share, seller_share = _surplus_shares(scenario, verdict)
    return RunMetrics(
        outcome=verdict.outcome,
        rounds=math.ceil(len(turns) / TURNS_PER_ROUND),
        buyer_surplus_share=buyer_share,
        seller_surplus_share=seller_share,
        missed_deal=verdict.outcome in MISSED_OUTCOMES and scenario.zopa > 0,
        buyer_leaked=_leaked(turns, Role.BUYER, scenario.buyer_max),
        seller_leaked=_leaked(turns, Role.SELLER, scenario.seller_min),
        buyer_giveaway=_gave_away(turns, Role.BUYER, scenario.buyer_max),
        seller_giveaway=_gave_away(turns, Role.SELLER, scenario.seller_min),
    )
