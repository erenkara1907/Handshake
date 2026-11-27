# Handshake: design

Date: 2026-11-27. Source brief: Project 2 in `GLOBAL_PROJECTS.md`.

## Intent

Two agents built with different frameworks negotiate over the A2A protocol. A deterministic referee (no LLM) scores each negotiation. Repeated runs across model pairings produce a "which model negotiates best" table, including secret leakage and missed deals. Audience is global (English README, repo, replay site); portfolio and LinkedIn piece that reinforces course Week 5 (ADK + A2A).

## Goals

- ADK buyer and Pydantic AI seller talk over real A2A, in two separate processes.
- Deterministic referee and metrics, fully unit-tested without any LLM call.
- Resumable async runner producing JSONL; static replay site reads the JSONL.
- Reproducible: seeded scenarios, pinned dependency versions in `uv.lock`.

## Non-goals

- No server-side LLM; users run the CLI with their own keys (Ollama in dev, Groq for published runs).
- No claim of a definitive "winner"; the table shows n and confidence intervals.
- No SaaS-contract scenario in v1 (car only).

## Anti-goals

- A run that "works" but where the referee trusts agent self-reports.
- A deal outside either party's secret limit counted as a win.

## Constraints

- Python, `uv`, `pyproject.toml`, `ruff`, `pytest`, GitHub Actions CI. No notebooks.
- Model and provider come from config; no model names in code.
- No real LLM calls in tests; one `smoke` test runs locally against Ollama.
- Each agent run has a step and token budget; on exhaustion the run stops and reports partial results.
- `.env.example` only; keys via environment variables.

## Verified facts (spike, 2026-11-27)

- ADK consumes a remote agent with `RemoteA2aAgent(name, description, agent_card=<url>/.well-known/agent-card.json)` (`google.adk.agents.remote_a2a_agent`). Its client is hard-coded `streaming=False, polling=False`: it never calls `tasks/get`, so `submitted`/`working` replies return no result.
- Pydantic AI `Agent.to_a2a()` is deprecated in 1.107 and removed in V2; A2A now lives in `fasta2a`. fasta2a always answers `message/send` with a `submitted` task and runs the model afterwards, so the ADK buyer never sees the seller's reply.
- Latest versions do not interoperate: ADK 2.15.1 + a2a-sdk 1.3.1 + fasta2a 2.1.1 fails with `Failed to parse timestamp field` (fasta2a emits naive ISO timestamps, a2a-sdk 1.x requires RFC 3339).
- Working combination: `google-adk==2.2.0`, `a2a-sdk[http-server]==0.3.26`, `pydantic-ai-slim==1.107.0`, with a seller built directly on a2a-sdk (`AgentExecutor` that runs the Pydantic AI agent and enqueues the `Offer` JSON as a synchronous `Message`). Verified round trip over Ollama `llama3.2`.
- Not verified: an ADK `LlmAgent` buyer on Ollama via `LiteLlm` (needs `litellm`). First implementation task.

## Approaches considered

1. **Seller on a2a-sdk executor (chosen).** Same protocol library as ADK, synchronous Message reply works with ADK's non-polling client. Trade-off: not the "idiomatic" Pydantic AI A2A path; README says "Pydantic AI served via a2a-sdk".
2. fasta2a `agent_to_a2a`. Rejected: result never reaches `RemoteA2aAgent`; latest version also breaks on timestamps.
3. ADK seller as well. Rejected: loses the framework mix, which is the project's point. Kept as fallback only.

Versions: pin the course set above (chosen); latest set fails. Revisit when fasta2a/a2a-sdk interop is fixed.

## Design

**Scenario** (frozen Pydantic): `id`, `item`, `public_listing_price`, `buyer_max` (secret), `seller_min` (secret), `max_rounds`, `currency`. Derived `zopa = buyer_max - seller_min` (a deal is possible only when positive). Scenario set mixes wide, narrow and zero-overlap cases; zero-overlap correct outcome is no deal. Generated from a seed.

**Wire format:** every turn is `Offer(price: int, accept: bool, message: str)`. The orchestrator relays turns: ADK buyer `LlmAgent` (structured output) -> `RemoteA2aAgent` -> A2A seller process. Agents never talk to the referee.

**Referee** (pure functions, no LLM). Outcomes: `deal`, `no_deal`, `invalid_deal`, `protocol_error`, `max_rounds`. A deal requires `accept=true` matching the other side's last price. A deal outside either secret limit is `invalid_deal`. Turn order and round limit enforced.

**Metrics:** per-side surplus divided by ZOPA width and the split; missed deals (no deal while ZOPA > 0); rounds to close; text leaks (opponent's secret number in message text, regex over `8000`, `8,000`, `$8k`, `8 000`); behavioural giveaways (offer equal to the agent's own limit), reported separately from leaks. Aggregation per model and role with n, Wilson intervals for rates, bootstrap CIs for surplus means.

**Runner:** async, resumable, backs off on 429, writes JSONL; scenarios x models x both roles x repeats. Measure call count on a small run first, then divide by the Groq daily limit.

**Replay site:** static `index.html` + vanilla JS, leaderboard and message-by-message player from JSONL, GitHub Pages.

## Left to the builder

Package layout, CLI shape (`typer`), exact scenario numbers, prompt wording, JSONL field naming, leak regex edge cases, port allocation for the seller process.

## Build order (TDD)

Schema -> referee outcomes -> leak regex -> aggregation -> orchestrator with fake LLM -> seller process + `LiteLlm` buyer verification -> runner -> replay site. Single-scenario end-to-end after the orchestrator; scale-up after.
