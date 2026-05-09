"""
大纲审批卡片
展示剧情大纲 + 时长选择器 + 审批按钮
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from feishu.cards.base_card import BaseCard
from feishu.config import ACTION, HEADER_TEMPLATES


def _format_duration_cn(sec: int) -> str:
    from feishu.config import DURATION_SEC_MIN, DURATION_SEC_MAX
    sec = max(DURATION_SEC_MIN, min(DURATION_SEC_MAX, int(sec)))
    m, s = divmod(sec, 60)
    if m >= 60:
        h, m2 = divmod(m, 60)
        return f"{h} 小时 {m2} 分 {s} 秒"
    return f"{m} 分 {s} 秒"


class SynopsisCard(BaseCard):
    card_type = "synopsis"
    header_template = HEADER_TEMPLATES["purple"]

    def __init__(self, session, mgr, synopsis_data: dict, duration_sec: int = 75):
        super().__init__(session, mgr)
        self.synopsis_data = synopsis_data
        self.duration_sec = duration_sec
        self.topic = synopsis_data.get("topic", "") or getattr(session, "topic", "")
        self.header_title = f"📖 剧情大纲：{self.topic}"

    def body_elements(self) -> list[dict]:
        d = self.synopsis_data
        mo = round(self.duration_sec / 60.0, 4)
        industry = d.get("industry_rules") or []
        industry_md = ""
        if industry:
            bullets = "\n".join(f"- {x}" for x in industry[:24])
            industry_md = f"\n\n**📌 行业潜规则**\n{bullets}"

        els = [
            self.make_md(
                f"**🕰️ 时代**：{d.get('era', '?')}\n"
                f"**👤 身份**：{d.get('identity', '?')}{industry_md}"
            ),
            self.make_hr(),
            self.make_md(d.get("synopsis", "")),
            self.make_hr(),
            self.make_md(
                "**⏱️ 成片目标时长**\n"
                "点 **−30 秒** / **+30 秒** 微调，或选下方常用档位；"
                "点 **确认时长并生成定妆照** 后，将把当前选择写入生产管线。\n\n"
                f"**当前选择：**{_format_duration_cn(self.duration_sec)}（约 **{mo:g}** 分钟）"
            ),
        ]
        return els

    def action_buttons(self) -> list[dict]:
        topic = self.topic
        return [
            self.make_action_row(
                self.make_button("−30 秒", ACTION["SYNOPSIS_DURATION_DELTA"], "default", topic=topic, delta=-30),
                self.make_button("+30 秒", ACTION["SYNOPSIS_DURATION_DELTA"], "default", topic=topic, delta=30),
            ),
            self.make_action_row(
                self.make_button("3 分钟", ACTION["SYNOPSIS_DURATION_PRESET"], "default", topic=topic, minutes=3),
                self.make_button("6 分钟", ACTION["SYNOPSIS_DURATION_PRESET"], "primary", topic=topic, minutes=6),
                self.make_button("10 分钟", ACTION["SYNOPSIS_DURATION_PRESET"], "default", topic=topic, minutes=10),
                self.make_button("15 分钟", ACTION["SYNOPSIS_DURATION_PRESET"], "default", topic=topic, minutes=15),
            ),
            self.make_hr(),
            self.make_md("**请选择下一步操作：**"),
            self.make_action_row(
                self.make_button("✅ 确认时长并生成定妆照", ACTION["APPROVE_SYNOPSIS"], "primary", topic=topic),
                self.make_button("✏️ 我要修改大纲", ACTION["REQUEST_REVISE_SYNOPSIS"], "default", topic=topic),
            ),
            self.make_action_row(
                self.make_button("🚫 取消项目，重新选题", ACTION["CANCEL_PROJECT"], "danger", topic=topic),
            ),
        ]
