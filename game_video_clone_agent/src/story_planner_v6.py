import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# ── 路径与环境配置 ──
load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
DATA_DIR = BASE_DIR / "data"

from src.style_config import LLM_API_KEY, LLM_BASE_URL, MODEL_LLM, FULL_STORY_V6_PATH, SCRIPT_DIR
from src.project_vault import init_project, backup as vault_backup
from src.ref_generator import run_ref_process

MODEL_WRITER = MODEL_LLM
NARRATION_MAX_RETRIES = 3
MIN_NARRATION_CHARS = 1300

# 兼容飞书既有链路（run_story_planner_with_mock.py / hub.py）
LEGACY_FEISHU_TEMP_SYNOPSIS_PATH = BASE_DIR / "feishu" / "temp_synopsis.json"

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
任务：根据提供的故事梗概，将“你”在副本中的这一生扩写为沉浸式纯净长文案。

【写作铁律】：
1. **唯一合法开头**：必须严格仅包含“今天你要体验的人生副本是，{TOPIC}的一生。”，不许有任何后缀。
2. **一镜到底的叙事**：绝对禁止使用任何段落小标题（如Level 1、第一阶段等）。必须通过时间流逝（如“三年过去”）、场景升级（如“你搬进了真皮转椅的独立办公室”）和手握筹码的变化来自然过渡剧情。
3. **第二人称与极简冷峻**：必须全程使用“你”。拒绝一切华丽辞藻、形容词和复杂的心理描写。多用短句，用客观动作、冷冰冰的数字和利益得失来推进剧情。
4. **纯净无标签文本（核心约束）**：必须是流畅连贯的散文式旁白全文。绝对禁止出现任何 [CUT_XXXX]、<subshot> 或任何形式的分镜标签与格式标记！字数控制在 1700 字左右。

【视觉与美术控制】（严格保持以下设定，绝不更改画风）：
必须全程使用“氰化物与欢乐”漫画风格（Cyanide and Happiness comic style）。
1. **底层/幼年期定妆照**：SD prompt需包含：Cyanide and Happiness style, flat illustration, simple line art, minimalist character design, bold outlines, flat vibrant colors, pure 2D flat aesthetic, absolutely no 3D rendering, young/poor version, character design sheet, triple view (front, side, back), simple solid white background.
2. **中层/发迹期定妆照**：SD prompt需包含：Cyanide and Happiness style, flat illustration, simple line art, minimalist character design, bold outlines, flat vibrant colors, pure 2D flat aesthetic, absolutely no 3D rendering, mature/successful version, character design sheet, triple view (front, side, back), simple solid white background.
3. **巅峰/老年期定妆照**：SD prompt需包含：Cyanide and Happiness style, flat illustration, simple line art, minimalist character design, bold outlines, flat vibrant colors, pure 2D flat aesthetic, absolutely no 3D rendering, older/boss version, character design sheet, triple view (front, side, back), simple solid white background.

