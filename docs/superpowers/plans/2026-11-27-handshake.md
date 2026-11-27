# Handshake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An ADK buyer and a Pydantic AI seller negotiate over A2A, a deterministic referee scores each run, and a resumable runner plus static replay site turn many runs into a per-model leaderboard.

**Architecture:** The orchestrator relays turns between two `Negotiator` callables (raw text in, raw text out). The real buyer is an ADK `LlmAgent` (LiteLlm); the real seller is a separate process serving a Pydantic AI agent through an `a2a-sdk` `AgentExecutor`, consumed by ADK `RemoteA2aAgent`. The referee, leak detection and metrics are pure functions tested without any LLM.

**Tech Stack:** Python 3.12, uv, pydantic, `google-adk==2.2.0`, `a2a-sdk[http-server]==0.3.26`, `pydantic-ai-slim[openai]==1.107.0`, litellm (version fixed by `uv.lock` in Task 8), typer, httpx, uvicorn, pytest, pytest-asyncio, pytest-cov, ruff.

**Spec:** `docs/superpowers/specs/2026-11-27-handshake-design.md`

## Global Constraints

- Python, `uv`, `pyproject.toml`, `ruff`, `pytest`, GitHub Actions CI. No notebooks.
- Pins (spec "Verified facts"): `google-adk==2.2.0`, `a2a-sdk[http-server]==0.3.26`, `pydantic-ai-slim==1.107.0`. Never use `Agent.to_a2a()` or `fasta2a`.
- Model and provider come from config; no model names in code.
- No real LLM calls in tests; one `smoke`-marked test per LLM-touching task runs locally against Ollama and is excluded from CI.
- Every agent run has a step budget (`max_rounds`) and a token budget (`max_output_tokens`); on exhaustion the run stops and reports partial results.
- `.env.example` only, never `.env`; keys via environment variables (`GROQ_API_KEY`).
- Wire format of every turn: `Offer(price: int, accept: bool, message: str)`.
- Files under 250 lines, functions under 50, frozen/immutable models, no `print`, no swallowed errors.
- Coverage floor 80% (`--cov-fail-under=80`); `execute.py` is covered by its smoke test only and omitted from the floor.
- Commit steps follow conventional commits; run them only when the user has OK'd committing. No attribution trailer (user config disables it). Never publish to PyPI/Pages/GitHub.

## Review Focus

1. Seller reply is not valid `Offer` JSON (or times out) -> `protocol_error`, run continues to be recorded, no crash (Tasks 3, 6).
2. `accept=true` on the first turn, or with a price different from the opponent's last price -> `protocol_error`, never `deal` (Task 3).
3. Zero-overlap scenario where the agents "agree" on a price -> `invalid_deal`, not a win (Task 3).
4. Leak regex false positives: secret `8000` must not match `18000`, `80000` or `8000x`; must match `8,000`, `8.000`, `8 000`, `$8k` (Task 4).
5. Resume after a crash that left a truncated last JSONL line; completed `run_id`s are never re-run (Tasks 5, 9).

---

### Task 1: Scaffold and core models

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `src/handshake/__init__.py`, `src/handshake/models.py`, `tests/test_models.py`

**Interfaces:**
- Produces (`handshake.models`): `Role(StrEnum)`: `BUYER="buyer"`, `SELLER="seller"`. `Outcome(StrEnum)`: `DEAL`, `NO_DEAL`, `INVALID_DEAL`, `PROTOCOL_ERROR`, `MAX_ROUNDS`. `Offer(BaseModel, frozen)`: `price: int` (>0), `accept: bool = False`, `walk_away: bool = False`, `message: str` (max 1000 chars). `Scenario(BaseModel, frozen)`: `id: str`, `item: str`, `public_listing_price: int`, `buyer_max: int`, `seller_min: int`, `max_rounds: int`, `currency: str`, property `zopa -> int` (`buyer_max - seller_min`). `Turn(BaseModel, frozen)`: `role: Role`, `raw: str`, `offer: Offer | None`, `error: str | None = None`.
- Note (builder call, deviates from spec): `walk_away` is added to `Offer` so `no_deal` is distinguishable from `max_rounds`.

