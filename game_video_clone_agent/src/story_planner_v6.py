from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv
from openai import OpenAI

# ── 路径与环境配置 ──
load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
DATA_DIR = BASE_DIR / "data"

from src.style_config import (
    DEFAULT_STORY_DURATION_MINUTES,
    LLM_API_KEY,
    LLM_BASE_URL,
    MODEL_LLM,
    NARRATION_CHARS_PER_MINUTE,
    NARRATION_SEGMENT_COUNT,
    NARRATION_SEGMENT_MAX_TOKEN_FACTOR,
    NARRATION_SEGMENT_TAIL_CHARS,
    SYNOPSIS_BODY_MAX_CHARS,
)
from src.api_audit import PHASE_NARRATION, PHASE_SYNOPSIS, log_event, log_llm_chat
from src.project_vault import init_project, backup as vault_backup
from src.ref_generator import run_ref_process
from src.run_context import start_new_run, get_paths, get_current_run_id

MODEL_WRITER = MODEL_LLM
SEGMENT_LENGTH_MAX_RETRIES = 3
SEGMENT_NETWORK_MAX_RETRIES = 5
SEGMENT_NETWORK_RETRY_BASE_SEC = 1.0
MIN_NARRATION_CHARS_BASE = 1000
# 分段拼接后，全文至少达到 target_chars 的该比例（不足则尾部扩写，避免「标 6 分钟却只有 4.x 分钟旁白」）
NARRATION_TARGET_SOFT_RATIO = 0.93
NARRATION_TAIL_PATCH_MAX_ROUNDS = 4
# 全文已达标但末句明显没收束时，最多追加几轮「收尾扩写」（与字数补丁共用模型调用）
NARRATION_CLOSE_PATCH_MAX_ROUNDS = 2

# 粗略判断旁白末字是否像完整句末（不依赖 LLM 自述；用于避免半截入盘）
_TAIL_SENTENCE_CHARS = frozenset("。！？!?…")


def opening_topic_phrase(topic: str) -> str:
    """
    用于开篇句「今天你要体验的人生副本是，XXX。」中的 XXX。
    若选题已是「朱元璋的一生」，不再重复拼接「的一生」。
    """
    t = (topic or "").strip()
    core = t.removesuffix("的一生").strip()
    if not core:
        core = t or "本主题"
    return f"{core}的一生"


# 叙事分段标签（与权重一一对应）；权重之和必须为 1
_SEGMENT_WEIGHTS_6 = [0.12, 0.15, 0.18, 0.20, 0.18, 0.17]
_SEGMENT_LABELS_6 = [
    "入局",
    "扎根与规则",
    "进阶与筹码",
    "掌权与扩张",
    "巅峰与失衡",
    "反噬与终局",
]
_SEGMENT_WEIGHTS_5 = [0.18, 0.22, 0.22, 0.22, 0.16]
_SEGMENT_LABELS_5 = ["入局", "进阶", "掌权", "巅峰", "终局反噬"]
_SEGMENT_WEIGHTS_4 = [0.22, 0.28, 0.28, 0.22]
_SEGMENT_LABELS_4 = ["入局与立足", "进阶与扩张", "掌权与巅峰", "终局"]

# 兼容飞书既有链路（run_story_planner_with_mock.py / hub.py）
LEGACY_FEISHU_TEMP_SYNOPSIS_PATH = BASE_DIR / "feishu" / "temp_synopsis.json"


def _synopsis_act_target_n() -> int:
    """与 NARRATION_SEGMENT_COUNT 对齐：大纲固定拆成相同幕数，供旁白分幕引用。"""
    try:
        n = int(NARRATION_SEGMENT_COUNT)
    except (TypeError, ValueError):
        n = 6
    return max(4, min(8, n))


def _partition_indices(n_items: int, n_buckets: int) -> list[tuple[int, int]]:
    """将 [0, n_items) 划成 n_buckets 段连续区间，每段长度尽量均匀。"""
    if n_buckets <= 0 or n_items <= 0:
        return []
    base = n_items // n_buckets
    rem = n_items % n_buckets
    out: list[tuple[int, int]] = []
    start = 0
    for b in range(n_buckets):
        size = base + (1 if b < rem else 0)
        end = start + size
        out.append((start, end))
        start = end
    return out


def _bucket_strings_for_n_segments(parts: list[str], n_seg: int) -> list[str]:
    """将若干段文本合并为恰好 n_seg 段（顺序不变、相邻合并）。"""
    parts = [str(p).strip() for p in parts if str(p).strip()]
    if n_seg <= 0:
        return []
    if not parts:
        return [""] * n_seg
    if len(parts) == n_seg:
        return parts
    if len(parts) < n_seg:
        out = list(parts)
        while len(out) < n_seg:
            out.append(out[-1] if out else "")
        return out[:n_seg]
    spans = _partition_indices(len(parts), n_seg)
    return ["\n\n".join(parts[lo:hi]) for lo, hi in spans]


