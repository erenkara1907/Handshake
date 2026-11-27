from pathlib import Path

import pytest

from handshake.metrics import RunMetrics
from handshake.models import Offer, Outcome, Role, Turn
from handshake.records import RunRecord, append_record, read_records
from handshake.referee import Verdict


def _record(run_id: str = "r1") -> RunRecord:
    return RunRecord(
        run_id=run_id,
        scenario_id="s",
        buyer_model="a",
        seller_model="b",
        repeat=0,
        verdict=Verdict(outcome=Outcome.DEAL, price=8400, reason="ok"),
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
        turns=[Turn(role=Role.BUYER, raw="x", offer=Offer(price=8400, message="hi"))],
    )


def test_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    first, second = _record("r1"), _record("r2")
    append_record(path, first)
    append_record(path, second)
    assert read_records(path) == [first, second]


def test_missing_file_is_empty(tmp_path: Path) -> None:
    assert read_records(tmp_path / "none.jsonl") == []


def test_truncated_last_line_ignored(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    append_record(path, _record("r1"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_record("r2").model_dump_json()[:40])
    assert [r.run_id for r in read_records(path)] == ["r1"]


def test_truncated_last_line_failing_validation_ignored(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    append_record(path, _record("r1"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"run_id": "r2"}')
    assert [r.run_id for r in read_records(path)] == ["r1"]


def test_corrupt_middle_line_raises_with_line_number(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    append_record(path, _record("r1"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    append_record(path, _record("r3"))
    with pytest.raises(ValueError, match="line 2"):
        read_records(path)


def test_corrupt_final_line_with_newline_raises(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    path.write_text("{not json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        read_records(path)
