import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from handshake.agents import build_buyer, remote_seller
from handshake.config import ModelConfig
from handshake.orchestrator import run_negotiation
from handshake.referee import Verdict, judge
from handshake.scenarios import generate_scenarios
from handshake.seller_server import LOCAL_HOST

SMOKE_OLLAMA_MODEL = "llama3.2"
SERVER_START_TIMEOUT_S = 60.0
SERVER_POLL_S = 0.5
MIN_TURNS = 2


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind((LOCAL_HOST, 0))
        return sock.getsockname()[1]


def _wait_for_card(card_url: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + SERVER_START_TIMEOUT_S
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"seller exited early with code {process.returncode}")
        try:
            if httpx.get(card_url).status_code == httpx.codes.OK:
                return
        except httpx.TransportError:
            time.sleep(SERVER_POLL_S)
    raise TimeoutError("seller agent card not reachable")


@pytest.mark.smoke
async def test_one_negotiation_on_ollama(tmp_path: Path):
    scenario = generate_scenarios(0, 1)[0]
    cfg = ModelConfig(provider="ollama", model=SMOKE_OLLAMA_MODEL)
    scenario_file = tmp_path / "scenario.json"
    scenario_file.write_text(scenario.model_dump_json())
    cfg_file = tmp_path / "model.json"
    cfg_file.write_text(cfg.model_dump_json())
    port = _free_port()
    card_url = f"http://{LOCAL_HOST}:{port}/.well-known/agent-card.json"
    cmd = [
        sys.executable, "-m", "handshake.seller_server",
        "--scenario-json", str(scenario_file),
        "--model-config-json", str(cfg_file),
        "--port", str(port),
    ]  # fmt: skip
    process = subprocess.Popen(cmd)
    try:
        _wait_for_card(card_url, process)
        turns = await run_negotiation(scenario, build_buyer(scenario, cfg), remote_seller(card_url))
    finally:
        process.terminate()
        process.wait(timeout=SERVER_START_TIMEOUT_S)

    assert len(turns) >= MIN_TURNS
    assert isinstance(judge(scenario, turns), Verdict)
