"""
卡片基类
所有阶段卡片继承此类，只需实现 body_elements() 和 action_buttons()
"""
import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from feishu.config import CARD_TEMPLATE


class BaseCard:
    """飞书卡片基类"""

    card_type: str = "base"  # 子类覆盖
    header_title: str = ""
    header_template: str = "blue"

    def __init__(self, session, mgr):
        """
        session: Session 对象（或兼容 dict 的 .to_dict() 接口）
        mgr:    FeishuManager 实例
        """
        self.session = session
        self.mgr = mgr
        self._open_id = getattr(session, "open_id", "") or session.get("open_id", "")

    # ── 子类必须实现 ──────────────────────────────

    def body_elements(self) -> list[dict]:
        """卡片主体内容区域（markdown / img / hr 等元素列表）"""
        raise NotImplementedError

    def action_buttons(self) -> list[dict]:
        """卡片底部操作按钮（action tag 列表）"""
        return []

    # ── 通用方法 ────────────────────────────────────

    def build(self) -> dict:
        """构建完整卡片 JSON"""
        card = dict(CARD_TEMPLATE)
        card["header"] = {
            "title": {"content": self.header_title, "tag": "plain_text"},
            "template": self.header_template,
        }
        elements = self.body_elements()
        actions = self.action_buttons()
        if actions:
            elements += actions
        card["elements"] = elements
        return card

    def send(self) -> Optional[str]:
        """发送新卡片，返回 message_id"""
        card = self.build()
        mid = self.mgr.send_card(self._open_id, "open_id", card)
        if mid and hasattr(self.session, "card_id"):
            self.session.card_id = mid
            self.session.card_type = self.card_type
        return mid

    def patch(self) -> bool:
        """原地刷新已有卡片"""
        card_id = (
            getattr(self.session, "card_id", "")
            or self.session.get("card_id", "")
            or ""
        )
        if not card_id:
            return False
        ok = self.mgr.update_card(card_id, self.build())
        if not ok:
            # patch 失败，降级为新发
            new_mid = self.mgr.send_card(self._open_id, "open_id", self.build())
            if new_mid and hasattr(self.session, "card_id"):
                self.session.card_id = new_mid
            return bool(new_mid)
        return ok

    def send_or_patch(self) -> Optional[str]:
        """智能选择：有 card_id 则 patch，否则新发"""
        card_id = (
            getattr(self.session, "card_id", "")
            or self.session.get("card_id", "")
            or ""
        )
        if card_id:
            ok = self.mgr.update_card(card_id, self.build())
            if ok:
                return card_id
        return self.send()

    # ── 辅助方法 ────────────────────────────────────

    @staticmethod
    def make_button(text: str, action_type: str, button_type: str = "default", **extra_value) -> dict:
        """快捷创建按钮"""
        value = {"action_type": action_type}
        value.update(extra_value)
        return {
            "tag": "button",
            "text": {"content": text, "tag": "plain_text"},
            "type": button_type,
            "value": value,
        }

    @staticmethod
    def make_action_row(*buttons: dict) -> dict:
        """将多个按钮放入一个 action 行"""
        return {"tag": "action", "actions": list(buttons)}

    @staticmethod
    def make_md(content: str) -> dict:
        return {"tag": "markdown", "content": content}

    @staticmethod
    def make_hr() -> dict:
        return {"tag": "hr"}

    @staticmethod
    def make_img(img_key: str, alt: str = "") -> dict:
        return {
            "tag": "img",
            "img_key": img_key,
            "alt": {"content": alt or "image", "tag": "plain_text"},
        }
