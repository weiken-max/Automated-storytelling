import json
import os
from openai import OpenAI
from pathlib import Path
from dotenv import load_dotenv
import argparse
from src.style_config import FULL_STORY_V6_PATH

# ── 路径与环境配置 ──
load_dotenv()
import sys
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
DATA_DIR = BASE_DIR / "data"
from src.style_config import LLM_API_KEY, LLM_BASE_URL, MODEL_LLM
MODEL_WRITER = MODEL_LLM

# ── 库与金库支持 ──
from src.project_vault import init_project, backup as vault_backup # 🧪 V8.2 物理级金库支持

# ── 建立角色定妆照物理目录 (回归官方 data/refs 路径) ──
CHAR_DIR = BASE_DIR / "data" / "refs"
CHAR_DIR.mkdir(parents=True, exist_ok=True)

SYNOPSIS_SYSTEM_PROMPT = """你是一个极其冷酷的现实主义编剧与行业规则解剖师。
任务：根据用户给出的主题，设计一个充满【利益算计】、【阶层跃迁】与【人性异化】的第二人称人生副本梗概。

要求：
1. **隐性阶层结构**：故事在底层逻辑上必须包含清晰的跃迁轨迹（入局 -> 进阶 -> 掌权 -> 巅峰与反噬），但绝不使用任何等级或Level标签。
2. **核心科普（潜规则拆解）**：将该行业的核心运作机制、灰产逻辑或权力分配规则，作为主角晋升的关键武器。不要枯燥说教，要通过主角的“具体决定”和“利益交换”来展现。
3. **数字与代价**：故事推进必须伴随具体的数字（金钱、份额、时间）以及主角为了权力所抛弃的底线。
4. **结局闭环**：巅峰时刻必须伴随绝对的冷酷与孤独，主角最终要彻底沦为庞大系统的“宿命囚徒”或面临命运的黑色幽默式反噬。
5. **字数限制**：梗概总字数控制在 700 字左右，逻辑必须极其严密。

请输出 JSON 格式：
{
  "synopsis": "（700字左右的完整故事梗概，包含入局、进阶、终局的完整情节）",
  "era": "时代背景",
  "identity": "主角的终极身份",
  "industry_rules": ["（揭露的1-2个行业深层潜规则）"]
}"""

MASTER_WRITER_SYSTEM_PROMPT = """你是一个极其冷峻、犀利的短视频旁白文案大师。
任务：根据提供的故事梗概，将“你”在副本中的这一生扩写为一镜到底的沉浸式旁白。

【写作铁律】：
1. **唯一合法开头**：必须严格仅包含“今天你要体验的人生副本是，{TOPIC}的一生。”，不许有任何后缀。
2. **一镜到底的叙事**：绝对禁止使用任何段落小标题（如Level 1、第一阶段等）。必须通过时间流逝（如“三年过去”）、场景升级（如“你搬进了真皮转椅的独立办公室”）和手握筹码的变化来自然过渡剧情。
3. **第二人称与极简冷峻**：必须全程使用“你”。拒绝一切华丽辞藻、形容词和复杂的心理描写。多用短句，用客观动作、冷冰冰的数字和利益得失来推进剧情。
4. **[CUT_XXXX] 标签**：每 15-20 个字必须精准插入标签 [CUT_0001], [CUT_0002]...

【视觉与美术控制】（严格保持以下设定，绝不更改画风）：
必须全程使用“氰化物与欢乐”漫画风格（Cyanide and Happiness comic style）。
1. **底层/幼年期定妆照**：SD prompt需包含：Cyanide and Happiness style, flat illustration, simple line art, minimalist character design, bold outlines, flat vibrant colors, pure 2D flat aesthetic, absolutely no 3D rendering, young/poor version, character design sheet, triple view (front, side, back), simple solid white background.
2. **中层/发迹期定妆照**：SD prompt需包含：Cyanide and Happiness style, flat illustration, simple line art, minimalist character design, bold outlines, flat vibrant colors, pure 2D flat aesthetic, absolutely no 3D rendering, mature/successful version, character design sheet, triple view (front, side, back), simple solid white background.
3. **巅峰/老年期定妆照**：SD prompt需包含：Cyanide and Happiness style, flat illustration, simple line art, minimalist character design, bold outlines, flat vibrant colors, pure 2D flat aesthetic, absolutely no 3D rendering, older/boss version, character design sheet, triple view (front, side, back), simple solid white background.

请输出 JSON 格式（内部键名固定，不可变更）：
{
  "full_narration": "沉浸式旁白全文（必须包含 CUT 标签，严禁小标题）...",
  "character_anchors": {
      "child": "...",
      "middle": "...",
      "old": "..."
  },
  "stage_map": [{"stage": "child", "start_shot": 1, "end_shot": 5}, {"stage": "middle", "start_shot": 6, "end_shot": 15}, {"stage": "elderly", "start_shot": 16, "end_shot": 20}]
}
"""

def get_client():
    return OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

def generate_synopsis(topic: str):
    """阶段 1：生成剧情梗概 (不限字数，只求创意)"""
    client = get_client()
    print(f"\n[Step 1] 正在构思核心故事 (小说家梗概模式)...")
    try:
        response = client.chat.completions.create(
            model=MODEL_LLM,
            messages=[
                {"role": "system", "content": SYNOPSIS_SYSTEM_PROMPT},
                {"role": "user", "content": f"请为【{topic}】设计一个硬核利益跃迁副本。"}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"❌ 梗概生成失败: {e}")
        return None

def expand_narration(synopsis_data: dict, topic: str):
    """阶段 2：扩写沉浸式旁白 (锁死 1700 字和 80 镜)"""
    client = get_client()
    print(f"\n[Step 2] 正在扩写 80 镜沉浸式文案 (1700-1900 字限时任务)...")
    try:
        prompt_content = f"主题：{topic}\n故事梗概：{json.dumps(synopsis_data, ensure_ascii=False)}"
        response = client.chat.completions.create(
            model=MODEL_WRITER,
            messages=[
                {"role": "system", "content": MASTER_WRITER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt_content}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"❌ 文案生成失败: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="工业级电影叙事总线 - 故事规划仪")
    parser.add_argument("--topic", type=str, required=True, help="项目主题（如：底层逆袭、福尔摩斯）")
    parser.add_argument("--regen_stage", type=str, default=None, help="内部重画生命周期指定")
    args = parser.parse_args()
    
    topic = args.topic
    
    # 🧪 初始化物理金库
    init_project(topic)

    # 1. 梗概构思
    syn_result = generate_synopsis(topic)
    if not syn_result: return
    
    # 2. 文案扩写
    final_result = expand_narration(syn_result, topic)
    if not final_result: return

    # 对齐下游 (step1_writer_v6) 数据结构要求：用 master_design 包裹
    package_data = {
        "metadata": {
            "topic": topic,
            "project_name": topic,
            "era": syn_result.get("era", "现代")
        },
        "master_design": final_result
    }

    # 3. 保存至 FULL_STORY_V6_PATH (对接下游流水线)
    FULL_STORY_V6_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FULL_STORY_V6_PATH, "w", encoding="utf-8") as f:
        json.dump(package_data, f, ensure_ascii=False, indent=2)
    
    # 🧪 物理备份至金库
    vault_backup(FULL_STORY_V6_PATH, f"scripts/{FULL_STORY_V6_PATH.name}")
    
    print(f"\n🏆 工业级剧本规划成功流转至下游！")
    print(f"📍 路径: {FULL_STORY_V6_PATH}")

if __name__ == "__main__":
    main()
