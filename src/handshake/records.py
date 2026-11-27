from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from handshake.metrics import RunMetrics
from handshake.models import Turn
from handshake.referee import Verdict


class RunRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    scenario_id: str
    buyer_model: str
    seller_model: str
    repeat: int
    verdict: Verdict
    metrics: RunMetrics
    turns: list[Turn]


def _drop_partial_tail(path: Path) -> None:
    if not path.exists():
        return
    data = path.read_bytes()
    if not data or data.endswith(b"\n"):
        return
    path.write_bytes(data[: data.rfind(b"\n") + 1])


def append_record(path: Path, record: RunRecord) -> None:
    _drop_partial_tail(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(record.model_dump_json() + "\n")
        handle.flush()


def read_records(path: Path) -> list[RunRecord]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    has_partial_tail = not text.endswith("\n")
    records: list[RunRecord] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            records.append(RunRecord.model_validate_json(line))
        except ValidationError as error:
            if has_partial_tail and number == len(lines):
                continue
            raise ValueError(f"corrupt record at line {number} of {path}") from error
    return records