def _fallback_split_synopsis_text(text: str, n: int) -> list[str]:
    """无 synopsis_acts 时，将整段 synopsis 粗切成 n 份。"""
    text = (text or "").strip()
    if n <= 0:
        return []
    if not text:
        return [""] * n
    if n == 1:
        return [text]
    paras = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    if len(paras) >= n:
        spans = _partition_indices(len(paras), n)
        return ["\n\n".join(paras[lo:hi]) for lo, hi in spans]
    L = len(text)
    cuts = [round(L * i / n) for i in range(n + 1)]
    return [text[cuts[i] : cuts[i + 1]].strip() for i in range(n)]


def _clamp_synopsis_acts_total(acts: list[str], max_total: int) -> list[str]:
    """保持幕数不变，从最后一幕起逐字删减，直至拼接总长不超过 max_total。"""
    acts = [str(a).strip() for a in acts]
    if not acts:
        return [""]
    sep = "\n\n"

    def joined() -> str:
        return sep.join(acts)

    guard = 0
    while len(joined()) > max_total and guard < max_total + 2000:
        guard += 1
        cut = False
        for i in range(len(acts) - 1, -1, -1):
            if acts[i]:
                acts[i] = acts[i][:-1].rstrip()
                cut = True
                break
        if not cut:
            s = joined()
            acts = [s[: max(1, max_total - 1)].rstrip() + "…"]
            break
    return acts


def normalize_synopsis_payload(data: dict) -> dict:
    """
    统一大纲：synopsis_acts 长度与 NARRATION_SEGMENT_COUNT 一致，synopsis 为其拼接全文，
    总长不超过 SYNOPSIS_BODY_MAX_CHARS。兼容仅有 synopsis 的旧 JSON。
    """
    out = dict(data)
    n_act = _synopsis_act_target_n()
    raw_acts = out.get("synopsis_acts")
    acts: list[str] = []
    if isinstance(raw_acts, list):
        acts = [str(x).strip() for x in raw_acts if str(x).strip()]
    syn_full = str(out.get("synopsis") or "").strip()

    if len(acts) > n_act:
        acts = _bucket_strings_for_n_segments(acts, n_act)
    elif len(acts) < n_act:
        if syn_full:
            acts = _fallback_split_synopsis_text(syn_full, n_act)
        elif acts:
            while len(acts) < n_act:
                acts.append(acts[-1])
        else:
            acts = [""] * n_act

    acts = _clamp_synopsis_acts_total(acts, int(SYNOPSIS_BODY_MAX_CHARS))
    out["synopsis_acts"] = acts
    out["synopsis"] = "\n\n".join(acts).strip()
    return out


def _writer_synopsis_excerpt(mo_slices: list[str], segment_index: int, n_mo: int) -> str:
    """第 1 幕：1+2；中间幕：i-1,i,i+1；最后一幕：倒数两幕。"""
    if n_mo <= 0:
        return ""
    mo = [str(x).strip() for x in mo_slices[:n_mo]]
    while len(mo) < n_mo:
        mo.append(mo[-1] if mo else "")
    if n_mo == 1:
        return mo[0]
    i = segment_index
    if i == 0:
        parts = mo[0:2]
    elif i == n_mo - 1:
        parts = mo[-2:]
    else:
        parts = mo[i - 1 : i + 2]
    return "\n\n".join(p for p in parts if p).strip()


def _patch_synopsis_excerpt_from_mo(mo_slices: list[str]) -> str:
    """尾部扩写补丁：只带末两幕梗概，减轻上下文。"""
    mo = [str(x).strip() for x in mo_slices if str(x).strip()]
    if len(mo) >= 2:
        s = "\n\n".join(mo[-2:])
    else:
        s = "\n\n".join(mo)
    cap = min(1200, int(SYNOPSIS_BODY_MAX_CHARS))
    if len(s) > cap:
        s = s[:cap] + "…"
    return s


_act_n = _synopsis_act_target_n()
SYNOPSIS_SYSTEM_PROMPT = f"""你是一个极其冷酷的现实主义编剧与行业规则解剖师。
任务：根据用户给出的主题，设计一个充满【利益算计】、【阶层跃迁】与【人性异化】的第二人称人生副本梗概。

要求：
1. **隐性阶层结构**：故事在底层逻辑上必须包含清晰的跃迁轨迹（入局 -> 进阶 -> 掌权 -> 巅峰与反噬），但绝不使用任何等级或Level标签。
2. **核心科普（潜规则拆解）**：将该行业的核心运作机制、灰产逻辑或权力分配规则，作为主角晋升的关键武器。不要枯燥说教，要通过主角的“具体决定”和“利益交换”来展现。
3. **数字与代价**：故事推进必须伴随具体的数字（金钱、份额、时间）以及主角为了权力所抛弃的底线。
4. **结局闭环**：巅峰时刻必须伴随绝对的冷酷与孤独，主角最终要彻底沦为庞大系统的“宿命囚徒”或面临命运的黑色幽默式反噬。
5. **分幕结构（硬性）**：必须输出 `synopsis_acts` 数组，长度**恰好**为 **{_act_n}**，每个元素对应一幕的连续叙事；幕内不要用「第X幕」等小标题；时间顺序从第 1 幕到最后一幕衔接成一条完整故事线。
6. **总字数**：`synopsis` 与 `synopsis_acts` 拼接后的总字符数（汉字+标点）**不得超过 {SYNOPSIS_BODY_MAX_CHARS}**，逻辑必须极其严密。

请输出 JSON 格式（键名固定）：
{{
  "synopsis_acts": [共{_act_n}个字符串，依次为第1幕…第{_act_n}幕梗概正文],
  "synopsis": "将 synopsis_acts 用两个换行符拼接成的全文，必须与各幕内容完全一致",
  "era": "时代背景",
  "identity": "主角的终极身份",
  "industry_rules": ["（揭露的1-2个行业深层潜规则）"]
}}"""