- [ ] **Step 1: `git init`, `uv init --package`, add the pinned dependencies and dev tools; set pytest `asyncio_mode = "auto"`, a `smoke` marker, ruff config, `addopts = "-m 'not smoke' --cov=handshake --cov-fail-under=80"` (relaxed to no floor until Task 5).**
- [ ] **Step 2: Write failing tests in `tests/test_models.py`:** `test_zopa_is_buyer_max_minus_seller_min` (`Scenario(..., buyer_max=9000, seller_min=8000).zopa == 1000`); `test_offer_rejects_non_positive_price` (`price=0` raises `ValidationError`); `test_offer_is_frozen` (assignment raises); `test_offer_defaults` (`accept` and `walk_away` False).
- [ ] **Step 3: Run `uv run pytest tests/test_models.py -v`; expected FAIL (module missing).**
- [ ] **Step 4: Implement the models in `src/handshake/models.py` per Interfaces.**
- [ ] **Step 5: Run the tests; expected 4 passed.**
- [ ] **Step 6: Commit `chore: scaffold project and core models`.**

### Task 2: Scenario generator

**Files:**
- Create: `src/handshake/scenarios.py`, `tests/test_scenarios.py`

**Interfaces:**
- Consumes: `Scenario`.
- Produces: `generate_scenarios(seed: int, count: int = 12) -> list[Scenario]`.

- [ ] **Step 1: Failing tests:** `test_same_seed_same_scenarios` (two calls equal); `test_different_seed_differs`; `test_mix_contains_positive_and_nonpositive_zopa` (`count=12` has at least 3 with `zopa <= 0` and at least 3 with `zopa > 0`); `test_ids_unique`; `test_seller_min_below_listing_price` (for all); `test_all_values_positive_ints`.
- [ ] **Step 2: Run; expected FAIL.**
- [ ] **Step 3: Implement.** Cycle three kinds by index: wide (ZOPA about 25% of listing), narrow (about 3%), none (`seller_min > buyer_max`). Use a `random.Random(seed)` instance, round to whole hundreds, `max_rounds=6`, `currency="USD"`, `item` from a small constant list of used cars.
- [ ] **Step 4: Run; expected 6 passed.**
- [ ] **Step 5: Commit `feat: seeded scenario generator`.**

### Task 3: Referee

**Files:**
- Create: `src/handshake/referee.py`, `tests/test_referee.py`

**Interfaces:**
- Consumes: `Scenario`, `Turn`, `Outcome`, `Role`.
- Produces: `Verdict(BaseModel, frozen)`: `outcome: Outcome`, `price: int | None`, `reason: str`. `is_over(scenario: Scenario, turns: Sequence[Turn]) -> bool`. `judge(scenario: Scenario, turns: Sequence[Turn]) -> Verdict` (valid only when `is_over` is true).
- Rules: buyer speaks first, roles alternate; `2 * max_rounds` turns is the cap. A turn with `offer is None` -> `PROTOCOL_ERROR`. `walk_away` -> `NO_DEAL`. `accept=true` on turn 1 -> `PROTOCOL_ERROR`; `accept=true` whose `price` differs from the previous turn's price -> `PROTOCOL_ERROR`; otherwise agreement price is the previous turn's price. Agreement outside `[seller_min, buyer_max]` -> `INVALID_DEAL`. Cap reached without agreement -> `MAX_ROUNDS`.

- [ ] **Step 1: Failing tests** (helper `t(role, price, accept=False, walk=False)` builds a `Turn`), scenario `buyer_max=9000, seller_min=8000, max_rounds=3`: `test_deal_inside_limits` (buyer 7500, seller 8500, buyer 8500 accept -> `DEAL`, price 8500); `test_accept_on_first_turn_is_protocol_error`; `test_accept_with_mismatched_price_is_protocol_error`; `test_unparseable_turn_is_protocol_error` (`offer=None, error="invalid json"`); `test_agreement_below_seller_min_is_invalid_deal`; `test_agreement_above_buyer_max_is_invalid_deal`; `test_zero_overlap_agreement_is_invalid_deal` (`buyer_max=7000, seller_min=8000`, agreement at 7500); `test_walk_away_is_no_deal`; `test_cap_reached_is_max_rounds` (6 non-accepting turns); `test_is_over_false_mid_negotiation`; `test_is_over_true_after_accept_walk_away_error_or_cap`.
- [ ] **Step 2: Run; expected FAIL.**
- [ ] **Step 3: Implement `is_over` and `judge` as pure functions; split rule checks into small helpers.**
- [ ] **Step 4: Run; expected 11 passed.**
- [ ] **Step 5: Commit `feat: deterministic referee`.**

### Task 4: Leak detection

**Files:**
- Create: `src/handshake/leaks.py`, `tests/test_leaks.py`

