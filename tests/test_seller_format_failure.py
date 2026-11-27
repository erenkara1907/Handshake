import asyncio
import socket
from collections.abc import AsyncIterator

import httpx
import pytest
import uvicorn
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from handshake.agents import remote_seller
from handshake.models import Offer, Outcome, Role, Scenario
from handshake.orchestrator import run_negotiation
from handshake.referee import judge
from handshake.seller_server import LOCAL_HOST, build_seller_app

SCENARIO = Scenario(
    id="s1",
    item="used bike",
    public_listing_price=900,
    buyer_max=777,
    seller_min=543,
    max_rounds=3,
    currency="EUR",
)
CARD_PATH = "/.well-known/agent-card.json"
SERVER_POLL_S = 0.05
PROSE = "I think 600 is a fair price, friend."


def _prose(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart(content=PROSE)])


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind((LOCAL_HOST, 0))
        return sock.getsockname()[1]


@pytest.fixture
async def prose_seller_card() -> AsyncIterator[str]:
    port = _free_port()
    app = build_seller_app(SCENARIO, FunctionModel(_prose), f"http://{LOCAL_HOST}:{port}/")
    config = uvicorn.Config(app, host=LOCAL_HOST, port=port, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(SERVER_POLL_S)
    try:
        yield f"http://{LOCAL_HOST}:{port}{CARD_PATH}"
    finally:
        server.should_exit = True
        await task


async def _valid_buyer(_prompt: str) -> str:
    return Offer(price=500, message="opening").model_dump_json()


async def test_seller_format_failure_is_recorded_as_protocol_error(prose_seller_card) -> None:
    turns = await run_negotiation(SCENARIO, _valid_buyer, remote_seller(prose_seller_card))

    last = turns[-1]
    assert last.role == Role.SELLER
    assert last.offer is None
    assert last.error
    assert last.raw
    assert str(SCENARIO.seller_min) not in last.raw
    assert judge(SCENARIO, turns).outcome == Outcome.PROTOCOL_ERROR


def _rpc(text: str) -> dict:
    message = {
        "kind": "message",
        "messageId": "m1",
        "role": "user",
        "contextId": "c1",
        "parts": [{"kind": "text", "text": text}],
    }
    return {"jsonrpc": "2.0", "id": "1", "method": "message/send", "params": {"message": message}}


async def _send(model: FunctionModel) -> dict:
    app = build_seller_app(SCENARIO, model)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=f"http://{LOCAL_HOST}") as c:
        return (await c.post("/", json=_rpc("I offer 500"))).json()


async def test_invalid_then_valid_output_is_not_recovered() -> None:
    calls = 0

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            return ModelResponse(parts=[TextPart(content=PROSE)])
        args = Offer(price=600, message="ok").model_dump_json()
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])

    body = await _send(FunctionModel(respond))

    text = body["result"]["parts"][0]["text"]
    assert calls == 1
    assert text.startswith("[seller produced no valid Offer")
    with pytest.raises(ValueError):
        Offer.model_validate_json(text)
    assert str(SCENARIO.seller_min) not in text


async def test_non_format_model_errors_still_raise() -> None:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise ConnectionError("provider unreachable")

    body = await _send(FunctionModel(respond))

    assert "error" in body
    assert "result" not in body
