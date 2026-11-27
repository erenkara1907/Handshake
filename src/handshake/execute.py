import asyncio
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

from handshake.agents import build_buyer, remote_seller
from handshake.metrics import score_run
from handshake.models import Scenario
from handshake.orchestrator import Negotiator, run_negotiation
from handshake.records import RunRecord
from handshake.referee import judge
from handshake.runner import RunSpec, with_backoff
from handshake.seller_server import LOCAL_HOST

SERVER_START_TIMEOUT_S = 60.0
SERVER_POLL_S = 0.5
SERVER_STOP_TIMEOUT_S = 10.0
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


async def _wait_for_card(card_url: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + SERVER_START_TIMEOUT_S
    async with httpx.AsyncClient() as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"seller exited early with code {process.returncode}")
            try:
                if (await client.get(card_url)).status_code == httpx.codes.OK:
                    return
            except httpx.TransportError:
                pass
            await asyncio.sleep(SERVER_POLL_S)
    raise TimeoutError("seller agent card not reachable")


def _with_retries(negotiator: Negotiator) -> Negotiator:
    async def call(prompt: str) -> str:
        return await with_backoff(lambda: negotiator(prompt))

    return call


def _start_seller(scenario: Scenario, spec: RunSpec, workdir: Path, port: int) -> subprocess.Popen:
    scenario_file = workdir / "scenario.json"
    scenario_file.write_text(scenario.model_dump_json(), encoding="utf-8")
    cfg_file = workdir / "model.json"
    cfg_file.write_text(spec.seller_model.model_dump_json(), encoding="utf-8")
    cmd = [
        sys.executable, "-m", "handshake.seller_server",
        "--scenario-json", str(scenario_file),
        "--model-config-json", str(cfg_file),
        "--port", str(port),
    ]  # fmt: skip
    return subprocess.Popen(cmd)


async def execute_run(spec: RunSpec) -> RunRecord:  # pragma: no cover
    scenario = spec.scenario
    port = _free_port()
    card_url = f"http://{LOCAL_HOST}:{port}{CARD_PATH}"
    with tempfile.TemporaryDirectory() as tmp:
        process = _start_seller(scenario, spec, Path(tmp), port)
        try:
            await _wait_for_card(card_url, process)
            buyer = _with_retries(build_buyer(scenario, spec.buyer_model))
            seller = _with_retries(remote_seller(card_url))
            turns = await run_negotiation(scenario, buyer, seller)
        finally:
            _stop(process)
    verdict = judge(scenario, turns)
    return RunRecord(
        run_id=spec.run_id,
        scenario_id=scenario.id,
        buyer_model=spec.buyer_model.label,
        seller_model=spec.seller_model.label,
        repeat=spec.repeat,
        verdict=verdict,
        metrics=score_run(scenario, verdict, turns),
        turns=list(turns),
    )
