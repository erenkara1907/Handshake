import asyncio
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx

from handshake.agents import build_buyer, remote_seller
from handshake.backoff import backoff_total_s, with_backoff
from handshake.metrics import score_run
from handshake.models import Scenario
from handshake.orchestrator import DEFAULT_TURN_TIMEOUT_S, Negotiator, run_negotiation
from handshake.records import RunRecord
from handshake.referee import judge
from handshake.runner import RunSpec
from handshake.seller_server import LOCAL_HOST

SERVER_START_TIMEOUT_S = 60.0
SERVER_POLL_S = 0.5
SERVER_STOP_TIMEOUT_S = 10.0
TURN_TIMEOUT_S = DEFAULT_TURN_TIMEOUT_S + backoff_total_s()
CARD_PATH = "/.well-known/agent-card.json"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind((LOCAL_HOST, 0))
        return sock.getsockname()[1]


def _stop(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=SERVER_STOP_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


async def _serves_our_card(client: httpx.AsyncClient, card_url: str, token: str) -> bool:
    try:
        response = await client.get(card_url)
    except httpx.TransportError:
        return False
    if response.status_code != httpx.codes.OK:
        return False
    try:
        card = response.json()
    except ValueError:
        return False
    return isinstance(card, dict) and token in str(card.get("description", ""))


async def _wait_for_card(card_url: str, process: subprocess.Popen, token: str) -> None:
    # A port race at concurrency > 1 can put another run's seller on our port: only a card
    # carrying this run's token, served while our child is alive, counts as ready.
    deadline = time.monotonic() + SERVER_START_TIMEOUT_S
    async with httpx.AsyncClient() as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"seller exited early with code {process.returncode}")
            if await _serves_our_card(client, card_url, token):
                return
            await asyncio.sleep(SERVER_POLL_S)
    raise TimeoutError(f"seller agent card with this run's token not served at {card_url}")


def _with_retries(negotiator: Negotiator) -> Negotiator:
    async def call(prompt: str) -> str:
        return await with_backoff(lambda: negotiator(prompt))

    return call


def _start_seller(
    scenario: Scenario, spec: RunSpec, workdir: Path, port: int, token: str
) -> subprocess.Popen:
    scenario_file = workdir / "scenario.json"
    scenario_file.write_text(scenario.model_dump_json(), encoding="utf-8")
    cfg_file = workdir / "model.json"
    cfg_file.write_text(spec.seller_model.model_dump_json(), encoding="utf-8")
    cmd = [
        sys.executable, "-m", "handshake.seller_server",
        "--scenario-json", str(scenario_file),
        "--model-config-json", str(cfg_file),
        "--port", str(port),
        "--card-token", token,
    ]  # fmt: skip
    return subprocess.Popen(cmd)


async def execute_run(spec: RunSpec) -> RunRecord:  # pragma: no cover
    scenario = spec.scenario
    port = _free_port()
    card_url = f"http://{LOCAL_HOST}:{port}{CARD_PATH}"
    token = uuid.uuid4().hex
    with tempfile.TemporaryDirectory() as tmp:
        process = _start_seller(scenario, spec, Path(tmp), port, token)
        try:
            await _wait_for_card(card_url, process, token)
            buyer = _with_retries(build_buyer(scenario, spec.buyer_model))
            seller = _with_retries(remote_seller(card_url))
            turns = await run_negotiation(scenario, buyer, seller, turn_timeout_s=TURN_TIMEOUT_S)
        finally:
            _stop(process)
    verdict = judge(scenario, turns)
    return RunRecord(
        run_id=spec.run_id,
        scenario_id=scenario.id,
        scenario=scenario,
        buyer_model=spec.buyer_model.label,
        seller_model=spec.seller_model.label,
        repeat=spec.repeat,
        verdict=verdict,
        metrics=score_run(scenario, verdict, turns),
        turns=list(turns),
    )
