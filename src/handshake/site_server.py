"""Serve the replay site over http for a runs file (the page cannot work from file://)."""

import json
import shutil
from collections.abc import Sequence
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from handshake.records import RunRecord, append_record, read_records
from handshake.stats import aggregate

LOCAL_HOST = "127.0.0.1"
SITE_DIR = Path(__file__).resolve().parents[2] / "site"
DATA_DIR = "data"
SUMMARY_FILE = "summary.json"
RUNS_FILE = "runs.jsonl"
JSON_INDENT = 2


def summary_json(records: Sequence[RunRecord]) -> str:
    """The leaderboard data the replay site reads (also written by `report --json-out`)."""
    payload = {
        "groups": [group.model_dump(mode="json") for group in aggregate(records)],
        "scenarios": sorted({record.scenario_id for record in records}),
    }
    return json.dumps(payload, indent=JSON_INDENT) + "\n"


def prepare_site(runs: Path, dest: Path, site_dir: Path = SITE_DIR) -> int:
    """Copy the site to `dest` and fill `dest/data` from `runs`; returns the record count."""
    if not site_dir.is_dir():
        raise FileNotFoundError(f"site folder not found at {site_dir}")
    records = read_records(runs)
    if not records:
        raise ValueError(f"no records found in {runs}")
    shutil.copytree(site_dir, dest, ignore=shutil.ignore_patterns(DATA_DIR), dirs_exist_ok=True)
    data = dest / DATA_DIR
    data.mkdir(parents=True, exist_ok=True)
    (data / SUMMARY_FILE).write_text(summary_json(records), encoding="utf-8")
    for record in records:
        append_record(data / RUNS_FILE, record)
    return len(records)


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return None


def make_server(directory: Path, port: int) -> ThreadingHTTPServer:
    """An http server for `directory`, bound to loopback only (port 0 picks a free port)."""
    handler = partial(_QuietHandler, directory=str(directory))
    server = ThreadingHTTPServer((LOCAL_HOST, port), handler)
    server.daemon_threads = True
    return server
