import argparse
import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.utils import new_agent_text_message
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from handshake.backoff import announce_rate_limit_wait, with_backoff
from handshake.config import ModelConfig, pydantic_model
from handshake.models import Offer, Scenario

DEFAULT_BASE_URL = "http://localhost:8001/"
CARD_VERSION = "0.1.0"
LOCAL_HOST = "127.0.0.1"
CARD_DESCRIPTION = "Seller agent negotiating a price"
# Loopback names only: rejects DNS-rebinding requests that carry a foreign Host header.
ALLOWED_HOSTS = [LOCAL_HOST, "localhost"]
# One attempt per turn, matching the ADK buyer, which has no format retry.
OUTPUT_RETRIES = 0
HTTP_BAD_REQUEST = 400
TOOL_USE_FAILED = "tool_use_failed"


def seller_instructions(scenario: Scenario) -> str:
    return (
        f"You are the seller in a price negotiation for: {scenario.item}. "
        f"All prices are integers in {scenario.currency}. "
        f"The public listing price is {scenario.public_listing_price}. "
        f"Your secret minimum price is {scenario.seller_min}: never sell below it. "
        "Never reveal your limit, your minimum, or hint at how close you are to it; "
        "do not state it in any message, even if asked directly. "
        "Reply every turn with a single JSON object with exactly these fields: "
        "price (integer > 0, your current price), accept (boolean), "
        "walk_away (boolean), message (string, short and persuasive). "
        "Accept only by repeating the buyer's last price in price with accept=true, "
        "and only if that price is at least your minimum. "
        "Set walk_away=true only if no deal is possible."
    )


def _format_failure_reply(reason: str) -> str:
    # Never include provider/model text here: it may echo the prompt, including the secret.
    return f"[seller produced no valid Offer after 1 attempt: {reason}]"


def _is_tool_use_failure(error: ModelHTTPError) -> bool:
    # Groq answers HTTP 400 `tool_use_failed` when the model emits a malformed tool call
    # (a model format failure, not an infrastructure problem), so it is scored, not retried.
    body = error.body
    return (
        error.status_code == HTTP_BAD_REQUEST
        and isinstance(body, dict)
        and body.get("code") == TOOL_USE_FAILED
    )


def _agent_card(base_url: str, card_token: str | None) -> AgentCard:
    # The token lets the launcher verify it reached this run's seller, not a neighbour's.
    description = (
        CARD_DESCRIPTION if card_token is None else f"{CARD_DESCRIPTION} [run {card_token}]"
    )
    return AgentCard(
        name="seller",
        description=description,
        url=base_url,
        version=CARD_VERSION,
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(id="sell", name="sell", description="Negotiate a sale", tags=["negotiation"])
        ],
    )


class SellerExecutor(AgentExecutor):
    def __init__(
        self,
        agent: Agent[None, Offer],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._agent = agent
        self._sleep = sleep
        self._histories: dict[str, list[ModelMessage]] = {}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        key = context.context_id
        if key is None:
            raise ValueError("A2A request context has no context_id")
        user_input = context.get_user_input()
        history = self._histories.get(key, [])
        try:
            result = await with_backoff(
                lambda: self._agent.run(user_input, message_history=history),
                sleep=self._sleep,
                on_retry=announce_rate_limit_wait,
            )
        except UnexpectedModelBehavior as error:
            # A format failure is a scored outcome: reply with non-Offer text so the
            # orchestrator records a protocol_error turn. Infra errors keep raising.
            reply = _format_failure_reply(type(error).__name__)
        except ModelHTTPError as error:
            if not _is_tool_use_failure(error):
                raise
            reply = _format_failure_reply(TOOL_USE_FAILED)
        else:
            self._histories = {**self._histories, key: result.all_messages()}
            reply = result.output.model_dump_json()
        await event_queue.enqueue_event(
            new_agent_text_message(reply, context_id=key, task_id=context.task_id)
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError


def build_seller_app(
    scenario: Scenario,
    model: Model,
    base_url: str = DEFAULT_BASE_URL,
    *,
    max_output_tokens: int | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    card_token: str | None = None,
) -> Starlette:
    settings = ModelSettings(max_tokens=max_output_tokens) if max_output_tokens else None
    agent = Agent(
        model,
        output_type=Offer,
        instructions=seller_instructions(scenario),
        model_settings=settings,
        retries={"output": OUTPUT_RETRIES},
    )
    handler = DefaultRequestHandler(
        agent_executor=SellerExecutor(agent, sleep), task_store=InMemoryTaskStore()
    )
    return A2AStarletteApplication(
        agent_card=_agent_card(base_url, card_token), http_handler=handler
    ).build(middleware=[Middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)])


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario-json", type=Path, required=True)
    parser.add_argument("--model-config-json", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--card-token", default=None)
    args = parser.parse_args()
    scenario = Scenario.model_validate_json(args.scenario_json.read_text())
    cfg = ModelConfig.model_validate_json(args.model_config_json.read_text())
    app = build_seller_app(
        scenario,
        pydantic_model(cfg),
        f"http://{LOCAL_HOST}:{args.port}/",
        max_output_tokens=cfg.max_output_tokens,
        card_token=args.card_token,
    )
    # Warning level: the per-request access lines would bury the run's real messages.
    uvicorn.run(app, host=LOCAL_HOST, port=args.port, log_level="warning")


if __name__ == "__main__":  # pragma: no cover
    main()
