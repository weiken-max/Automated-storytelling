"""
大纲时长调整 Action
"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
from feishu.config import DEFAULT_DURATION_SECONDS, DURATION_SEC_MAX, DURATION_SEC_MIN
from feishu.synopsis_duration_sync import (
    persist_synopsis_duration_seconds,
    save_synopsis_duration_draft,
)


def _clamp(sec: int) -> int:
    return max(DURATION_SEC_MIN, min(DURATION_SEC_MAX, int(sec)))


def _format_duration_cn(sec: int) -> str:
    m, s = divmod(_clamp(sec), 60)
    if m >= 60:
        h, m2 = divmod(m, 60)
        return f"{h} 小时 {m2} 分 {s} 秒"
    return f"{m} 分 {s} 秒"


def _load_draft(session) -> int:
    """从 session.context_json 读取时长草稿"""
    ctx = getattr(session, "context_json", {}) or {}
    return _clamp(ctx.get("duration_seconds", DEFAULT_DURATION_SECONDS))


def _save_draft(session, sec: int):
    if hasattr(session, "context_json"):
        session.context_json["duration_seconds"] = _clamp(sec)


class SynopsisDurationDeltaAction:
    """±30 秒微调"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        try:
            delta = int(data.get("delta", 0))
        except (TypeError, ValueError):
            delta = 0

        sec = _load_draft(session)
        sec = _clamp(sec + delta)
        _save_draft(session, sec)
        persist_synopsis_duration_seconds(sec)
        t = (data.get("topic", "") or "").strip() or getattr(session, "topic", "")
        if getattr(session, "open_id", None) and t:
            save_synopsis_duration_draft(session.open_id, t, sec)

        # 尝试原地刷新大纲卡片
        card_id = getattr(session, "card_id", "") or ""
        if card_id:
            from feishu.cards.synopsis_card import SynopsisCard
            path = BASE_DIR / "feishu" / "temp_synopsis.json"
            if path.exists():
                try:
                    sd = json.loads(path.read_text(encoding="utf-8"))
                    card = SynopsisCard(session, mgr, sd, sec)
                    card.patch()
                except Exception:
                    pass

        return {"toast": {"type": "success", "content": f"已设为 {_format_duration_cn(sec)}"}}


class SynopsisDurationPresetAction:
    """预设时长（3/6/10/15 分钟）"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        try:
            minutes = float(data.get("minutes", 6))
        except (TypeError, ValueError):
            minutes = 6.0

        sec = _clamp(int(round(minutes * 60)))
        _save_draft(session, sec)
        persist_synopsis_duration_seconds(sec)
        t = (data.get("topic", "") or "").strip() or getattr(session, "topic", "")
        if getattr(session, "open_id", None) and t:
            save_synopsis_duration_draft(session.open_id, t, sec)

        card_id = getattr(session, "card_id", "") or ""
        if card_id:
            from feishu.cards.synopsis_card import SynopsisCard
            path = BASE_DIR / "feishu" / "temp_synopsis.json"
            if path.exists():
                try:
                    sd = json.loads(path.read_text(encoding="utf-8"))
                    card = SynopsisCard(session, mgr, sd, sec)
                    card.patch()
                except Exception:
                    pass

        return {"toast": {"type": "success", "content": f"已设为 {_format_duration_cn(sec)}"}}