MASTER_WRITER_SYSTEM_PROMPT = """你是一个极其冷峻、犀利的短视频旁白文案大师。
任务：根据提供的故事梗概，将“你”在副本中的这一生扩写为沉浸式纯净长文案。

【写作铁律】：
1. **唯一合法开头**：必须严格仅包含“今天你要体验的人生副本是，{TOPIC}的一生。”（{TOPIC} 为主题核心名；若选题本身已含「的一生」则勿重复写成「一生的一生」），不许有其他后缀。
2. **一镜到底的叙事**：绝对禁止使用任何段落小标题（如Level 1、第一阶段等）。必须通过时间流逝（如“三年过去”）、场景升级（如“你搬进了真皮转椅的独立办公室”）和手握筹码的变化来自然过渡剧情。
3. **第二人称与极简冷峻**：必须全程使用“你”。拒绝一切华丽辞藻、形容词和复杂的心理描写。多用短句，用客观动作、冷冰冰的数字和利益得失来推进剧情。
4. **纯净无标签文本（核心约束）**：必须是流畅连贯的散文式旁白、<subshot> 或任何形式的分镜标签与格式标记！字数控制在 1700 字左右。

【视觉与美术控制】：旁白保持冷峻叙事即可；人物定妆英文提示词由定妆流水线根据梗概生成，并写入当前 run 的 scripts/refs-prompt.json，勿在本 JSON 中输出 character_anchors。

请输出 JSON 格式（内部键名固定，不可变更）：
{
  "full_narration": "沉浸式旁白全文（绝对纯净文本，约1700字。）..."
}
"""


def get_client():
    return OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)


def _compute_narration_targets(duration_min: float) -> tuple[int, int]:
    """(目标字数, 校验下限) — 由目标成片时长（分钟）驱动。"""
    try:
        dur = float(duration_min)
    except (TypeError, ValueError):
        dur = DEFAULT_STORY_DURATION_MINUTES
    dur = max(0.25, min(dur, 120.0))
    target = int(dur * NARRATION_CHARS_PER_MINUTE)
    target = max(1200, min(target, 25000))
    min_chars = max(MIN_NARRATION_CHARS_BASE, int(target * 0.88))
    min_chars = min(min_chars, target)
    return target, min_chars


def _is_pure_narration(text: str, min_chars: int) -> bool:
    if not text:
        return False
    if re.search(r"\[CUT_?\d+\]", text, re.IGNORECASE):
        return False
    if "<subshot>" in text.lower():
        return False
    if len(text.strip()) < min_chars:
        return False
    return True


def _narration_tail_sentence_complete(text: str) -> bool:
    """末字是否落在常见句末标点（中文旁白）；不视为语法分析，仅作流水线护栏。"""
    t = (text or "").rstrip()
    if not t:
        return False
    last = t[-1]
    if last in _TAIL_SENTENCE_CHARS:
        return True
    # 节选体「……」后以弯引号收尾
    if last in "\u201d\u2019」』":
        return True
    return False


def _allocate_segment_chars(total: int, weights: Sequence[float]) -> list[int]:
    """最大余数法分配整数段长，保证之和等于 total。"""
    n = len(weights)
    if n == 0:
        return []
    exact = [total * w for w in weights]
    base = [int(x) for x in exact]
    rem = total - sum(base)
    order = sorted(range(n), key=lambda i: (exact[i] - base[i]), reverse=True)
    for j in range(rem):
        base[order[j]] += 1
    return base


def _pick_segment_plan(target_total: int) -> tuple[list[float], list[str]]:
    """按总字数选择段数与权重（降低短文强行拆 6 段的稀薄感）。"""
    if target_total < 1600:
        return list(_SEGMENT_WEIGHTS_4), list(_SEGMENT_LABELS_4)
    if target_total < 2800:
        return list(_SEGMENT_WEIGHTS_5), list(_SEGMENT_LABELS_5)
    # 长文：默认 6 幕；可通过 style_config NARRATION_SEGMENT_COUNT 改为 5（合并末两段权重）
    if NARRATION_SEGMENT_COUNT <= 5:
        return list(_SEGMENT_WEIGHTS_5), list(_SEGMENT_LABELS_5)
    return list(_SEGMENT_WEIGHTS_6), list(_SEGMENT_LABELS_6)


