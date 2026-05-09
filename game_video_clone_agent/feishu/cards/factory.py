"""
卡片工厂
根据 Session 状态自动选择对应的卡片类
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from feishu.config import STATUS
from feishu.cards.idle_card import IdleCard
from feishu.cards.synopsis_card import SynopsisCard
from feishu.cards.character_card import CharacterCard
from feishu.cards.storyboard_card import StoryboardCard
from feishu.cards.progress_card import ProgressCard

# 状态 → 卡片类 映射
CARD_MAP = {
    STATUS["IDLE"]:                      IdleCard,
    STATUS["WAITING_TOPIC"]:            IdleCard,
    STATUS["COMPLETED"]:                IdleCard,
    STATUS["GENERATING_SYNOPSIS"]:      ProgressCard,
    STATUS["WAITING_SYNOPSIS_APPROVAL"]:SynopsisCard,
    STATUS["GENERATING_VISUALS"]:       ProgressCard,
    STATUS["WAITING_CHARACTER_APPROVAL"]:CharacterCard,
    STATUS["WAITING_STORYBOARD_APPROVAL"]:StoryboardCard,
    STATUS["STEP1_WRITING"]:            ProgressCard,
    STATUS["STEP1_READY"]:              ProgressCard,
    STATUS["STEP2_GENERATING"]:         ProgressCard,
    STATUS["STEP2_FAILED"]:             ProgressCard,
    STATUS["STEP2_SUCCESS"]:            ProgressCard,
    STATUS["STEP3_ASSEMBLING"]:         ProgressCard,
    STATUS["PAUSED"]:                   ProgressCard,
    STATUS["ERROR"]:                    ProgressCard,
}


class CardFactory:
    """根据 Session 状态创建对应卡片"""

    @staticmethod
    def get_card_class(status: str):
        return CARD_MAP.get(status, IdleCard)

    @staticmethod
    def build_card(session, mgr, **extra_kwargs) -> "BaseCard":
        """
        工厂方法：根据 session 状态自动选择卡片类并实例化。
        extra_kwargs 传递给卡片构造器（如 topics, synopsis_data 等）。
        """
        card_cls = CARD_MAP.get(session.status, IdleCard)
        return card_cls(session, mgr, **extra_kwargs)
