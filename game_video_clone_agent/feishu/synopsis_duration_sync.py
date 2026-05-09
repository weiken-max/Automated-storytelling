"""
飞书大纲卡片上选择的成片时长 → 立即写入本地梗概 JSON，
避免 story_planner / Hub 仍读取默认 1.25 分钟。

写入路径：
- feishu/temp_synopsis.json（Hub、run_story_planner_with_mock 读取）
- data/runs/<current>/scripts/temp_synopsis.json（若当前 Run 已存在）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parent.parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))


def _apply_duration_to_file(path: Path, minutes: float) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False
        data["duration"] = round(float(minutes), 4)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def sync_session_duration_from_feishu_synopsis(session) -> None:
    """
    将 feishu/temp_synopsis.json 中的 duration（分钟）同步到 Session，
    避免用户未点「3/6/10/15」预设就直接确认时，Session 仍为默认 75 秒。
    """
    path = _AGENT_ROOT / "feishu" / "temp_synopsis.json"
    if not path.exists() or not hasattr(session, "set_duration_seconds"):
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
        dm = data.get("duration")
        if dm is None:
            return
        sec = int(round(float(dm) * 60))
        session.set_duration_seconds(sec)
    except Exception:
        pass


def persist_synopsis_duration_seconds(duration_seconds: int) -> None:
    """
    将成片时长（秒）换算为分钟后，写入所有已存在的梗概副本。
    """
    from feishu.config import DURATION_SEC_MIN, DURATION_SEC_MAX

    sec = max(DURATION_SEC_MIN, min(DURATION_SEC_MAX, int(duration_seconds)))
    minutes = round(sec / 60.0, 4)

    feishu_path = _AGENT_ROOT / "feishu" / "temp_synopsis.json"
    _apply_duration_to_file(feishu_path, minutes)

    try:
        from src.run_context import get_paths

        paths = get_paths(create_if_missing=False)
        scripts_dir = paths.get("scripts_dir") if paths else None
        if scripts_dir:
            run_path = scripts_dir / "temp_synopsis.json"
            _apply_duration_to_file(run_path, minutes)
    except Exception:
        pass
