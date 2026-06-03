"""
提示词操作模块 (prompt_ops.py)
职责：加载/提取/翻译/改写/写回 visual_prompt
"""
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.run_context import get_paths
from src.model_presets import TRANSLATE_MODEL
from feishu.config import (
    PROMPT_REVISION_SYSTEM,
    PROMPT_BATCH_REVIEW_SYSTEM,
)


def _get_narrative_path(run_id: str) -> Path:
    """获取 narrative_v6_final.json 路径"""
    paths = get_paths()
    if not paths:
        # fallback: 用 run_id 直接构造路径
        run_dir = BASE_DIR / "data" / "runs" / run_id
        return run_dir / "scripts" / "narrative_v6_final.json"
    return paths["scripts_dir"] / "narrative_v6_final.json"


def load_narrative_final(run_id: str) -> dict:
    """加载 narrative_v6_final.json"""
    path = _get_narrative_path(run_id)
    if not path.exists():
        raise FileNotFoundError(f"narrative_v6_final.json 不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def get_batch_prompts(narrative: dict, batch_index: int) -> dict[str, str]:
    """
    提取某批次的 visual_prompt（仅 AI 生成部分，不含系统预设前缀）。
    返回: {"S_017": "A middle-aged man...", "S_018": "...", ...}

    batch_index 是 1-indexed。
    batch 1 → S_001~S_016, batch 2 → S_017~S_032, ...
    """
    timeline = narrative.get("timeline", [])
    batch_start = (batch_index - 1) * 16
    batch_end = min(batch_start + 16, len(timeline))
    prompts = {}
    for i in range(batch_start, batch_end):
        shot = timeline[i]
        sid = shot.get("subshot_id", f"S_{i+1:03d}")
        vp = shot.get("visual_prompt", "")
        prompts[sid] = vp.strip() if vp else ""
    return prompts


def _call_llm(messages: list[dict], model: str | None = None) -> str:
    """
    通用 LLM 调用（OpenAI 兼容接口）。
    model: 可选指定模型，默认用 style_config 的 LLM 模型。
    """
    from openai import OpenAI
    from src.style_config import LLM_API_KEY, LLM_BASE_URL, MODEL_LLM

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    completion = client.chat.completions.create(
        model=model or MODEL_LLM,
        messages=messages,
        temperature=0.7,
    )
    return completion.choices[0].message.content.strip()


def translate_prompts(prompts: dict[str, str]) -> dict[str, str]:
    """
    调用 DeepSeek V4 Pro Flash 英译中。
    输入: {"S_017": "A middle-aged man standing..."}
    输出: {"S_017": "一个中年男子站在..."}
    """
    if not prompts:
        return {}

    lines = []
    for sid, vp in prompts.items():
        if vp:
            lines.append(f"{sid}: {vp}")

    system = (
        "你是一个翻译助手。请将以下英文视觉提示词翻译成简洁的中文描述。"
        "保持原意，输出格式严格为：S_XXX: 中文翻译，每行一条。"
    )
    user_msg = "请翻译以下提示词：\n" + "\n".join(lines)

    result = _call_llm(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        model=TRANSLATE_MODEL,
    )

    translated = {}
    for line in result.split("\n"):
        line = line.strip()
        if ":" in line and line[:2] == "S_":
            parts = line.split(":", 1)
            if len(parts) == 2:
                sid = parts[0].strip()
                cn_text = parts[1].strip()
                if sid in prompts:
                    translated[sid] = cn_text

    # 如果有漏掉的，用原文兜底
    for sid in prompts:
        if sid not in translated:
            translated[sid] = prompts[sid]

    return translated


def revise_single_prompt(
    original_en: str,
    feedback_cn: str,
    subshot_id: str = "",
) -> str:
    """
    根据用户修改意见，调用 LLM 改写单条 visual_prompt。
    original_en: 当前英文 visual_prompt
    feedback_cn: 用户的中文修改意见
    subshot_id: 分镜 ID（仅用于日志）
    返回改写后的英文 visual_prompt
    """
    user_msg = (
        f"【原提示词】\n{original_en}\n\n"
        f"【修改意见】\n{feedback_cn}\n\n"
        f"请改写这条提示词。"
    )
    if subshot_id:
        user_msg = f"分镜 {subshot_id} 需要修改：\n" + user_msg

    result = _call_llm(
        [
            {"role": "system", "content": PROMPT_REVISION_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
    )
    return result


def revise_batch_prompts(
    batch_prompts: dict[str, str],
    feedback_cn: str,
) -> dict[str, str]:
    """
    整批审查：LLM 审查全部 16 条 prompt，找出可能导致问题的并改写。
    batch_prompts: {"S_017": "...", "S_018": "...", ...}
    feedback_cn: 用户的整批修改意见
    返回: {"S_017": "revised...", "S_018": "revised...", ...}（只包含被修改的）
    """
    lines = []
    for sid in sorted(batch_prompts.keys()):
        lines.append(f"{sid}: {batch_prompts[sid]}")

    user_msg = (
        f"【全部 16 条提示词】\n" + "\n".join(lines) + "\n\n"
        f"【整批修改意见】\n{feedback_cn}\n\n"
        f"请审查并改写有问题的提示词，只返回被修改的条目（JSON 格式）。"
    )

    result = _call_llm(
        [
            {"role": "system", "content": PROMPT_BATCH_REVIEW_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
    )

    # 解析 JSON
    try:
        # 去除可能的 markdown 包裹
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("\n```", 1)[0]
        revised = json.loads(cleaned)
        if isinstance(revised, dict):
            return {k: v for k, v in revised.items() if k in batch_prompts}
    except json.JSONDecodeError:
        pass

    # JSON 解析失败，尝试逐行解析
    revised = {}
    for line in result.split("\n"):
        line = line.strip()
        match = None
        for sid in batch_prompts:
            prefix = f'"{sid}":'
            if prefix in line:
                match = sid
                break
            prefix2 = f"'{sid}':"
            if prefix2 in line:
                match = sid
                break
        if match:
            parts = line.split(":", 1)
            if len(parts) == 2:
                val = parts[1].strip().strip('"').strip("'").rstrip(",").rstrip('"').rstrip("'")
                revised[match] = val

    return revised


def write_back_prompts(
    narrative: dict,
    batch_index: int,
    revised: dict[str, str],
    file_path: Path | None = None,
):
    """
    将修改后的 prompt 写回 narrative dict（调用方负责落盘）。
    narrative: 完整的 narrative dict（会被就地修改）
    batch_index: 1-indexed 批次号
    revised: {sid: "new prompt", ...}
    """
    timeline = narrative.get("timeline", [])
    batch_start = (batch_index - 1) * 16
    for i in range(batch_start, min(batch_start + 16, len(timeline))):
        shot = timeline[i]
        sid = shot.get("subshot_id", "")
        if sid in revised:
            shot["visual_prompt"] = revised[sid]


def save_narrative_final(narrative: dict, run_id: str):
    """将 narrative dict 落盘"""
    path = _get_narrative_path(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(narrative, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_revision_message(msg: str) -> dict | None:
    """
    解析提示词修改消息，返回结构化信息。
    支持三种格式：
      1. 单子分镜: "批次 2 S_18 光影较弱，增强光影"
      2. 多子分镜: "批次 2 修改：S_18 增强光影；S_22 拉近特写"
      3. 整批修改: "批次 2 加强 4×4 宫格布局约束"

    返回 None 表示无法解析。
    返回 dict 示例：
      {"type": "single", "batch": 2, "subshots": ["S_018"], "feedback": "光影较弱..."}
      {"type": "batch",  "batch": 2, "subshots": ["S_018", "S_022"], "feedback": "..."}
      {"type": "full",   "batch": 2, "subshots": [], "feedback": "加强 4×4 宫格..."}
    """
    from feishu.config import PROMPT_REVISION_SINGLE, PROMPT_REVISION_BATCH, PROMPT_REVISION_FULL

    msg_clean = msg.strip()

    # 1. 单子分镜
    m_single = PROMPT_REVISION_SINGLE.match(msg_clean)
    if m_single:
        batch_num = int(m_single.group(1))
        sub_num = int(m_single.group(2))
        feedback = m_single.group(3)
        sid = f"S_{sub_num:03d}"
        return {
            "type": "single",
            "batch": batch_num,
            "subshots": [sid],
            "feedback": feedback,
        }

    # 2. 多子分镜
    m_batch = PROMPT_REVISION_BATCH.match(msg_clean)
    if m_batch:
        batch_num = int(m_batch.group(1))
        raw_feedback = m_batch.group(2)
        # 按 ; ； 分号或换行拆分
        import re
        parts = re.split(r"[;；\n]+", raw_feedback)
        subshots = []
        per_feedback_parts = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            m_sub = re.match(r"S[_]?(\d+)\s+(.+)", part, re.IGNORECASE)
            if m_sub:
                subshots.append(f"S_{int(m_sub.group(1)):03d}")
                per_feedback_parts.append(m_sub.group(2))
            else:
                per_feedback_parts.append(part)
        feedback = "; ".join(per_feedback_parts)
        return {
            "type": "batch",
            "batch": batch_num,
            "subshots": subshots,
            "feedback": feedback,
        }

    # 3. 整批修改
    m_full = PROMPT_REVISION_FULL.match(msg_clean)
    if m_full:
        batch_num = int(m_full.group(1))
        feedback = m_full.group(2)
        # 过滤掉纯数字或太短的情况（避免误匹配 "批次 2 重画" 等）
        if len(feedback) < 2:
            return None
        return {
            "type": "full",
            "batch": batch_num,
            "subshots": [],
            "feedback": feedback,
        }

    return None