def _strip_ai_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _strip_overlap_with_previous(prev: str, curr: str, max_overlap: int = 160) -> str:
    """若当前段开头重复了上一段结尾，去掉重复前缀。"""
    if not prev or not curr:
        return curr
    max_ov = min(max_overlap, len(prev), len(curr))
    for k in range(max_ov, 24, -1):
        if curr.startswith(prev[-k:]):
            return curr[k:].strip()
    return curr


_RE_OPENING = re.compile(
    r"今天你要体验的人生副本是，[^。\n]{1,80}?的一生。"
)


def _format_mo_roadmap(labels: list[str]) -> str:
    return " → ".join(f"第{i + 1}幕「{lb}」" for i, lb in enumerate(labels))


def _handoff_for_next_segment(
    client: OpenAI,
    topic: str,
    synopsis_data: dict,
    text_so_far: str,
    next_label: str,
    next_1based: int,
    total_mo: int,
) -> str:
    """
    上一幕写完后，由统筹模型根据梗概+已写正文生成「给下一幕写手」的续写指令。
    """
    sys_p = """你是编剧统筹。根据故事梗概与**已写旁白正文**，为下一位「旁白写手」写一段**续写指令**（约 80～200 个汉字）。

要求：
- 只写**必须推进的剧情节点**（可含时间、数字、利益交换、转折），不要写旁白正文，不要复述梗概全文。
- 指令必须衔接已写内容，并指向「下一幕」的叙事任务，不能另起无关故事或改人设。
- 用一段连续文字，不要用 markdown 分条。不要重复已写事实。"""
    tail = text_so_far[-3000:] if len(text_so_far) > 3000 else text_so_far
    syn_s = json.dumps(synopsis_data, ensure_ascii=False)[:4500]
    user_p = (
        f"主题：{topic}\n\n"
        f"【梗概 JSON 节选】\n{syn_s}\n\n"
        f"【已写旁白共 {len(text_so_far)} 字，下为近文】\n…{tail}\n\n"
        f"【下一任务】第 {next_1based}/{total_mo} 幕「{next_label}」。请只输出给写手的续写指令。"
    )
    t0 = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=MODEL_LLM,
            messages=[
                {"role": "system", "content": sys_p},
                {"role": "user", "content": user_p},
            ],
            max_tokens=500,
            temperature=0.25,
        )
        ms = (time.perf_counter() - t0) * 1000
        log_event(
            PHASE_NARRATION,
            "handoff_next_segment",
            "llm_chat",
            ok=True,
            duration_ms=ms,
            model=MODEL_LLM,
            extra={"next_mo": next_1based, "total_mo": total_mo},
        )
        h = _strip_ai_fences(response.choices[0].message.content or "")
        h = h.strip()
        if len(h) < 20:
            raise ValueError("handoff too short")
        return h[:800]
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        log_event(
            PHASE_NARRATION,
            "handoff_next_segment",
            "llm_chat",
            ok=False,
            duration_ms=ms,
            model=MODEL_LLM,
            error=str(e),
            extra={"next_mo": next_1based, "total_mo": total_mo},
        )
        print(f"     ⚠️ 续写统筹 handoff 未生成（{e}），使用幕次回退提示。")
        return (
            f"请紧接上文时态与事实，进入第 {next_1based} 幕「{next_label}」："
            f"从梗概中择取本阶段尚未写透的关键事件与代价，把叙事推进一步，避免重复上段已写内容。"
        )


def _compact_synopsis_json_for_writer(
    synopsis_data: dict,
    *,
    emergency: bool = False,
    synopsis_excerpt: str | None = None,
) -> str:
    """
    分幕写手请求用梗概节选：不传 industry_rules。
    synopsis_excerpt 有值时只写入该段（本幕相关梗概），否则用全文 synopsis（并压到 SYNOPSIS_BODY_MAX_CHARS）。
    emergency=True 时进一步缩短 excerpt，供灾难重试。
    """
    if synopsis_excerpt is not None:
        syn = synopsis_excerpt.strip()
    else:
        syn = str(synopsis_data.get("synopsis") or "").strip()
        if len(syn) > int(SYNOPSIS_BODY_MAX_CHARS):
            syn = syn[: int(SYNOPSIS_BODY_MAX_CHARS)] + "…"
    max_syn = 900 if emergency else 4200
    if len(syn) > max_syn:
        syn = syn[:max_syn] + "…"
    slim: dict = {
        "synopsis": syn,
        "era": synopsis_data.get("era"),
        "identity": synopsis_data.get("identity"),
        "duration": synopsis_data.get("duration"),
    }
    raw = json.dumps(slim, ensure_ascii=False)
    cap = 2800 if emergency else 9000
    if len(raw) > cap:
        raw = raw[:cap] + "…"
    return raw


def _segment_system_prompt(seg_target: int) -> str:
    return f"""你是一个极其冷峻、犀利的短视频旁白文案大师。
任务：按用户指示写出**一段**沉浸式旁白（不是全文，只是连续叙事中的一段）。

【写作铁律】
1. **一镜到底**：禁止使用段落小标题（如 Level、第一阶段）。用时间流逝、场景升级、数字与利益推进。
2. **第二人称**：全程使用「你」，极简冷峻，少用形容词。
3. **纯净文本**：禁止 <subshot>、禁止 [CUT]、禁止任何分镜标签。
4. **本段体量**：本段目标约 **{seg_target}** 字（允许 ±10%）。

输出要求：**只输出旁白正文**，不要标题、不要 JSON、不要代码围栏、不要解释。"""


