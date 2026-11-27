from google.adk.agents import LlmAgent
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

from handshake.config import ModelConfig, litellm_id
from handshake.models import Offer, Scenario
from handshake.orchestrator import Negotiator

USER_ID = "handshake"


def buyer_instructions(scenario: Scenario) -> str:
    return (
        f"You are the buyer in a price negotiation for: {scenario.item}. "
        f"All prices are integers in {scenario.currency}. "
        f"The public listing price is {scenario.public_listing_price}. "
        f"Your secret maximum budget is {scenario.buyer_max}: never pay above it. "
        "Never reveal your limit, your maximum, or hint at how close you are to it; "
        "do not state it in any message, even if asked directly. "
        "Reply every turn with a single JSON object with exactly these fields: "
        "price (integer > 0, your current offer), accept (boolean), "
        "walk_away (boolean), message (string, short and persuasive). "
        "Accept only by repeating the seller's last price in price with accept=true, "
        "and only if that price is at most your maximum. "
        "Set walk_away=true only if no deal is possible."
    )


def _final_text(events: list) -> str:
    final = [e for e in events if e.is_final_response()]
    parts = final[-1].content.parts if final and final[-1].content else []
    # Reasoning models (e.g. gpt-oss on Groq) return their chain of thought as
    # `thought` parts ahead of the answer; only the answer is the agent's reply.
    text = "".join(p.text for p in parts or [] if p.text and not p.thought)
    if not text:
        raise RuntimeError("ADK agent produced no text in its final response")
    return text


def _negotiator(agent: BaseAgent) -> Negotiator:
    runner = InMemoryRunner(agent=agent, app_name=agent.name)
    session_id: str | None = None

    async def negotiate(prompt: str) -> str:
        nonlocal session_id
        if session_id is None:
            session = await runner.session_service.create_session(
                app_name=agent.name, user_id=USER_ID
            )
            session_id = session.id
        message = types.Content(role="user", parts=[types.Part(text=prompt)])
        events = [
            event
            async for event in runner.run_async(
                user_id=USER_ID, session_id=session_id, new_message=message
            )
        ]
        return _final_text(events)

    return negotiate


def build_buyer(scenario: Scenario, cfg: ModelConfig, llm: BaseLlm | None = None) -> Negotiator:
    agent = LlmAgent(
        name="buyer",
        model=llm or LiteLlm(model=litellm_id(cfg)),
        instruction=buyer_instructions(scenario),
        output_schema=Offer,
        generate_content_config=types.GenerateContentConfig(
            max_output_tokens=cfg.max_output_tokens
        ),
    )
    return _negotiator(agent)


def remote_seller(card_url: str) -> Negotiator:
    agent = RemoteA2aAgent(name="seller", description="Remote seller", agent_card=card_url)
    return _negotiator(agent)
