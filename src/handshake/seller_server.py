import argparse
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
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from starlette.applications import Starlette

from handshake.config import ModelConfig, pydantic_model
from handshake.models import Offer, Scenario

DEFAULT_BASE_URL = "http://localhost:8001/"
CARD_VERSION = "0.1.0"
LOCAL_HOST = "127.0.0.1"


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


def _agent_card(base_url: str) -> AgentCard:
    return AgentCard(
        name="seller",
        description="Seller agent negotiating a price",
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
    def __init__(self, agent: Agent[None, Offer]) -> None:
        self._agent = agent
        self._histories: dict[str, list[ModelMessage]] = {}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        key = context.context_id or ""
        result = await self._agent.run(
            context.get_user_input(), message_history=self._histories.get(key, [])
        )
        self._histories = {**self._histories, key: result.all_messages()}
        await event_queue.enqueue_event(new_agent_text_message(result.output.model_dump_json()))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError


def build_seller_app(
    scenario: Scenario,
    model: Model,
    base_url: str = DEFAULT_BASE_URL,
    *,
    max_output_tokens: int | None = None,
) -> Starlette:
    settings = ModelSettings(max_tokens=max_output_tokens) if max_output_tokens else None
    agent = Agent(
        model,
        output_type=Offer,
        instructions=seller_instructions(scenario),
        model_settings=settings,
    )
    handler = DefaultRequestHandler(
        agent_executor=SellerExecutor(agent), task_store=InMemoryTaskStore()
    )
    return A2AStarletteApplication(agent_card=_agent_card(base_url), http_handler=handler).build()


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario-json", type=Path, required=True)
    parser.add_argument("--model-config-json", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    scenario = Scenario.model_validate_json(args.scenario_json.read_text())
    cfg = ModelConfig.model_validate_json(args.model_config_json.read_text())
    app = build_seller_app(
        scenario,
        pydantic_model(cfg),
        f"http://{LOCAL_HOST}:{args.port}/",
        max_output_tokens=cfg.max_output_tokens,
    )
    uvicorn.run(app, host=LOCAL_HOST, port=args.port)


if __name__ == "__main__":  # pragma: no cover
    main()
