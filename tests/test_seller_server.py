from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from handshake.models import Offer, Scenario
from handshake.seller_server import build_seller_app, seller_instructions

SCENARIO = Scenario(
    id="s1",
    item="used bike",
    public_listing_price=900,
    buyer_max=777,
    seller_min=543,
    max_rounds=5,
    currency="EUR",
)
CARD_PATH = "/.well-known/agent-card.json"


def _rpc(text: str, context_id: str | None = "c1") -> dict:
    message = {
        "kind": "message",
        "messageId": f"m-{text}",
        "role": "user",
        "parts": [{"kind": "text", "text": text}],
    }
    if context_id is not None:
        message["contextId"] = context_id
    return {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "message/send",
        "params": {"message": message},
    }


def _model(seen: list[list[ModelMessage]]) -> FunctionModel:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(list(messages))
        args = Offer(price=600, message="counter").model_dump_json()
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])

    return FunctionModel(respond)


@pytest.fixture
async def client() -> AsyncIterator[tuple[httpx.AsyncClient, list[list[ModelMessage]]]]:
    seen: list[list[ModelMessage]] = []
    app = build_seller_app(SCENARIO, _model(seen))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c, seen


async def test_agent_card_has_no_secret(client) -> None:
    http, _ = client
    response = await http.get(CARD_PATH)
    assert response.status_code == 200
    assert str(SCENARIO.seller_min) not in response.text
    assert str(SCENARIO.buyer_max) not in response.text


async def test_message_send_returns_message_with_offer_json(client) -> None:
    http, _ = client
    body = (await http.post("/", json=_rpc("I offer 500"))).json()
    assert body["result"]["kind"] == "message"
    offer = Offer.model_validate_json(body["result"]["parts"][0]["text"])
    assert offer.price == 600


async def test_history_kept_per_context(client) -> None:
    http, seen = client
    await http.post("/", json=_rpc("first"))
    await http.post("/", json=_rpc("second"))
    assert len(seen[1]) >= 3
    await http.post("/", json=_rpc("other", context_id="c2"))
    assert len(seen[2]) < len(seen[1])


async def test_reply_context_id_carries_history_for_client_without_context(client) -> None:
    http, seen = client
    first = (await http.post("/", json=_rpc("first", context_id=None))).json()
    context_id = first["result"]["contextId"]
    assert context_id
    await http.post("/", json=_rpc("second", context_id=context_id))
    assert len(seen[1]) >= 3


async def test_max_output_tokens_applied() -> None:
    seen: list[AgentInfo] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(info)
        args = Offer(price=1, message="x").model_dump_json()
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])

    app = build_seller_app(SCENARIO, FunctionModel(respond), max_output_tokens=123)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        await c.post("/", json=_rpc("hi"))
    assert seen[0].model_settings["max_tokens"] == 123


def test_instructions_contain_secret_and_never_reveal_rule() -> None:
    text = seller_instructions(SCENARIO)
    assert str(SCENARIO.seller_min) in text
    assert "EUR" in text
    assert "used bike" in text
    assert "never reveal" in text.lower()
    assert "walk_away" in text
    assert "repeat" in text.lower()
    assert str(SCENARIO.buyer_max) not in text