def _generate_one_segment(
    client: OpenAI,
    *,
    topic: str,
    synopsis_data: dict,
    synopsis_excerpt: str,
    segment_index: int,
    segment_label: str,
    seg_target: int,
    prev_full_text: str,
    tail_chars: int,
    all_labels: list[str],
    handoff_brief: str = "",
) -> str | None:
    sys_p = _segment_system_prompt(seg_target)
    max_tokens = min(
        16384,
        max(2048, int(seg_target * float(NARRATION_SEGMENT_MAX_TOKEN_FACTOR))),
    )
    n_mo = len(all_labels)
    mo_road = _format_mo_roadmap(all_labels)
    syn_block = _compact_synopsis_json_for_writer(
        synopsis_data, synopsis_excerpt=synopsis_excerpt
    )
    hard_floor = max(200, int(seg_target * 0.55))
    base_ctx = (
        f"主题：{topic}\n\n"
        f"【本幕相关梗概节选（JSON）】\n{syn_block}\n\n"
        f"【全剧共 {n_mo} 幕（勿跳幕、勿提前写后几幕才发生的事）】\n{mo_road}\n\n"
        f"【当前】第 {segment_index + 1}/{n_mo} 幕「{segment_label}」\n"
    )

    if segment_index == 0:
        user_p = (
            base_ctx
            + f"你只写**第 1 幕**正文。\n"
            + f"【开篇唯一合法形式】正文第一句必须且仅能是："
            f"「今天你要体验的人生副本是，{opening_topic_phrase(topic)}。」"
            f"随后立刻接着写，不要复述主题。\n"
            f"本幕目标约 {seg_target} 字，须落实梗概里入局阶段的关键事实。\n"
            f"【硬性】本段须输出不少于 {hard_floor} 个汉字的连贯旁白正文（不是提纲、不是对话、不要 JSON）。\n"
        )
    else:
        tail = prev_full_text[-tail_chars:] if len(prev_full_text) > tail_chars else prev_full_text
        hb = (handoff_brief or "").strip()
        user_p = (
            base_ctx
            + f"【统筹给本幕的续写指令（须落实，勿与梗概矛盾）】\n{hb}\n\n"
            + f"【承接】上一幕结尾（无缝接续，禁止再写开场白「今天你要体验的人生副本是」）：\n"
            f"「…{tail}」\n\n"
            f"你只写**第 {segment_index + 1} 幕**正文。本幕目标约 {seg_target} 字。"
            f"从接续处自然往下写，不要复述已写过的段落。\n"
            f"【硬性】本段须输出不少于 {hard_floor} 个汉字的连贯旁白正文（不是提纲、不是对话、不要 JSON）。\n"
        )

    length_failures = 0
    network_failures = 0
    attempt = 0
    used_emergency_synopsis = False
    while True:
        attempt += 1
        try:
            t_req = time.perf_counter()
            response = client.chat.completions.create(
                model=MODEL_WRITER,
                messages=[
                    {"role": "system", "content": sys_p},
                    {"role": "user", "content": user_p},
                ],
                max_tokens=max_tokens,
                temperature=0.35,
            )
            choice = response.choices[0] if response.choices else None
            finish_reason = getattr(choice, "finish_reason", None) if choice else None
            raw = (choice.message.content if choice and choice.message else "") or ""
            text = _strip_ai_fences(raw)
            if segment_index > 0:
                text = _RE_OPENING.sub("", text, count=1).strip()
            lo = int(seg_target * 0.78)
            hi = int(seg_target * 1.18)
            ln = len(text)
            log_event(
                PHASE_NARRATION,
                f"segment_writer_{segment_index + 1}_{segment_label}",
                "llm_chat",
                ok=True,
                duration_ms=(time.perf_counter() - t_req) * 1000,
                model=MODEL_WRITER,
                attempt=attempt,
                extra={
                    "seg_target": seg_target,
                    "mo_index": segment_index + 1,
                    "out_chars": ln,
                    "finish_reason": finish_reason,
                    "max_tokens": max_tokens,
                },
            )
            if finish_reason == "length":
                print(
                    f"     ⚠️ 第 {segment_index + 1} 幕 API 返回 finish_reason=length（生成撞 max_tokens），"
                    f"本段 {ln} 字，末字：{text[-1] if text else ''}"
                )
            if lo <= ln <= hi:
                return text

            length_failures += 1
            if length_failures > SEGMENT_LENGTH_MAX_RETRIES:
                catastrophic = ln < max(150, int(seg_target * 0.30))
                if catastrophic and not used_emergency_synopsis:
                    used_emergency_synopsis = True
                    length_failures = 0
                    print(
                        f"     ⚠️ 第 {segment_index + 1} 段仅 {ln} 字，疑似上下文过长或模型未展开；"
                        "已切换极简梗概并重试本幕…"
                    )
                    syn_block = _compact_synopsis_json_for_writer(
                        synopsis_data, emergency=True, synopsis_excerpt=synopsis_excerpt
                    )
                    base_ctx = (
                        f"主题：{topic}\n\n"
                        f"【本幕相关梗概节选（JSON，极简重试）】\n{syn_block}\n\n"
                        f"【全剧共 {n_mo} 幕（勿跳幕、勿提前写后几幕才发生的事）】\n{mo_road}\n\n"
                        f"【当前】第 {segment_index + 1}/{n_mo} 幕「{segment_label}」\n"
                    )
                    if segment_index == 0:
                        user_p = (
                            base_ctx
                            + f"你只写**第 1 幕**正文。\n"
                            + f"【开篇唯一合法形式】正文第一句必须且仅能是："
                            f"「今天你要体验的人生副本是，{opening_topic_phrase(topic)}。」"
                            f"随后立刻接着写，不要复述主题。\n"
                            f"本幕目标约 {seg_target} 字，须落实梗概里入局阶段的关键事实。\n"
                            f"【硬性】本段须输出不少于 {hard_floor} 个汉字的连贯旁白正文（不是提纲、不是对话、不要 JSON）。\n"
                        )
                    else:
                        tail = (
                            prev_full_text[-tail_chars:]
                            if len(prev_full_text) > tail_chars
                            else prev_full_text
                        )
                        hb = (handoff_brief or "").strip()
                        user_p = (
                            base_ctx
                            + f"【统筹给本幕的续写指令（须落实，勿与梗概矛盾）】\n{hb}\n\n"
                            + f"【承接】上一幕结尾（无缝接续，禁止再写开场白「今天你要体验的人生副本是」）：\n"
                            f"「…{tail}」\n\n"
                            f"你只写**第 {segment_index + 1} 幕**正文。本幕目标约 {seg_target} 字。"
                            f"从接续处自然往下写，不要复述已写过的段落。\n"
                            f"【硬性】本段须输出不少于 {hard_floor} 个汉字的连贯旁白正文（不是提纲、不是对话、不要 JSON）。\n"
                        )
                    continue
                if ln < lo:
                    print(
                        f"     ⚠️ 第 {segment_index + 1} 段字数 {ln} 低于理想下限 {lo}，"
                        "已达字数最大重试仍采纳。"
                    )
                else:
                    print(
                        f"     ⚠️ 第 {segment_index + 1} 段字数 {ln} 高于理想上限 {hi}，"
                        "已达字数最大重试仍采纳。"
                    )
                return text
            print(
                f"     🔄 第 {segment_index + 1} 段字数 {ln} 不在 [{lo},{hi}]，"
                f"字数重试 {length_failures}/{SEGMENT_LENGTH_MAX_RETRIES}"
            )
        except Exception as e:
            log_event(
                PHASE_NARRATION,
                f"segment_writer_{segment_index + 1}_{segment_label}",
                "llm_chat",
                ok=False,
                duration_ms=(time.perf_counter() - t_req) * 1000,
                model=MODEL_WRITER,
                attempt=attempt,
                error=str(e),
                extra={"seg_target": seg_target},
            )
            network_failures += 1
            if network_failures > SEGMENT_NETWORK_MAX_RETRIES:
                print(
                    f"     ❌ 第 {segment_index + 1} 段生成异常且已达网络重试上限 "
                    f"{SEGMENT_NETWORK_MAX_RETRIES}: {e}"
                )
                return None
            backoff = SEGMENT_NETWORK_RETRY_BASE_SEC * (2 ** (network_failures - 1))
            print(
                f"     🔄 第 {segment_index + 1} 段生成异常: {e}；"
                f"网络重试 {network_failures}/{SEGMENT_NETWORK_MAX_RETRIES}，"
                f"{backoff:.1f}s 后重试。"
            )
            time.sleep(backoff)


