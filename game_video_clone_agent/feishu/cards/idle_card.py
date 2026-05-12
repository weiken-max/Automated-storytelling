"""
空闲态卡片（选题盲盒）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from feishu.cards.base_card import BaseCard
from feishu.config import ACTION, HEADER_TEMPLATES


class IdleCard(BaseCard):
    card_type = "idle"
    header_title = "🎬 今日好戏开场"
    header_template = HEADER_TEMPLATES["turquoise"]

    def __init__(
        self,
        session,
        mgr,
        topics: list[str] | None = None,
        is_busy: bool = False,
        busy_topic: str = "",
        *,
        variant: str = "topics",
        show_resume: bool = False,
        resume_topic: str = "",
        resume_status_label: str = "",
    ):
        super().__init__(session, mgr)
        self.topics = topics or []
        self.is_busy = is_busy
        self.busy_topic = busy_topic
        self.variant = variant
        self.show_resume = show_resume
        self.resume_topic = resume_topic
        self.resume_status_label = resume_status_label

        if variant == "portal":
            self.header_title = "老板好"
            self.header_template = HEADER_TEMPLATES["turquoise"]
        else:
            self.header_title = "🎯 主题盲盒"
            self.header_template = HEADER_TEMPLATES["turquoise"]

    def body_elements(self) -> list[dict]:
        if self.variant == "portal":
            els = []
            els.append(
                self.make_md(
                    "**老板好！**\n\n"
                    "请选择今天的路线：点 **主题** 浏览盲盒选题，点 **剧本投喂** 粘贴您的梗概或片段。\n"
                    "（也可先处理下方未完成任务，再开新单。）"
                )
            )
            if self.show_resume:
                name = (self.resume_topic or "").strip() or "（未命名任务）"
                prog = (self.resume_status_label or "").strip() or "进行中"
                els.append(
                    self.make_md(
                        f"> **📌 进行中的任务**：`{name}`\n"
                        f"> **当前进度**：{prog}"
                    )
                )
            return els

        els = []
        header_text = "**为您精选了 10 个真实历史/现实题材！**\n\n"
        if self.is_busy:
            header_text += (
                f"> ⚠️ **当前提醒**：后台正忙于制作【{self.busy_topic}】，"
                "您可以先看选题，等它忙完再开新单哦！\n\n"
            )
        els.append(self.make_md(header_text))

        if self.topics:
            items = "\n\n".join(f"🎯 `{t}`" for t in self.topics)
            els.append(self.make_md(items))
        return els

    def action_buttons(self) -> list[dict]:
        if self.variant == "portal":
            row1 = [
                self.make_button("主题", ACTION["OPEN_TOPIC_BLIND_BOX"], "primary"),
                self.make_button("剧本投喂", ACTION["REQUEST_SCRIPT_FEED"], "default"),
            ]
            rows = [self.make_action_row(*row1)]
            if self.show_resume:
                rows.append(
                    self.make_action_row(
                        self.make_button("▶️ 继续上一个任务", ACTION["RESUME_LAST_TASK"], "primary")
                    )
                )
            rows.append(
                self.make_action_row(
                    self.make_button("📊 查看状态", ACTION["OPS_STATUS"], "default")
                )
            )
            return rows

        row1 = [
            self.make_button("🔄 换一批", ACTION["REFRESH_TOPICS"], "default"),
            self.make_button("📝 投喂剧本", ACTION["REQUEST_SCRIPT_FEED"], "default"),
        ]
        row2 = [
            self.make_button("📊 查看状态", ACTION["OPS_STATUS"], "default"),
        ]
        return [
            self.make_action_row(*row1),
            self.make_action_row(*row2),
        ]
