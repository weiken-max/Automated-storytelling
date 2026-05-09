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

    def __init__(self, session, mgr, topics: list[str] | None = None, is_busy: bool = False,
                 busy_topic: str = ""):
        super().__init__(session, mgr)
        self.topics = topics or []
        self.is_busy = is_busy
        self.busy_topic = busy_topic

    def body_elements(self) -> list[dict]:
        els = []
        header_text = "**老板早安！** 🌤️\n为您精选了 10 个真实历史/现实题材！\n\n"
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
        buttons = [
            self.make_button("🔄 换一批", ACTION["REFRESH_TOPICS"], "default"),
            self.make_button("📊 查看状态", ACTION["OPS_STATUS"], "default"),
        ]
        return [self.make_action_row(*buttons)]
