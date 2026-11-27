import asyncio
from collections.abc import Awaitable, Callable

from pydantic import ValidationError

from handshake.models import Offer, Role, Scenario, Turn
from handshake.referee import TURNS_PER_ROUND, is_over

Negotiator = Callable[[str], Awaitable[str]]

DEFAULT_TURN_TIMEOUT_S = 60.0
OFFER_FORMAT_HINT = (
    '{"price": <positive integer>, "accept": <true|false>, '
    '"walk_away": <true|false>, "message": "<short text>"}'
)


def opening_prompt(scenario: Scenario) -> str:
    return (
        f"You are negotiating the purchase of: {scenario.item}. "
        f"The public listing price is {scenario.public_listing_price} {scenario.currency}. "
        f"Make your opening offer. Reply with JSON only, in this format: {OFFER_FORMAT_HINT}"
    )


def _parse_turn(role: Role, raw: str) -> Turn:
    try:
        offer = Offer.model_validate_json(raw)
    except ValidationError as exc:
        reason = f"invalid offer: {exc.error_count()} validation error(s)"
        return Turn(role=role, raw=raw, offer=None, error=reason)
    return Turn(role=role, raw=raw, offer=offer)


async def _take_turn(role: Role, negotiator: Negotiator, prompt: str, timeout_s: float) -> Turn:
    try:
        raw = await asyncio.wait_for(negotiator(prompt), timeout=timeout_s)
    except TimeoutError:
        return Turn(role=role, raw="", offer=None, error=f"timeout after {timeout_s}s")
    return _parse_turn(role, raw)


async def run_negotiation(
    scenario: Scenario,
    buyer: Negotiator,
    seller: Negotiator,
    turn_timeout_s: float = DEFAULT_TURN_TIMEOUT_S,
) -> list[Turn]:
    negotiators = {Role.BUYER: buyer, Role.SELLER: seller}
    turns: list[Turn] = []
    prompt = opening_prompt(scenario)
    while not is_over(scenario, turns):
        role = Role.BUYER if len(turns) % TURNS_PER_ROUND == 0 else Role.SELLER
        turn = await _take_turn(role, negotiators[role], prompt, turn_timeout_s)
        turns = [*turns, turn]
        prompt = turn.raw
    return turns