**Interfaces:**
- Produces: `mentions_number(text: str, value: int) -> bool` (True when `value` appears as a standalone number in `text`).
- Builder call: a leak means an agent's own secret limit appears in its own message text (not in the `price` field); the spec's wording "opponent's secret" is read as "the leaked party's secret".

- [ ] **Step 1: Failing tests** (value 8000): parametrized true for `"8000"`, `"8,000"`, `"8.000"`, `"8 000"`, `"$8000"`, `"$8k"`, `"8K"`, `"my floor is 8000 dollars."`; parametrized false for `"18000"`, `"80000"`, `"8000x"`, `"1,8000"`, `"I can do 8500"`, `""`; `test_non_round_value` (value 8250 matches `"8,250"`, never `"8k"`).
- [ ] **Step 2: Run; expected FAIL.**
- [ ] **Step 3: Implement with one compiled regex per call built from the digit string with optional `[,. ]` thousands separators, and `(?<![\d,.])` / `(?![\d,.]?\d)` guards; the `k` form only when `value % 1000 == 0`.**
- [ ] **Step 4: Run; expected all pass.**
- [ ] **Step 5: Commit `feat: secret-number leak detection`.**

### Task 5: Metrics, records, aggregation

**Files:**
- Create: `src/handshake/metrics.py`, `src/handshake/records.py`, `src/handshake/stats.py`, `tests/test_metrics.py`, `tests/test_records.py`, `tests/test_stats.py`

