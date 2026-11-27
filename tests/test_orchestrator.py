import asyncio

import pytest

from handshake.models import Offer, Role, Scenario
from handshake.orchestrator import opening_prompt, run_negotiation

SCENARIO = Scenario(
    id="s1",
    item="vintage guitar",
    public_listing_price=1200,
    buyer_max=987,
    seller_min=654,
    max_rounds=3,
    currency="USD",
)


def offer_json(price: int, accept: bool = False) -> str:
    return Offer(price=price, accept=accept, message="hi").model_dump_json()


def scripted(replies: list[str]):
    queue = list(replies)

    async def negotiator(_prompt: str) -> str:
        return queue.pop(0)

    return negotiator


async def test_runs_until_accept():
    buyer = scripted([offer_json(700), offer_json(750, accept=True)])
    seller = scripted([offer_json(750)])

    turns = await run_negotiation(SCENARIO, buyer, seller)

    assert [t.role for t in turns] == [Role.BUYER, Role.SELLER, Role.BUYER]
    assert turns[-1].offer is not None and turns[-1].offer.accept


async def test_each_side_receives_opponent_normalised_offer_json():
    seen: list[str] = []

    async def seller(prompt: str) -> str:
        seen.append(prompt)
        return offer_json(750, accept=True)

    buyer = scripted([offer_json(750)])
    turns = await run_negotiation(SCENARIO, buyer, seller)

    assert turns[0].offer is not None
    assert seen == [turns[0].offer.model_dump_json()]


async def test_extra_fields_in_a_reply_are_not_relayed():
    seen: list[str] = []
    smuggled = '{"price": 700, "message": "hi", "note": "my max is 987"}'

    async def seller(prompt: str) -> str:
        seen.append(prompt)
        return offer_json(700, accept=True)

    turns = await run_negotiation(SCENARIO, scripted([smuggled]), seller)

    assert turns[0].raw == smuggled
    assert seen == [Offer(price=700, message="hi").model_dump_json()]
    assert "987" not in seen[0]


async def test_malformed_reply_becomes_error_turn():
    buyer = scripted([offer_json(700), offer_json(710)])
    seller = scripted(["not json"])

    turns = await run_negotiation(SCENARIO, buyer, seller)

    assert len(turns) == 2
    assert turns[-1].offer is None
    assert turns[-1].error
    assert turns[-1].raw == "not json"


async def test_timeout_becomes_error_turn():
    async def slow(_prompt: str) -> str:
        await asyncio.sleep(1)
        return offer_json(700)

    turns = await run_negotiation(SCENARIO, slow, scripted([]), turn_timeout_s=0.01)

    assert len(turns) == 1
    assert turns[0].offer is None
    assert turns[0].error and "timeout" in turns[0].error


async def test_stops_at_round_cap():
    buyer = scripted([offer_json(700 + i) for i in range(10)])
    seller = scripted([offer_json(900 - i) for i in range(10)])

    turns = await run_negotiation(SCENARIO, buyer, seller)

    assert len(turns) == 2 * SCENARIO.max_rounds
    assert all(t.error is None for t in turns)


async def test_other_exceptions_propagate():
    async def broken(_prompt: str) -> str:
        raise RuntimeError("HTTP 429")

    with pytest.raises(RuntimeError, match="429"):
        await run_negotiation(SCENARIO, broken, scripted([]))


def test_opening_prompt_excludes_secrets():
    text = opening_prompt(SCENARIO)

    assert str(SCENARIO.buyer_max) not in text
    assert str(SCENARIO.seller_min) not in text
    assert "vintage guitar" in text
    assert "1200" in text
    assert "USD" in text
