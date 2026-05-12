import os
import sys
import json
import random
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from feishu_mgr import FeishuManager
from state_mgr import FeishuStateMgr

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

def load_env(path=".env.feishu"):
    env = {}
    with open(BASE_DIR / path, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                key, val = line.strip().split("=", 1)
                env[key] = val
    return env

env_vars = load_env()
mgr = FeishuManager(env_vars["FEISHU_APP_ID"], env_vars["FEISHU_APP_SECRET"])
state = FeishuStateMgr()

# 全局记录上一批已推送的题目，用于换一批时排重
_last_sent_topics: list = []


def send_welcome_portal(receive_id: str):
    """
    第二版总入口：老板好 +（可选）未完成任务的名称与进度 + 主题 / 剧本投喂。
    不改变状态机（不发题目前保持 IDLE / 原状态）。
    """
    from feishu.cards.idle_card import IdleCard
    from feishu.config import STATUS, STATUS_HUMAN, STATUS_HUMAN_SHORT

    curr = state.get_current_state()
    st = curr.get("status", STATUS["IDLE"])
    topic = (curr.get("topic") or "").strip()

    # 仅在选择盲盒选题阶段或纯空闲/已交付时不展示「进行中任务」条
    hide_resume = {
        STATUS["IDLE"],
        STATUS["COMPLETED"],
        STATUS["WAITING_TOPIC"],
    }
    show_resume = st not in hide_resume
    resume_label = STATUS_HUMAN_SHORT.get(st) or STATUS_HUMAN.get(st, st)

    class _MiniSession:
        def __init__(self, oid: str):
            self.open_id = oid

    card = IdleCard(
        _MiniSession(receive_id),
        mgr,
        variant="portal",
        show_resume=show_resume,
        resume_topic=topic,
        resume_status_label=str(resume_label),
    )
    mgr.send_card(receive_id, "open_id", card.build())

def get_dynamic_topics(exclude: list = None):
    """生成选题列表，exclude 传入上一批标题可防止重复"""
    try:
        import re
        from openai import OpenAI
        from src.style_config import LLM_API_KEY, LLM_BASE_URL, MODEL_LLM
        client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
        
        salt = random.randint(1, 9999999)
        exclude_str = ""
        if exclude:
            exclude_str = "\n\n**严格禁止**出现以下已推荐过的主题（一个都不能重复）：\n" + "\n".join(f"- {e}" for e in exclude)
        
        prompt = f"""任务：生成 10 个精炼的视频剧本选题，主题格式为"XX的一生"或"XX的故事"。

**核心要求（必须全部满足）：**
1. 必须是**真实存在于历史或现实生活中的职业或社会身份**，例如：煤矿工人、古代驿站邮差、战地记者、末代铁匠、1980年代下岗工人、盲人钢琴调音师等真实有过的职业。
2. **严禁**出现任何虚构幻想类职业，如"星辰修补匠"、"时间清道夫"、"记忆管理员"这类在现实中根本不存在的职业。
3. 优先选择有强烈时代感的中国或世界历史背景题材。
4. 10个主题必须覆盖**不同时代、不同国家、不同社会阶层**，不得雷同。
5. 选题要有张力：要么有悲剧感、要么有强烈反转、要么有鲜明的时代隐喻。
随机种子：{salt}{exclude_str}

输出格式：纯 JSON 数组，例如：["煤矿工人的一生", "末代邮差的故事"]"""
        
        completion = client.chat.completions.create(
            model=MODEL_LLM,
            messages=[
                {"role": "system", "content": "你是一个严肃的纪录片策划人，专注于真实人物和真实历史题材，绝对不写任何玄幻或虚构职业的故事。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.9,
            presence_penalty=0.8,
            frequency_penalty=0.5
        )
        content = completion.choices[0].message.content.strip()
        if content.startswith("```"): content = re.sub(r"^```(?:json)?\n|\n```$", "", content)
        topics = json.loads(content)
        if isinstance(topics, dict): topics = list(topics.values())[0]
        if isinstance(topics, list) and len(topics) > 0: return topics[:10]
    except Exception as e:
        print(f"[IDEATOR] LLM topics error: {e}")
    
    return ["煤矿工人的一生", "末代铁匠的故事", "1960年代赤脚医生的一生"]

def send_morning_topics(receive_id: str):
    """第二步：发送选题盲盒列表（与 IdleCard topics 一致，含换一批/投喂/状态）"""
    global _last_sent_topics
    from feishu.cards.idle_card import IdleCard

    curr = state.get_current_state()
    is_busy = curr["status"] not in ["IDLE", "WAITING_TOPIC", "COMPLETED"]

    topics = get_dynamic_topics(exclude=_last_sent_topics if _last_sent_topics else None)
    _last_sent_topics = list(topics)

    class _MiniSession:
        def __init__(self, oid: str):
            self.open_id = oid

    card = IdleCard(
        _MiniSession(receive_id),
        mgr,
        topics=topics,
        is_busy=is_busy,
        busy_topic=curr.get("topic") or "",
        variant="topics",
    )
    mgr.send_card(receive_id, "open_id", card.build())
    if not is_busy:
        state.set_status("WAITING_TOPIC", "")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--openid", type=str, required=True)
    args = parser.parse_args()
    send_morning_topics(args.openid)
