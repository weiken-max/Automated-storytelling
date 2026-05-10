import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RUNS_ROOT = BASE_DIR / "data" / "runs"
CURRENT_RUN_FILE = RUNS_ROOT / "current_run.json"


def _safe_topic(topic: str | None) -> str:
    raw = (topic or "task").strip()
    allowed = []
    for ch in raw:
        if ch.isalnum() or ch in ("-", "_"):
            allowed.append(ch)
        elif ch in (" ", "　"):
            allowed.append("_")
    name = "".join(allowed).strip("_")
    return name or "task"


def create_run_id(topic: str | None = None) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = _safe_topic(topic)[:20]
    return f"Run_{ts}_{suffix}"


def _run_dir_from_id(run_id: str) -> Path:
    return RUNS_ROOT / run_id


def _ensure_run_dirs(run_dir: Path):
    for sub in ("scripts", "storyboards", "audio", "output", "refs", "logs", "后台"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)


def start_new_run(topic: str | None = None, run_id: str | None = None) -> Path:
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    rid = run_id or create_run_id(topic)
    run_dir = _run_dir_from_id(rid)
    _ensure_run_dirs(run_dir)
    CURRENT_RUN_FILE.write_text(json.dumps({"run_id": rid}, ensure_ascii=False), encoding="utf-8")
    return run_dir


def get_current_run_id() -> str | None:
    if not CURRENT_RUN_FILE.exists():
        return None
    try:
        return json.loads(CURRENT_RUN_FILE.read_text(encoding="utf-8")).get("run_id")
    except Exception:
        return None


def get_current_run_dir() -> Path | None:
    rid = get_current_run_id()
    if not rid:
        return None
    run_dir = _run_dir_from_id(rid)
    return run_dir if run_dir.exists() else None


def get_paths(create_if_missing: bool = False) -> dict[str, Path]:
    run_dir = get_current_run_dir()
    if run_dir is None:
        if not create_if_missing:
            return {}
        run_dir = start_new_run(topic="manual")
    _ensure_run_dirs(run_dir)
    return {
        "run_dir": run_dir,
        "scripts_dir": run_dir / "scripts",
        "storyboards_dir": run_dir / "storyboards",
        "audio_dir": run_dir / "audio",
        "output_dir": run_dir / "output",
        "refs_dir": run_dir / "refs",
        "logs_dir": run_dir / "logs",
    }
