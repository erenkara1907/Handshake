# Handshake

Two LLM agents built on different frameworks (a Google ADK buyer and a Pydantic AI seller) negotiate a used-car price over the A2A protocol, and a deterministic referee with no LLM scores every negotiation.

<!-- PLACEHOLDER: demo GIF of the replay site. No file exists yet. -->
*GIF coming*

## Install and run

Not published to PyPI. Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```
git clone <repository-url> handshake
cd handshake
uv sync
uv run handshake run --config handshake.example.toml --out runs.jsonl
uv run handshake report runs.jsonl
```

The run needs Ollama running locally with the model named in the config (`llama3.2` in `handshake.example.toml`); the Groq entry also needs `GROQ_API_KEY` in the environment. `run` is resumable: re-running the same command skips runs already in `runs.jsonl`. Options: `--scenarios` (default 12), `--seed` (0), `--repeats` (3), `--concurrency` (1).

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

An orchestrator relays turns between two agents; the agents never talk to the referee. The buyer is an ADK `LlmAgent` (model via `LiteLlm`) that reaches the seller through ADK's `RemoteA2aAgent`. The seller runs as a separate process: an a2a-sdk `AgentExecutor` wrapping a Pydantic AI agent. Every turn is a structured `Offer`. After the negotiation, a pure-Python referee decides the outcome and metrics compute surplus, missed deals and leaks; results are appended to JSONL, which the static replay site reads.

```
                  +------------------------------+
                  |         orchestrator         |
                  +------+---------------+-------+
                         |               |
           turn / reply  |               | transcript
                         v               v
  +----------------------------+   +-------------------+
  | ADK buyer                  |   | referee (no LLM)  |
  | LlmAgent + LiteLlm         |   | -> metrics        |
  +-------------+--------------+   | -> runs.jsonl     |
                | RemoteA2aAgent   | -> replay site    |
                | (A2A, message/send)+-----------------+
                v
  +----------------------------+
  | seller process             |
  | a2a-sdk AgentExecutor      |
  | wrapping a Pydantic AI     |
  | agent                      |
  +----------------------------+
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
- **`walk_away`.** It was added to `Offer` (beyond the original price, accept, message) so a no-deal is distinguishable from hitting the round cap.
- **Leak definition.** A leak is an agent's own secret limit appearing in its own message text (the price field is excluded). The regex treats a space as a thousands separator, so `8 000 000` can false-match 8000. Giveaway (offering exactly your own limit) is reported separately from leaks.
- **Rate limits.** The runner retries 429s with exponential backoff (2, 4, 8, 16, 32 s) on the buyer side and inside the seller process. A seller-side 429 that outlasts the seller's ladder reaches the buyer without a status code, so it is not retried buyer-side. With the CLI's per-run error handler such a run is skipped, not recorded, and retried when the same command is re-run. A sustained seller-side 429 could still appear as a `protocol_error` in the data.
- **Reliability.** Model replies are unbounded text except for the `max_output_tokens` cap (default 400) from the config. A small local model (the Ollama smoke run with llama3.2) often ends a negotiation as `protocol_error`, for example by accepting a price different from the one on the table. That is a legitimate measured outcome, not a harness failure.
- **Replay site.** Vanilla JS modules, no build step, all agent text rendered with `textContent` only. Leaderboard rows are sorted by model and role by default; filters apply to the run list, not the leaderboard. Verified in headless Chrome only; browser console capture and real keyboard tab-through were not fully verified.
- **Groq.** Free-tier limits and the model names in `handshake.example.toml` must be verified in the Groq console before a published run. Keys are read only from the `GROQ_API_KEY` environment variable.
- **CI.** It cannot run the smoke tests, which need a local Ollama. Run them locally with `uv run pytest -m smoke --no-cov`.

Development checks (the same ones CI runs):

```
uv run ruff check
uv run ruff format --check
uv run pytest
```