请输出 JSON 格式（内部键名固定，不可变更）：
{
  "full_narration": "沉浸式旁白全文（绝对纯净文本，约1700字，严禁包含任何 CUT 标签或小标题）...",
  "character_anchors": {
      "child": "...",
      "middle": "...",
      "elderly": "..."
  }
}
"""


def get_client():
    return OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)


def _is_pure_narration(text: str) -> bool:
    if not text:
        return False
    if re.search(r"\[CUT_?\d+\]", text, re.IGNORECASE):
        return False
    if "<subshot>" in text.lower():
        return False
    if len(text.strip()) < MIN_NARRATION_CHARS:
        return False
    return True


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_synopsis(temp_synopsis_path: Path):
    if temp_synopsis_path.exists():
        return json.loads(temp_synopsis_path.read_text(encoding="utf-8"))
    if LEGACY_FEISHU_TEMP_SYNOPSIS_PATH.exists():
        data = json.loads(LEGACY_FEISHU_TEMP_SYNOPSIS_PATH.read_text(encoding="utf-8"))
        _write_json(temp_synopsis_path, data)
        return data
    return None


def generate_synopsis(topic: str):
    """阶段 1：生成剧情梗概 (不限字数，只求创意)"""
    client = get_client()
    print("\n[Step 1] 正在构思核心故事 (小说家梗概模式)...")
    try:
        response = client.chat.completions.create(
            model=MODEL_LLM,
            messages=[
                {"role": "system", "content": SYNOPSIS_SYSTEM_PROMPT},
                {"role": "user", "content": f"请为【{topic}】设计一个硬核利益跃迁副本。"},
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"❌ 梗概生成失败: {e}")
        return None


def expand_narration(synopsis_data: dict, topic: str):
    """阶段 2：调用 LLM 扩写沉浸式纯净长文案。"""
    print("\n[Step 2] 正在扩写 1700 字沉浸式纯净文案...")
    client = get_client()

    for attempt in range(1, NARRATION_MAX_RETRIES + 1):
        try:
            prompt_content = f"主题：{topic}\n故事梗概：{json.dumps(synopsis_data, ensure_ascii=False)}"
            response = client.chat.completions.create(
                model=MODEL_WRITER,
                messages=[
                    {"role": "system", "content": MASTER_WRITER_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt_content},
                ],
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            narration = (result.get("full_narration") or "").strip()
            print(f"     · Attempt {attempt}/{NARRATION_MAX_RETRIES} 文本字数≈{len(narration)}")
            if _is_pure_narration(narration):
                print("     ✅ 文案纯净校验通过（无 CUT / 无 subshot / 字数达标）")
                return result
            print("     ❌ 文案纯净校验未通过，准备重试。")
        except Exception as e:
            print(f"❌ 文案生成单次失败: {e}")

    return None


def _run_ref_generation(topic: str):
    print("\n📸 [Pipeline] 纯净文案已就绪，正在触发定妆照流水线...")
    try:
        asyncio.run(run_ref_process(topic, "protagonist", None))
        print("\n✅ 定妆照全部生成完毕，可供飞书节点二审批！")
    except Exception as e:
        print(f"\n❌ 定妆照生成环节发生错误: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="工业级电影叙事总线 - 故事规划仪 (解耦版)")
    parser.add_argument("--topic", type=str, required=True, help="项目主题（如：底层逆袭、福尔摩斯）")
    parser.add_argument(
        "--step",
        type=str,
        choices=["all", "synopsis", "narration"],
        default="all",
        help="执行阶段 (适配飞书审批节点)",
    )
    # 保留向后兼容，避免现有脚本传参报错
    parser.add_argument("--regen_stage", type=str, default=None, help="兼容保留参数")
    args = parser.parse_args()

    topic = args.topic
    step = args.step
    temp_synopsis_path = SCRIPT_DIR / "temp_synopsis.json"

    if step in ["all", "synopsis"]:
        init_project(topic)
        syn_result = generate_synopsis(topic)
        if not syn_result:
            print("❌ [FATAL] 梗概生成失败，流程终止。")
            sys.exit(1)

        _write_json(temp_synopsis_path, syn_result)
        _write_json(LEGACY_FEISHU_TEMP_SYNOPSIS_PATH, syn_result)
        vault_backup(temp_synopsis_path, f"scripts/{temp_synopsis_path.name}")

        print("\n🏆 阶段一 (梗概) 成功完成，等待飞书审批！")
        print(f"📍 路径: {temp_synopsis_path}")

    if step in ["all", "narration"]:
        syn_result = _load_synopsis(temp_synopsis_path)
        if not syn_result:
            print(f"❌ [FATAL] 找不到梗概文件 {temp_synopsis_path}，请先执行 --step synopsis")
            sys.exit(1)

        final_result = expand_narration(syn_result, topic)
        if not final_result:
            print("❌ [FATAL] 文案扩写失败（纯净校验连续未通过），流程终止。")
            sys.exit(1)

        package_data = {
            "metadata": {
                "topic": topic,
                "project_name": topic,
                "era": syn_result.get("era", "现代"),
            },
            "master_design": final_result,
        }

        try:
            _write_json(FULL_STORY_V6_PATH, package_data)
            vault_backup(FULL_STORY_V6_PATH, f"scripts/{FULL_STORY_V6_PATH.name}")
        except Exception as e:
            print(f"❌ [FATAL] 剧本写入磁盘失败: {e}")
            sys.exit(1)

        print("\n🏆 阶段二 (长文案) 生成完毕！")
        print(f"📍 路径: {FULL_STORY_V6_PATH}")
        _run_ref_generation(topic)


if __name__ == "__main__":
    main()
