"""
飞书大纲卡片上选择的成片时长 → 立即写入本地梗概 JSON，
避免 story_planner / Hub 仍读取错误默认时长。

写入路径：
- feishu/temp_synopsis.json（Hub、run_story_planner_with_mock 读取）
- data/runs/<current>/scripts/temp_synopsis.json（若当前 Run 已存在）

另：synopsis_duration_draft.json 与卡片按钮状态对齐，确认大纲时合并进 temp_synopsis。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parent.parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

SYNOPSIS_DURATION_DRAFT_FILE = _AGENT_ROOT / "feishu" / "synopsis_duration_draft.json"


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


def _clamp_sec(sec: int) -> int:
    from feishu.config import DURATION_SEC_MAX, DURATION_SEC_MIN

    return max(DURATION_SEC_MIN, min(DURATION_SEC_MAX, int(sec)))


def _snap_seconds(sec: int, step: int = 30) -> int:
    return _clamp_sec(int(round(sec / step) * step))


def load_synopsis_duration_drafts_dict() -> dict:
    try:
        if SYNOPSIS_DURATION_DRAFT_FILE.exists():
            return json.loads(SYNOPSIS_DURATION_DRAFT_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [WARN] 读取 synopsis_duration_draft 失败: {e}")
    return {"drafts": {}}


def clear_synopsis_duration_draft(open_id: str) -> None:
    data = load_synopsis_duration_drafts_dict()
    drafts = data.setdefault("drafts", {})
    if open_id in drafts:
        del drafts[open_id]
        try:
            SYNOPSIS_DURATION_DRAFT_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass


def save_synopsis_duration_draft(open_id: str, topic: str, seconds: int) -> None:
    """与 hub_old 卡片逻辑一致：按 open_id 记录当前主题下的成片时长（秒）。"""
    seconds = _clamp_sec(int(seconds))
    data = load_synopsis_duration_drafts_dict()
    drafts = data.setdefault("drafts", {})
    drafts[open_id] = {"topic": topic, "seconds": seconds, "ts": time.time()}
    try:
        SYNOPSIS_DURATION_DRAFT_FILE.parent.mkdir(parents=True, exist_ok=True)
        SYNOPSIS_DURATION_DRAFT_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        print(f"  [WARN] 写入 synopsis_duration_draft 失败: {e}")


def load_synopsis_duration_draft_seconds(open_id: str, topic: str, fallback_seconds: int) -> int:
    data = load_synopsis_duration_drafts_dict()
    rec = (data.get("drafts") or {}).get(open_id)
    if isinstance(rec, dict) and rec.get("topic") == topic and rec.get("seconds") is not None:
        return _clamp_sec(int(rec["seconds"]))
    return _clamp_sec(int(fallback_seconds))


def sync_synopsis_duration_from_draft(open_id: str, topic: str) -> None:
    """将卡片草稿时长写入 feishu/temp_synopsis.json（供定妆 / 剧本扩写读取）。"""
    from feishu.config import DEFAULT_SYNOPSIS_DURATION_MINUTES

    path = _AGENT_ROOT / "feishu" / "temp_synopsis.json"
    if not path.exists():
        return
    try:
        synopsis_data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    fb_sec = _snap_seconds(
        int(round(float(synopsis_data.get("duration", DEFAULT_SYNOPSIS_DURATION_MINUTES)) * 60))
    )
    sec = load_synopsis_duration_draft_seconds(open_id, topic, fb_sec)
    minutes = round(sec / 60.0, 4)
    synopsis_data["duration"] = float(minutes)
    try:
        path.write_text(json.dumps(synopsis_data, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"  [WARN] 回写 temp_synopsis duration 失败: {e}")


def sync_session_duration_from_feishu_synopsis(session) -> None:
    """
    将 feishu/temp_synopsis.json 中的 duration（分钟）同步到 Session。
    若 JSON 无 duration 字段，则使用 DEFAULT_SYNOPSIS_DURATION_MINUTES。
    """
    from feishu.config import DEFAULT_SYNOPSIS_DURATION_MINUTES

    path = _AGENT_ROOT / "feishu" / "temp_synopsis.json"
    if not path.exists() or not hasattr(session, "set_duration_seconds"):
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
        dm = data.get("duration")
        if dm is None:
            dm = DEFAULT_SYNOPSIS_DURATION_MINUTES
        sec = int(round(float(dm) * 60))
        session.set_duration_seconds(sec)
    except Exception:
        pass


def persist_synopsis_duration_seconds(duration_seconds: int) -> None:
    """
    将成片时长（秒）换算为分钟后，写入所有已存在的梗概副本。
    """
    from feishu.config import DURATION_SEC_MAX, DURATION_SEC_MIN

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
