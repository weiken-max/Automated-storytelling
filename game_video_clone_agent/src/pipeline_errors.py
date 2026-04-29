import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


def make_task_id(prefix: str = "task") -> str:
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{prefix}_{ts}_{uuid.uuid4().hex[:8]}"


@dataclass
class PipelineErrorPayload:
    task_id: str
    stage: str
    beat_id: str
    subshot_id: str
    error_code: str
    error_message: str
    raw_response_snippet: str


class PipelineStageError(RuntimeError):
    def __init__(
        self,
        task_id: str,
        stage: str,
        error_code: str,
        error_message: str,
        beat_id: str = "",
        subshot_id: str = "",
        raw_response_snippet: str = "",
    ):
        self.payload = PipelineErrorPayload(
            task_id=task_id,
            stage=stage,
            beat_id=beat_id or "",
            subshot_id=subshot_id or "",
            error_code=error_code,
            error_message=error_message,
            raw_response_snippet=(raw_response_snippet or "")[:400],
        )
        loc = self.payload.subshot_id or self.payload.beat_id or "N/A"
        super().__init__(f"{error_code} @ {loc}: {error_message}")

    def to_dict(self):
        return asdict(self.payload)


def dump_pipeline_error(err: PipelineStageError, logs_dir: Path):
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = logs_dir / f"pipeline_error_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(err.to_dict(), f, ensure_ascii=False, indent=2)
    return path
