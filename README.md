# Handshake

Two LLM agents built on different frameworks (a Google ADK buyer and a Pydantic AI seller) negotiate a used-car price over the A2A protocol, and a deterministic referee with no LLM scores every negotiation.

<!-- PLACEHOLDER: demo GIF of the replay site. No file exists yet. -->
*GIF coming*

## Install and run

Not published to PyPI. Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

<!-- PLACEHOLDER: replace <repository-url> with the real repository URL once one exists. -->

```
git clone <repository-url> handshake
cd handshake
uv sync
uv run handshake run --config handshake.example.toml --out runs.jsonl
uv run handshake report runs.jsonl
```

The run needs Ollama running locally with the model named in the config (`llama3.2` in `handshake.example.toml`); the Groq entry also needs `GROQ_API_KEY`, either exported in your shell or in a `.env` file in the directory you run from (copy `.env.example` to `.env`; `.env` is git-ignored and an exported variable wins over it). `run` is resumable: re-running the same command skips runs already in `runs.jsonl`. Options: `--scenarios` (default 12), `--seed` (0), `--repeats` (3), `--concurrency` (1).

Replay site data (the site is served over http, not `file://`):

```
uv run handshake report runs.jsonl --json-out site/data/summary.json
cp runs.jsonl site/data/runs.jsonl
python3 -m http.server -d site
```

## Sample output

<!-- PLACEHOLDER: link to a published sample run and hosted replay site. None exists yet. -->
*Sample output link coming*

## How it works

The orchestrator holds the transcript and alternates two independent negotiators, passing each reply to the other side as its next prompt, re-serialised from the parsed `Offer` so only its four fields are relayed; the agents never call each other or the referee. The buyer is an ADK `LlmAgent` (model via `LiteLlm`). The seller negotiator is an ADK `RemoteA2aAgent` client that sends A2A `message/send` to a separate seller process: an a2a-sdk `AgentExecutor` running a Pydantic AI agent. Every turn is a structured `Offer` parsed by the orchestrator; when the negotiation ends, a pure-Python referee judges the finished turn list, and metrics, JSONL records (each carrying its full scenario) and the static replay site follow.

```
                +------------------------+
                |      orchestrator      |
                |  (holds the turn list) |
                +------------------------+
                   |                  |
            prompt |                  | prompt
                   v                  v
  +--------------------------+  +--------------------------+
  | buyer negotiator         |  | seller negotiator        |
  | ADK LlmAgent + LiteLlm   |  | ADK RemoteA2aAgent       |
  +--------------------------+  +--------------------------+
                                             |
                                             | A2A message/send
                                             v
                                +--------------------------+
                                | seller process           |
                                | a2a-sdk AgentExecutor    |
                                | running a Pydantic AI    |
                                | agent                    |
                                +--------------------------+

  After the last turn (agents are not involved):

  orchestrator -> referee (no LLM) -> metrics -> runs.jsonl -> replay site
```

| Concept | Values |
|---|---|
| Scenario | `item`, `public_listing_price`, secret `buyer_max` and `seller_min`, `max_rounds`, `currency`; ZOPA = `buyer_max - seller_min`. Generated from a seed: wide, narrow and zero-overlap cases. |
| Offer | `price` (positive int), `accept`, `walk_away`, `message` |
| Outcome | `deal`, `no_deal`, `invalid_deal`, `protocol_error`, `max_rounds` |

A deal requires `accept=true` matching the other side's last price; a deal outside either side's secret limit is `invalid_deal`.

## Known limits

