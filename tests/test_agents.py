import asyncio
import socket
from collections.abc import AsyncGenerator, AsyncIterator, Callable

import pytest
import uvicorn
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from handshake.agents import build_buyer, buyer_instructions, remote_seller
from handshake.config import ModelConfig
from handshake.models import Offer, Scenario
from handshake.seller_server import LOCAL_HOST, build_seller_app

SCENARIO = Scenario(
    id="s1",
    item="used bike",
    public_listing_price=900,
    buyer_max=777,
    seller_min=543,
    max_rounds=5,
    currency="EUR",
)
CFG = ModelConfig(provider="ollama", model="fake")
CANNED = Offer(price=500, message="opening")
SERVER_START_TIMEOUT_S = 10.0
SERVER_POLL_S = 0.02


class FakeLlm(BaseLlm):
    model: str = "fake"
    seen: list[LlmRequest] = []

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.seen.append(llm_request)
        content = types.Content(role="model", parts=[types.Part(text=CANNED.model_dump_json())])
        yield LlmResponse(content=content)


def _request_text(request: LlmRequest) -> str:
    return " ".join(p.text or "" for c in request.contents for p in c.parts or [])


def test_buyer_instructions_contain_secret_and_contract():
    text = buyer_instructions(SCENARIO)

    assert "777" in text
    assert "used bike" in text
    assert "EUR" in text
    for field in ("price", "accept", "walk_away", "message"):
        assert field in text
    assert "Never reveal" in text
    assert "543" not in text


async def test_buyer_returns_offer_json_from_injected_fake_llm():
    buyer = build_buyer(SCENARIO, CFG, llm=FakeLlm(seen=[]))

    raw = await buyer("Opening prompt")

    assert Offer.model_validate_json(raw) == CANNED


async def test_buyer_keeps_history_across_calls():
    llm = FakeLlm(seen=[])
    buyer = build_buyer(SCENARIO, CFG, llm=llm)

    await buyer("first seller message")
    await buyer("second seller message")

    second_request = _request_text(llm.seen[-1])
    assert "first seller message" in second_request
    assert CANNED.model_dump_json() in second_request
    assert "second seller message" in second_request


class ThoughtLlm(FakeLlm):
    """Mimics reasoning models: a `thought` part followed by the real answer part."""

    answer: str = CANNED.model_dump_json()

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        parts = [types.Part(text="We must make an opening offer, maybe 17000.", thought=True)]
        if self.answer:
            parts.append(types.Part(text=self.answer))
        yield LlmResponse(content=types.Content(role="model", parts=parts))


async def test_buyer_ignores_reasoning_thought_parts():
    buyer = build_buyer(SCENARIO, CFG, llm=ThoughtLlm(seen=[]))

    raw = await buyer("Opening prompt")

    assert Offer.model_validate_json(raw) == CANNED


async def test_buyer_raises_when_only_thought_parts_are_returned():
    buyer = build_buyer(SCENARIO, CFG, llm=ThoughtLlm(seen=[], answer=""))

    with pytest.raises(RuntimeError, match="no text"):
        await buyer("Opening prompt")


async def test_buyer_raises_when_final_event_has_no_text():
    class EmptyLlm(FakeLlm):
        async def generate_content_async(
            self, llm_request: LlmRequest, stream: bool = False
        ) -> AsyncGenerator[LlmResponse, None]:
            yield LlmResponse(content=types.Content(role="model", parts=[]))

    buyer = build_buyer(SCENARIO, CFG, llm=EmptyLlm(seen=[]))

    with pytest.raises(RuntimeError, match="no text"):
        await buyer("hello")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind((LOCAL_HOST, 0))
        return sock.getsockname()[1]


def _seller_model(seen: list[str]) -> FunctionModel:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(repr(messages))
        args = Offer(price=600, message="counter").model_dump_json()
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])

    return FunctionModel(respond)


@pytest.fixture
async def seller_card_url() -> AsyncIterator[str]:
    port = _free_port()
    app = build_seller_app(SCENARIO, _seller_model([]), f"http://{LOCAL_HOST}:{port}/")
    config = uvicorn.Config(app, host=LOCAL_HOST, port=port, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    try:
        async with asyncio.timeout(SERVER_START_TIMEOUT_S):
            while not server.started:
                await asyncio.sleep(SERVER_POLL_S)
        yield f"http://{LOCAL_HOST}:{port}/.well-known/agent-card.json"
    finally:
        server.should_exit = True
        await task


async def test_remote_seller_returns_seller_text(seller_card_url: str):
    seller: Callable = remote_seller(seller_card_url)

    raw = await seller("I offer 500 EUR")

    assert Offer.model_validate_json(raw).price == 600
