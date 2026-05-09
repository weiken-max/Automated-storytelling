"""
Session 模型
封装单个用户项目会话的数据与状态转移逻辑
"""
from dataclasses import dataclass, field
from typing import Optional

# 从 config 导入状态常量
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    STATUS,
    ALLOWED_TRANSITIONS,
    DURATION_SEC_MIN,
    DURATION_SEC_MAX,
)


@dataclass
class Session:
    """一个用户项目会话"""

    session_id: str
    open_id: str
    topic: str = ""
    status: str = STATUS["IDLE"]
    card_id: str = ""
    card_type: str = ""
    prod_progress: dict = field(default_factory=dict)
    error_context: str = ""
    context_json: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    # ── 状态转移 ────────────────────────────────────

    def can_transition_to(self, target: str) -> bool:
        """检查是否允许从当前状态转移到目标状态"""
        allowed = ALLOWED_TRANSITIONS.get(self.status, set())
        return target in allowed

    def transition_to(self, target: str) -> bool:
        """执行状态转移，不合法时抛出 ValueError"""
        if not self.can_transition_to(target):
            allowed = ALLOWED_TRANSITIONS.get(self.status, set())
            raise ValueError(
                f"非法状态转移: {self.status} → {target}，"
                f"只能转移到: {allowed}"
            )
        self.status = target
        return True

    def is_idle(self) -> bool:
        return self.status == STATUS["IDLE"]

    def is_completed(self) -> bool:
        return self.status == STATUS["COMPLETED"]

    def is_in_review(self) -> bool:
        """是否在等待用户审批阶段"""
        return self.status in [
            STATUS["WAITING_SYNOPSIS_APPROVAL"],
            STATUS["WAITING_CHARACTER_APPROVAL"],
            STATUS["WAITING_STORYBOARD_APPROVAL"],
        ]

    def is_producing(self) -> bool:
        """是否在生产中（包括暂停）"""
        return self.status in [
            STATUS["STEP1_WRITING"],
            STATUS["STEP1_READY"],
            STATUS["STEP2_GENERATING"],
            STATUS["STEP2_FAILED"],
            STATUS["STEP2_SUCCESS"],
            STATUS["STEP3_ASSEMBLING"],
            STATUS["PAUSED"],
        ]

    def is_paused(self) -> bool:
        return self.status == STATUS["PAUSED"]

    def is_error(self) -> bool:
        return self.status == STATUS["ERROR"]

    # ── 阶段查询 ────────────────────────────────────

    def get_stage_name(self) -> str:
        """返回人类可读的当前阶段名称"""
        from config import STATUS_HUMAN_SHORT
        return STATUS_HUMAN_SHORT.get(self.status, self.status)

    def get_previous_review_status(self) -> str | None:
        """
        如果当前在 ERROR 状态，返回出错前应处的位置。
        根据上下文推断：有 full_story → 可能在定妆后；无 → 可能在大纲阶段。
        """
        if not self.is_error():
            return None
        # 根据 context_json 里的线索判断
        if self.context_json.get("has_full_story"):
            return STATUS["WAITING_CHARACTER_APPROVAL"]
        if self.context_json.get("has_synopsis"):
            return STATUS["WAITING_SYNOPSIS_APPROVAL"]
        return None

    # ── 上下文读写 ──────────────────────────────────

    def set_context(self, key: str, value):
        self.context_json[key] = value

    def get_context(self, key: str, default=None):
        return self.context_json.get(key, default)

    def get_duration_seconds(self) -> int:
        """从上下文读成片时长（秒），默认 75 秒 (1.25 分钟)"""
        sec = self.get_context("duration_seconds", 75)
        try:
            sec = int(sec)
        except (TypeError, ValueError):
            sec = 75
        return max(DURATION_SEC_MIN, min(DURATION_SEC_MAX, sec))

    def set_duration_seconds(self, sec: int):
        sec = max(DURATION_SEC_MIN, min(DURATION_SEC_MAX, int(sec)))
        self.set_context("duration_seconds", sec)

    # ── 进度管理 ────────────────────────────────────

    def set_progress(self, step: str, current: int, total: int):
        self.prod_progress = {
            "step": step,
            "current": current,
            "total": total,
        }

    def get_progress_pct(self) -> int:
        """获取进度百分比 (0-100)"""
        cur = self.prod_progress.get("current", 0)
        tot = max(1, self.prod_progress.get("total", 1))
        return min(100, int((cur / tot) * 100))

    # ── 工厂方法 ────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        """从字典创建 Session（兼容 session_store 返回的 dict）"""
        return cls(
            session_id=data.get("session_id", ""),
            open_id=data.get("open_id", ""),
            topic=data.get("topic", ""),
            status=data.get("status", STATUS["IDLE"]),
            card_id=data.get("card_id", ""),
            card_type=data.get("card_type", ""),
            prod_progress=data.get("prod_progress") or {},
            error_context=data.get("error_context", ""),
            context_json=data.get("context_json") or {},
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    def to_dict(self) -> dict:
        """转为字典（用于持久化）"""
        return {
            "session_id": self.session_id,
            "open_id": self.open_id,
            "topic": self.topic,
            "status": self.status,
            "card_id": self.card_id,
            "card_type": self.card_type,
            "prod_progress": self.prod_progress,
            "error_context": self.error_context,
            "context_json": self.context_json,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