**Interfaces:**
- Consumes: `Scenario`, `Turn`, `Verdict`, `Role`, `Outcome`, `mentions_number`.
- Produces (`metrics`): `RunMetrics(BaseModel, frozen)`: `outcome: Outcome`, `rounds: int` (buyer+seller exchanges taken, rounded up), `buyer_surplus_share: float | None`, `seller_surplus_share: float | None` (surplus divided by `zopa`, only for `DEAL`), `missed_deal: bool` (`NO_DEAL` or `MAX_ROUNDS` while `zopa > 0`), `buyer_leaked: bool`, `seller_leaked: bool`, `buyer_giveaway: bool`, `seller_giveaway: bool` (an offer `price` equal to that agent's own limit). `score_run(scenario, verdict, turns) -> RunMetrics`.
- Produces (`records`): `RunRecord(BaseModel, frozen)`: `run_id: str`, `scenario_id: str`, `buyer_model: str`, `seller_model: str`, `repeat: int`, `verdict: Verdict`, `metrics: RunMetrics`, `turns: list[Turn]`. `append_record(path: Path, record: RunRecord) -> None` (one JSON line, flushed). `read_records(path: Path) -> list[RunRecord]` (missing file -> `[]`; a truncated final line is ignored; a corrupt non-final line raises `ValueError` naming the line number).
- Produces (`stats`): `wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]`. `bootstrap_mean_ci(values: Sequence[float], seed: int = 0, n_boot: int = 2000) -> tuple[float, float]`. `GroupStats(BaseModel, frozen)`: `model: str`, `role: Role`, `n: int`, `deal_rate`, `deal_rate_ci`, `leak_rate`, `leak_rate_ci`, `missed_deal_rate`, `mean_surplus_share: float | None`, `surplus_ci: tuple[float, float] | None`. `aggregate(records: Sequence[RunRecord]) -> list[GroupStats]` (one group per `(model, role)`; surplus uses that role's own share over deals only).

- [ ] **Step 1: Failing tests.** metrics: `test_deal_surplus_shares_sum_to_one` (limits 9000/8000, price 8400 -> buyer 0.6, seller 0.4); `test_missed_deal_when_zopa_positive_and_no_deal`; `test_no_missed_deal_when_zopa_nonpositive`; `test_leak_flags_own_secret_in_own_message` (seller message "I can't go below 8,000" -> `seller_leaked`; buyer mentioning 8000 does not set `seller_leaked`); `test_price_field_alone_is_not_a_leak`; `test_giveaway_when_price_equals_own_limit`. records: `test_roundtrip`; `test_missing_file_is_empty`; `test_truncated_last_line_ignored`; `test_corrupt_middle_line_raises_with_line_number`. stats: `test_wilson_known_value` (`wilson_interval(5, 10)` within 0.001 of `(0.237, 0.763)`); `test_wilson_zero_n_is_full_range` (`(0.0, 1.0)`); `test_bootstrap_deterministic_for_seed`; `test_bootstrap_constant_values_collapse`; `test_aggregate_groups_by_model_and_role` (two records, same model as buyer in one and seller in the other -> two groups, each `n == 1`); `test_aggregate_surplus_none_without_deals`.
- [ ] **Step 2: Run; expected FAIL.**
- [ ] **Step 3: Implement the three modules; tighten `pyproject` coverage floor to 80.**
- [ ] **Step 4: Run `uv run pytest -v`; expected all pass, coverage >= 80%.**
- [ ] **Step 5: Commit `feat: run metrics, records and aggregation`.**

### Task 6: Orchestrator

**Files:**
- Create: `src/handshake/orchestrator.py`, `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `Scenario`, `Turn`, `Offer`, `Role`, `is_over`.
- Produces: `Negotiator = Callable[[str], Awaitable[str]]`. `opening_prompt(scenario: Scenario) -> str` (item, public listing price, currency, never the secrets). `run_negotiation(scenario: Scenario, buyer: Negotiator, seller: Negotiator, turn_timeout_s: float = 60.0) -> list[Turn]`.
- Behavior: buyer receives `opening_prompt`, then each side receives the opponent's last raw text. Each reply is parsed with `Offer.model_validate_json`; a `ValidationError` or `asyncio.TimeoutError` becomes `Turn(offer=None, error=<reason>)` and ends the loop via `is_over`. Other exceptions (for example HTTP 429) propagate.

- [ ] **Step 1: Failing tests** with scripted fake negotiators (async functions popping canned JSON strings): `test_runs_until_accept` (turn count and roles alternate starting with buyer); `test_malformed_reply_becomes_error_turn` (second reply `"not json"` -> last turn `offer is None`, `error` set, loop stops); `test_timeout_becomes_error_turn` (negotiator sleeps, `turn_timeout_s=0.01`); `test_stops_at_round_cap` (never accepts, `len(turns) == 2 * max_rounds`); `test_other_exceptions_propagate` (negotiator raises `RuntimeError`); `test_opening_prompt_excludes_secrets` (neither `str(buyer_max)` nor `str(seller_min)` in text).
- [ ] **Step 2: Run; expected FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run; expected 6 passed.**
- [ ] **Step 5: Commit `feat: negotiation orchestrator`.**

### Task 7: Model config and A2A seller server

**Files:**
- Create: `src/handshake/config.py`, `src/handshake/seller_server.py`, `tests/test_config.py`, `tests/test_seller_server.py`, `.env.example`

**Interfaces:**
- Produces (`config`): `ModelConfig(BaseModel, frozen)`: `provider: Literal["ollama", "groq"]`, `model: str`, `max_output_tokens: int = 400`; property `label -> str` (`"<provider>:<model>"`). `ConfigError(Exception)`. `pydantic_model(cfg: ModelConfig) -> OpenAIChatModel` (Ollama base `http://localhost:11434/v1`, Groq base `https://api.groq.com/openai/v1` with `GROQ_API_KEY`). `litellm_id(cfg: ModelConfig) -> str` (`ollama_chat/<model>` or `groq/<model>`). `load_models(path: Path) -> list[ModelConfig]` from a TOML `[[models]]` array.
- Produces (`seller_server`): `seller_instructions(scenario: Scenario) -> str` (contains `seller_min`, the `Offer` JSON contract, never-reveal rule). `build_seller_app(scenario: Scenario, model: Model) -> Starlette` (a2a-sdk `A2AStarletteApplication`, agent card public and free of secrets, history kept per `context_id`, reply sent as a single `Message` whose text is `Offer.model_dump_json()`). `main()` CLI: `python -m handshake.seller_server --scenario-json PATH --model-config-json PATH --port N`.

- [ ] **Step 1: Failing tests.** config: `test_groq_without_key_raises_config_error_naming_variable`; `test_ollama_needs_no_key`; `test_litellm_id_per_provider`; `test_load_models_from_toml`; `test_unknown_provider_rejected`. seller (Pydantic AI `TestModel`/`FunctionModel`, `httpx.AsyncClient(transport=ASGITransport(app=app))`): `test_agent_card_has_no_secret` (GET `/.well-known/agent-card.json`, `str(seller_min)` absent); `test_message_send_returns_message_with_offer_json` (JSON-RPC `message/send`, `result.kind == "message"`, text validates as `Offer`); `test_history_kept_per_context` (two sends with the same `contextId`; the model's second call sees at least 3 messages); `test_instructions_contain_secret_and_never_reveal_rule`.
- [ ] **Step 2: Run; expected FAIL.**
- [ ] **Step 3: Implement. Model the executor on the spike: `await agent.run(context.get_user_input(), message_history=history[context_id])`, store `result.all_messages()`, `event_queue.enqueue_event(new_agent_text_message(result.output.model_dump_json()))`. `cancel` raises `NotImplementedError`.**
- [ ] **Step 4: Run; expected all pass.**
- [ ] **Step 5: Add `.env.example` (`GROQ_API_KEY=`), commit `feat: model config and A2A seller server`.**

### Task 8: ADK buyer and remote-seller adapter

**Files:**
- Create: `src/handshake/agents.py`, `tests/test_agents.py`, `tests/test_smoke.py`

**Interfaces:**
- Consumes: `ModelConfig`, `litellm_id`, `Scenario`, `Negotiator`, `Offer`.
- Produces: `buyer_instructions(scenario: Scenario) -> str` (contains `buyer_max`, the `Offer` contract, never-reveal rule). `build_buyer(scenario: Scenario, cfg: ModelConfig, llm: BaseLlm | None = None) -> Negotiator` (ADK `LlmAgent` with `output_schema=Offer`, `LiteLlm(litellm_id(cfg))` unless `llm` is injected, one `InMemoryRunner` session per negotiator, returns the final text). `remote_seller(card_url: str) -> Negotiator` (ADK `RemoteA2aAgent` through an `InMemoryRunner`, as in the spike; returns the concatenated text parts of the final event).

- [ ] **Step 1: Add `litellm` via `uv add litellm`; confirm `uv run python -c "from google.adk.models.lite_llm import LiteLlm"` succeeds. If it fails, stop and report to the user before continuing (this is the spec's open verification).**
- [ ] **Step 2: Failing tests (no network):** `test_buyer_instructions_contain_secret_and_contract`; `test_buyer_returns_offer_json_from_injected_fake_llm` (subclass `BaseLlm` yielding a canned `Offer` JSON; result validates as `Offer`); `test_remote_seller_returns_seller_text` (serve `build_seller_app` with a `TestModel` via a uvicorn `Server` task on an ephemeral port in the test, call the negotiator, text validates as `Offer`).
- [ ] **Step 3: Failing smoke test `@pytest.mark.smoke test_one_negotiation_on_ollama`: seller subprocess + ADK buyer, both `ollama:llama3.2`, one scenario; assert the transcript has at least 2 turns and `judge` returns a `Verdict` (any outcome).**
- [ ] **Step 4: Run non-smoke; expected FAIL; implement; run; expected pass.**
- [ ] **Step 5: Run `uv run pytest -m smoke -v` with Ollama up; expected pass.**
- [ ] **Step 6: Commit `feat: ADK buyer and A2A seller adapter`.**

### Task 9: Runner and executor

**Files:**
- Create: `src/handshake/runner.py`, `src/handshake/execute.py`, `tests/test_runner.py`

**Interfaces:**
- Consumes: `Scenario`, `ModelConfig`, `RunRecord`, `append_record`, `read_records`.
- Produces (`runner`): `RunSpec(BaseModel, frozen)`: `scenario: Scenario`, `buyer_model: ModelConfig`, `seller_model: ModelConfig`, `repeat: int`; property `run_id -> str` (`"<scenario.id>|<buyer.label>|<seller.label>|<repeat>"`). `build_specs(scenarios: Sequence[Scenario], models: Sequence[ModelConfig], repeats: int) -> list[RunSpec]` (all ordered model pairs, including same model on both sides). `with_backoff(call: Callable[[], Awaitable[T]], retries: int = 5, base_delay_s: float = 2.0, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> T` (retries only on exceptions with `status_code == 429`, exponential delay). `run_all(specs: Sequence[RunSpec], out_path: Path, execute: Callable[[RunSpec], Awaitable[RunRecord]], concurrency: int = 1) -> int` (skips `run_id`s already in `out_path`, appends each record as it completes, returns the number executed).
- Produces (`execute`): `execute_run(spec: RunSpec) -> RunRecord` (starts the seller subprocess on a free port, waits for the agent card, runs `run_negotiation`, `judge`, `score_run`, stops the subprocess in `finally`). Marked `# pragma: no cover`; exercised by the smoke test.

- [ ] **Step 1: Failing tests:** `test_build_specs_count` (2 scenarios x 2 models x 2 repeats == 16); `test_run_id_unique_per_spec`; `test_run_all_skips_completed` (pre-write one record, fake `execute`, only the rest are called); `test_run_all_resumes_after_truncated_line` (append half a JSON line to the file; run proceeds, file reloads cleanly); `test_run_all_appends_incrementally` (a fake `execute` that raises on the third spec leaves two records on disk); `test_backoff_retries_on_429_then_succeeds` (injected `sleep` records delays `[2.0, 4.0]`); `test_backoff_does_not_retry_other_errors`; `test_backoff_gives_up_after_retries` (raises the last 429).
- [ ] **Step 2: Run; expected FAIL; implement; run; expected pass.**
- [ ] **Step 3: Commit `feat: resumable runner with 429 backoff`.**

### Task 10: CLI

**Files:**
- Create: `src/handshake/cli.py`, `tests/test_cli.py`, `handshake.example.toml`
- Modify: `pyproject.toml` (`[project.scripts] handshake = "handshake.cli:app"`)

**Interfaces:**
- Produces: typer app with `run` (`--config PATH`, `--out PATH`, `--scenarios INT = 12`, `--seed INT = 0`, `--repeats INT = 3`, `--concurrency INT = 1`) and `report` (`RUNS PATH`, `--json-out PATH | None`). `report` prints a table of `GroupStats` (model, role, n, deal rate with CI, leak rate with CI, mean surplus share) and, with `--json-out`, writes `{"groups": [GroupStats...], "scenarios": [...]}`.

- [ ] **Step 1: Failing tests (typer `CliRunner`, fixture JSONL written via `append_record`):** `test_report_prints_each_model_role_with_n`; `test_report_json_out_has_groups_key`; `test_report_empty_file_exits_nonzero_with_message`; `test_run_requires_existing_config`.
- [ ] **Step 2: Run; expected FAIL; implement; run; expected pass.**
- [ ] **Step 3: Add `handshake.example.toml` (one Ollama and one Groq model entry using placeholder model names to be verified in the Groq console).**
- [ ] **Step 4: Commit `feat: CLI run and report`.**

### Task 11: Replay site

**Files:**
- Create: `site/index.html`, `site/app.js`, `site/style.css`, `site/data/.gitkeep`, `tests/test_site_contract.py`

**Interfaces:**
- Consumes: `summary.json` from `report --json-out` and `runs.jsonl`, both fetched from `site/data/`.

- [ ] **Step 1: Failing contract test:** `test_summary_json_keys_match_site_expectations` (generate summary from a fixture; assert the key set equals the set `app.js` reads, listed in a constant block at the top of `app.js` that the test parses with a regex).
- [ ] **Step 2: Implement vanilla-JS page: leaderboard table with n and CIs, run list filterable by scenario/outcome, message-by-message player (buyer left, seller right, outcome banner). No framework, no external requests.**
- [ ] **Step 3: Verify manually: write a fixture `site/data/*` from a fake run, `python -m http.server -d site`, open the page, confirm no console errors and the player steps through turns (screenshot via the browser tool).**
- [ ] **Step 4: Run contract test; expected pass. Commit `feat: static replay site`.**

### Task 12: README and CI

**Files:**
- Create: `README.md`, `.github/workflows/ci.yml`

- [ ] **Step 1: CI workflow: checkout, `astral-sh/setup-uv`, `uv sync --frozen`, `uv run ruff check`, `uv run ruff format --check`, `uv run pytest` (smoke excluded by `addopts`).**
- [ ] **Step 2: README in this order: one sentence, GIF placeholder, one-command install, sample output link placeholder, how it works (the Architecture paragraph plus a single diagram), known limits (pinned versions and why, "Pydantic AI served via a2a-sdk", small n, `walk_away` addition, leak definition).**
- [ ] **Step 3: Verify `uv run ruff check && uv run pytest` green locally; paste output. Commit `docs: README and CI`.**

---

## Self-review

- **Spec coverage:** schema (T1-2), referee (T3), leaks and metrics and aggregation (T4-5), orchestrator (T6), seller over a2a-sdk with pins (T7), ADK buyer plus `LiteLlm` verification (T8), resumable runner with 429 backoff and JSONL (T9), CLI (T10), replay site (T11), README/CI (T12). Budgets: step via `max_rounds` (T3, T6), tokens via `max_output_tokens` (T7).
- **Deviations from the spec (flag to the user):** `walk_away` field on `Offer` (T1); leak means own secret in own message (T4).
- **Type consistency:** `Negotiator`, `Verdict`, `RunRecord`, `ModelConfig.label` are defined once and reused unchanged in later tasks.
