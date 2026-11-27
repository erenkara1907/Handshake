import json
import threading
import urllib.request
from pathlib import Path

import pytest
from typer.testing import CliRunner

from handshake import cli
from handshake.cli import app
from handshake.metrics import RunMetrics
from handshake.models import Outcome, Scenario
from handshake.records import RunRecord, append_record
from handshake.referee import Verdict
from handshake.site_server import make_server, prepare_site

runner = CliRunner()

SCENARIO = Scenario(
    id="s",
    item="car",
    public_listing_price=100,
    buyer_max=95,
    seller_min=80,
    max_rounds=5,
    currency="EUR",
)
HTTP_TIMEOUT_S = 5


def _record(scenario_id: str, repeat: int = 0) -> RunRecord:
    return RunRecord(
        run_id=f"{scenario_id}|a|b|{repeat}",
        scenario_id=scenario_id,
        scenario=SCENARIO,
        buyer_model="a",
        seller_model="b",
        repeat=repeat,
        verdict=Verdict(outcome=Outcome.DEAL, price=90, reason="r"),
        metrics=RunMetrics(
            outcome=Outcome.DEAL,
            rounds=1,
            buyer_surplus_share=0.6,
            seller_surplus_share=0.4,
            missed_deal=False,
            buyer_leaked=False,
            seller_leaked=False,
            buyer_giveaway=False,
            seller_giveaway=False,
        ),
        turns=[],
    )


@pytest.fixture
def site_dir(tmp_path: Path) -> Path:
    site = tmp_path / "site"
    (site / "data").mkdir(parents=True)
    (site / "index.html").write_text("<h1>hello</h1>")
    (site / "data" / "stale.json").write_text("{}")
    return site


@pytest.fixture
def runs_file(tmp_path: Path) -> Path:
    path = tmp_path / "runs.jsonl"
    append_record(path, _record("s2"))
    append_record(path, _record("s1", repeat=1))
    return path


def test_prepare_site_writes_summary_and_runs(
    site_dir: Path, runs_file: Path, tmp_path: Path
) -> None:
    dest = tmp_path / "out"

    count = prepare_site(runs_file, dest, site_dir)

    assert count == 2
    summary = json.loads((dest / "data" / "summary.json").read_text())
    assert set(summary) == {"groups", "scenarios"}
    assert summary["scenarios"] == ["s1", "s2"]
    assert len((dest / "data" / "runs.jsonl").read_text().splitlines()) == 2
    assert (dest / "index.html").read_text() == "<h1>hello</h1>"


def test_prepare_site_does_not_copy_stale_data(
    site_dir: Path, runs_file: Path, tmp_path: Path
) -> None:
    dest = tmp_path / "out"

    prepare_site(runs_file, dest, site_dir)

    assert not (dest / "data" / "stale.json").exists()


def test_prepare_site_rejects_missing_or_empty_runs(site_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no records"):
        prepare_site(tmp_path / "missing.jsonl", tmp_path / "out", site_dir)


def test_prepare_site_requires_the_site_folder(runs_file: Path, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="site folder"):
        prepare_site(runs_file, tmp_path / "out", tmp_path / "no-such-site")


def _minimal_site(tmp_path: Path) -> Path:
    site = tmp_path / "minimal-site"
    site.mkdir()
    (site / "index.html").write_text("x")
    return site


def test_summary_matches_report_json_out(runs_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    runner.invoke(app, ["report", str(runs_file), "--json-out", str(out)])
    dest = tmp_path / "served"

    prepare_site(runs_file, dest, _minimal_site(tmp_path))

    assert (dest / "data" / "summary.json").read_text() == out.read_text()


def test_make_server_serves_files_over_http(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("hi")
    server = make_server(tmp_path, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/index.html"
        assert urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_S).read() == b"hi"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=HTTP_TIMEOUT_S)


class FakeServer:
    server_address = ("127.0.0.1", 8123)

    def __init__(self) -> None:
        self.closed = False

    def serve_forever(self) -> None:
        raise KeyboardInterrupt

    def server_close(self) -> None:
        self.closed = True


def _patch_serving(monkeypatch: pytest.MonkeyPatch, server: FakeServer) -> list[str]:
    opened: list[str] = []
    monkeypatch.setattr(cli, "make_server", lambda directory, port: server)
    monkeypatch.setattr(cli.webbrowser, "open", opened.append)
    return opened


def test_serve_prints_url_opens_browser_and_stops_on_ctrl_c(
    runs_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = FakeServer()
    opened = _patch_serving(monkeypatch, server)

    result = runner.invoke(app, ["serve", str(runs_file), "--port", "8123"])

    assert result.exit_code == 0
    assert "http://127.0.0.1:8123/" in result.output
    assert opened == ["http://127.0.0.1:8123/"]
    assert server.closed


def test_serve_no_open_does_not_launch_a_browser(
    runs_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = _patch_serving(monkeypatch, FakeServer())

    result = runner.invoke(app, ["serve", str(runs_file), "--no-open"])

    assert result.exit_code == 0
    assert opened == []


def test_serve_missing_runs_file_exits_with_a_message(tmp_path: Path) -> None:
    result = runner.invoke(app, ["serve", str(tmp_path / "nope.jsonl"), "--no-open"])

    assert result.exit_code == 1
    assert "no records" in result.output


def test_serve_port_in_use_exits_with_a_message(
    runs_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def busy(directory: Path, port: int) -> FakeServer:
        raise OSError("Address already in use")

    monkeypatch.setattr(cli, "make_server", busy)

    result = runner.invoke(app, ["serve", str(runs_file), "--no-open"])

    assert result.exit_code == 1
    assert "port" in result.output.lower()