- **Pinned versions.** `google-adk==2.2.0`, `a2a-sdk[http-server]==0.3.26`, `pydantic-ai-slim==1.107.0`, Python 3.12. The latest versions (ADK 2.15.1, a2a-sdk 1.3.1, fasta2a 2.1.1) did not interoperate in a spike on 2026-11-27: fasta2a emits naive ISO timestamps that a2a-sdk 1.x rejects. Revisit when that is fixed.
- **Pydantic AI served via a2a-sdk.** The seller is a small a2a-sdk `AgentExecutor` around a Pydantic AI agent, not `Agent.to_a2a()` / fasta2a. fasta2a answers `message/send` with a `submitted` task, and ADK's `RemoteA2aAgent` is hard-coded `streaming=False, polling=False`, so it never fetches the result.
- **Small samples.** Results show n and 95% intervals (Wilson for rates, bootstrap for surplus means). The missed-deal rate has no interval. Nothing here is a ranking of models.
- **Denominators.** Deal and missed-deal rates count only feasible runs (ZOPA > 0), reported as `feasible_n`; with no feasible runs they show 0 with interval [0, 1]. Leak and giveaway rates count all runs (`n`).
- **`walk_away`.** It was added to `Offer` (beyond the original price, accept, message) so a no-deal is distinguishable from hitting the round cap.
- **Leak definition.** A leak is an agent's own secret limit appearing in its own message text (the price field is excluded). The regex treats a space as a thousands separator, so `8 000 000` can false-match 8000. Giveaway (offering exactly your own limit) is reported separately from leaks, as `giveaway_rate`.
- **Rate limits.** The run executor (`execute.py`) retries 429s with exponential backoff (2, 4, 8, 16, 32 s) on the orchestrator-side negotiator calls (both buyer and seller), and the seller process retries inside `seller_server.py`. A seller-side 429 that outlasts the seller's ladder reaches the orchestrator without a status code, so it is not retried there. With the CLI's per-run error handler such a run is skipped, not recorded, and retried when the same command is re-run. A sustained 429 that pushes a turn past the per-turn timeout is recorded as a timeout, which scores as `protocol_error`.
- **Reliability.** Model replies are unbounded text except for the `max_output_tokens` cap (default 400) from the config. A small local model (the Ollama smoke run with llama3.2) often ends a negotiation as `protocol_error`, for example by accepting a price different from the one on the table. That is a legitimate measured outcome, not a harness failure. Each role gets exactly one attempt per turn: a reply of either role that is not a valid `Offer` (for the seller, Pydantic AI's output validation fails with no retry) ends the run as `protocol_error`. Infrastructure failures such as transport errors or exhausted 429 retries are not scored: the run is skipped and retried on resume.
- **Replay site.** Vanilla JS modules, no build step, all agent text rendered with `textContent` only. Each replay shows the scenario's hidden limits (`buyer_max`, `seller_min`, ZOPA), labelled as revealed after the run, so leak, giveaway and `invalid_deal` flags can be checked. JSONL files written before records carried the scenario are not readable. Leaderboard rows are sorted by model and role by default; filters apply to the run list, not the leaderboard. Verified in headless Chrome only; browser console capture and real keyboard tab-through were not fully verified.
- **Seller process.** It binds 127.0.0.1 and rejects any Host header other than 127.0.0.1 or localhost. Each run passes a random `--card-token` that the seller puts in its agent card, so a port race at `--concurrency` above 1 cannot pair a run with another run's seller.
- **Groq.** Free-tier limits and the model names in `handshake.example.toml` must be verified in the Groq console before a published run. Keys are read only from the `GROQ_API_KEY` environment variable (a `.env` file in the working directory is loaded into it by `handshake run`). Reasoning models such as `openai/gpt-oss-20b` spend tokens on their chain of thought before answering, so give them a larger `max_output_tokens` (the example config uses 3000). Their reasoning parts are ignored; only the answer part is parsed. A Groq HTTP 400 `tool_use_failed` (the model emitted a malformed tool call) is scored as a seller `protocol_error` rather than skipped.
- **CI.** It cannot run the smoke tests, which need a local Ollama. Run them locally with `uv run pytest -m smoke --no-cov`.

Development checks (the same ones CI runs):

```
uv run ruff check
uv run ruff format --check
uv run pytest
```