def _patch_narration_length(
    client: OpenAI,
    topic: str,
    synopsis_data: dict,
    text: str,
    need_chars: int,
    *,
    synopsis_excerpt: str | None = None,
) -> str | None:
    """全文略低于下限时，仅在尾部做一次扩写补丁。"""
    if need_chars <= 0:
        return text
    sys_p = """你是旁白写手。在下列正文**末尾**自然续写，保持第二人称与既有冷峻风格，禁止重复开篇句。
只输出**续写部分**（不要重复已有正文）。"""
    tail = text[-1200:] if len(text) > 1200 else text
    stub = (synopsis_excerpt or "").strip() or _patch_synopsis_excerpt_from_mo(
        list(synopsis_data.get("synopsis_acts") or [])
    )
    syn_line = _compact_synopsis_json_for_writer(
        synopsis_data, synopsis_excerpt=stub[: min(1400, int(SYNOPSIS_BODY_MAX_CHARS))]
    )
    user_p = (
        f"主题：{topic}\n梗概节选：{syn_line}\n\n"
        f"当前正文结尾：\n…{tail}\n\n"
        f"请续写约 {need_chars} 字，收束叙事闭环。"
    )
    t0 = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=MODEL_WRITER,
            messages=[{"role": "system", "content": sys_p}, {"role": "user", "content": user_p}],
            max_tokens=min(8192, int(need_chars * 2.5)),
            temperature=0.35,
        )
        ch = response.choices[0] if response.choices else None
        fr = getattr(ch, "finish_reason", None) if ch else None
        extra = _strip_ai_fences(ch.message.content if ch and ch.message else "") or ""
        log_event(
            PHASE_NARRATION,
            "narration_tail_patch",
            "llm_chat",
            ok=True,
            duration_ms=(time.perf_counter() - t0) * 1000,
            model=MODEL_WRITER,
            extra={
                "need_chars": need_chars,
                "finish_reason": fr,
                "patch_out_chars": len(extra),
            },
        )
        if not extra:
            return None
        return text.rstrip() + extra
    except Exception as e:
        log_event(
            PHASE_NARRATION,
            "narration_tail_patch",
            "llm_chat",
            ok=False,
            duration_ms=(time.perf_counter() - t0) * 1000,
            model=MODEL_WRITER,
            error=str(e),
            extra={"need_chars": need_chars},
        )
        print(f"❌ 尾部扩写补丁失败: {e}")
        return None


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
    """阶段 1：生成剧情梗概（分幕 synopsis_acts + 总长上限，见 normalize_synopsis_payload）。"""
    client = get_client()
    print("\n[Step 1] 正在构思核心故事 (小说家梗概模式)...")
    try:
        response = log_llm_chat(
            PHASE_SYNOPSIS,
            "generate_synopsis",
            MODEL_LLM,
            lambda: client.chat.completions.create(
                model=MODEL_LLM,
                messages=[
                    {"role": "system", "content": SYNOPSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": f"请为【{topic}】设计一个硬核利益跃迁副本。"},
                ],
                response_format={"type": "json_object"},
            ),
        )
        raw = json.loads(response.choices[0].message.content)
        return normalize_synopsis_payload(raw)
    except Exception as e:
        print(f"❌ 梗概生成失败: {e}")
        return None


def expand_narration(synopsis_data: dict, topic: str, duration_min: float = DEFAULT_STORY_DURATION_MINUTES):
    """阶段 2：分段扩写旁白并拼接。人物定妆英文提示词由 ref_generator 写入 scripts/refs-prompt.json。"""
    synopsis_data = normalize_synopsis_payload(dict(synopsis_data))
    syn_dur = synopsis_data.get("duration")
    try:
        eff_dur = float(syn_dur) if syn_dur is not None else float(duration_min)
    except (TypeError, ValueError):
        eff_dur = float(duration_min)
    target_chars, min_chars = _compute_narration_targets(eff_dur)
    weights, labels = _pick_segment_plan(target_chars)
    seg_chars = _allocate_segment_chars(target_chars, weights)
    n_seg = len(seg_chars)
    acts_norm = [str(x).strip() for x in (synopsis_data.get("synopsis_acts") or [])]
    mo_slices = _bucket_strings_for_n_segments(acts_norm, n_seg)
    if len(mo_slices) != n_seg or not any(mo_slices):
        mo_slices = _fallback_split_synopsis_text(str(synopsis_data.get("synopsis") or ""), n_seg)
    patch_stub = _patch_synopsis_excerpt_from_mo(mo_slices)
    print(
        f"\n[Step 2] 分段扩写旁白（目标成片约 {eff_dur:g} 分钟 → 全文目标约 {target_chars} 字，"
        f"下限 {min_chars} 字，共 {n_seg} 段）..."
    )
    client = get_client()
    accumulated = ""
    parts: list[str] = []
    tail_n = max(80, int(NARRATION_SEGMENT_TAIL_CHARS))
    handoff = ""

    for i in range(n_seg):
        print(f"     · 正在生成第 {i + 1}/{n_seg} 幕「{labels[i]}」（目标约 {seg_chars[i]} 字）...")
        excerpt = _writer_synopsis_excerpt(mo_slices, i, n_seg)
        seg_text = _generate_one_segment(
            client,
            topic=topic,
            synopsis_data=synopsis_data,
            synopsis_excerpt=excerpt,
            segment_index=i,
            segment_label=labels[i],
            seg_target=seg_chars[i],
            prev_full_text=accumulated,
            tail_chars=tail_n,
            all_labels=labels,
            handoff_brief=handoff,
        )
        if seg_text is None:
            print(f"❌ [FATAL] 第 {i + 1} 段连续失败，终止。")
            return None
        if i > 0:
            seg_text = _strip_overlap_with_previous(accumulated, seg_text)
        if i > 0 and not (seg_text or "").strip():
            print(f"❌ [FATAL] 第 {i + 1} 幕在去重后为空，终止。")
            return None
        parts.append(seg_text)
        accumulated = "".join(parts)

        if i < n_seg - 1:
            print(f"     · 统筹：生成给第 {i + 2} 幕的续写指令...")
            handoff = _handoff_for_next_segment(
                client,
                topic,
                synopsis_data,
                accumulated,
                labels[i + 1],
                i + 2,
                n_seg,
            )

    full_narration = accumulated.strip()
    print(f"     · 拼接完成，全文约 {len(full_narration)} 字")

    if len(full_narration) < min_chars:
        gap = min_chars - len(full_narration)
        print(f"     · 全文低于下限 {gap} 字，尝试尾部扩写补丁...")
        patched = _patch_narration_length(
            client,
            topic,
            synopsis_data,
            full_narration,
            gap + max(80, gap // 8),
            synopsis_excerpt=patch_stub,
        )
        if patched:
            full_narration = patched.strip()

    soft_floor = max(min_chars, int(target_chars * NARRATION_TARGET_SOFT_RATIO))
    for _round in range(NARRATION_TAIL_PATCH_MAX_ROUNDS):
        if len(full_narration) >= soft_floor:
            break
        gap2 = soft_floor - len(full_narration)
        ask = gap2 + max(120, gap2 // 6)
        print(
            f"     · 全文 {len(full_narration)} 字，低于目标软下限 {soft_floor} 字，"
            f"尾部扩写（第 {_round + 1}/{NARRATION_TAIL_PATCH_MAX_ROUNDS} 轮，约 +{ask} 字）..."
        )
        patched2 = _patch_narration_length(
            client, topic, synopsis_data, full_narration, ask, synopsis_excerpt=patch_stub
        )
        if not patched2 or len(patched2.strip()) <= len(full_narration):
            break
        full_narration = patched2.strip()

    # 字数已够但末句没收束（常见于第六幕落在「理想字数带」内却停在半句话；与是否顶满 max_tokens 无必然关系）
    for _ci in range(NARRATION_CLOSE_PATCH_MAX_ROUNDS):
        if _narration_tail_sentence_complete(full_narration):
            break
        ask_close = 420 if _ci == 0 else 220
        tail_preview = full_narration[-56:].replace("\n", " ")
        print(
            f"     · 末句未落在句末标点，尝试收尾扩写（第 {_ci + 1}/"
            f"{NARRATION_CLOSE_PATCH_MAX_ROUNDS} 轮，约 +{ask_close} 字）…"
            f"\n       结尾预览：…{tail_preview}"
        )
        patched_close = _patch_narration_length(
            client,
            topic,
            synopsis_data,
            full_narration,
            ask_close,
            synopsis_excerpt=patch_stub,
        )
        if not patched_close or len(patched_close.strip()) <= len(full_narration):
            print("     ⚠️ 收尾扩写未生效或失败，保留当前正文。")
            break
        full_narration = patched_close.strip()

    if not _is_pure_narration(full_narration, min_chars):
        print(
            f"     ❌ 全文校验未通过（字数 {len(full_narration)} / 下限 {min_chars}，"
            f"或含违禁标记）。可缩短目标时长或放宽 MIN_NARRATION 比例后重试。"
        )
        return None

    print("     ✅ 分段扩写已完成（定妆提示词见 ref_generator → scripts/refs-prompt.json）")
    return {"full_narration": full_narration}


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
    parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_STORY_DURATION_MINUTES,
        help="目标视频时长（分钟）",
    )
    args = parser.parse_args()

    topic = args.topic
    step = args.step
    duration = args.duration
    run_dir = start_new_run(topic=topic) if step in ["all", "synopsis"] else None
    paths = get_paths(create_if_missing=True)
    scripts_dir = paths["scripts_dir"]
    full_story_v6_path = scripts_dir / "full_story_v6.json"
    temp_synopsis_path = scripts_dir / "temp_synopsis.json"

    if step in ["all", "synopsis"]:
        init_project(topic)
        syn_result = generate_synopsis(topic)
        if not syn_result:
            print("❌ [FATAL] 梗概生成失败，流程终止。")
            sys.exit(1)
        syn_result = normalize_synopsis_payload(syn_result)

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
        syn_result = normalize_synopsis_payload(syn_result)

        try:
            effective_duration = float(syn_result.get("duration", duration))
        except (TypeError, ValueError):
            effective_duration = float(duration)

        final_result = expand_narration(syn_result, topic, effective_duration)
        if not final_result:
            print("❌ [FATAL] 文案扩写失败（纯净校验连续未通过），流程终止。")
            sys.exit(1)

        package_data = {
            "metadata": {
                "topic": topic,
                "project_name": topic,
                "era": syn_result.get("era", "现代"),
                "duration": effective_duration,
                "run_id": get_current_run_id(),
            },
            "master_design": final_result,
        }

        try:
            _write_json(full_story_v6_path, package_data)
            vault_backup(full_story_v6_path, f"scripts/{full_story_v6_path.name}")
        except Exception as e:
            print(f"❌ [FATAL] 剧本写入磁盘失败: {e}")
            sys.exit(1)

        print("\n🏆 阶段二 (长文案) 生成完毕！")
        print(f"📍 路径: {full_story_v6_path}")
        if run_dir:
            print(f"🧪 Run-ID 隔离目录: {run_dir}")
        _run_ref_generation(topic)


if __name__ == "__main__":
    main()
