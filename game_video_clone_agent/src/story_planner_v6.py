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
    NARRATION_EXPAND_MODE,
    NARRATION_SEGMENT_COUNT,
    NARRATION_SEGMENT_MAX_TOKENS_CHAR_BUFFER,
    NARRATION_SEGMENT_CH_TO_TOKEN_RATIO,
    NARRATION_SEGMENT_TAIL_CHARS,
    ONE_SHOT_LENGTH_MAX_ATTEMPTS,
    ONE_SHOT_NARRATION_HI_RATIO,
    ONE_SHOT_NARRATION_LO_RATIO,
    SYNOPSIS_BODY_MAX_CHARS,
)
from src.api_audit import PHASE_NARRATION, PHASE_SYNOPSIS, log_event, log_llm_chat
from src.project_vault import init_project, backup as vault_backup
from src.ref_generator import run_ref_process
from src.run_context import start_new_run, get_paths, get_current_run_id

MODEL_WRITER = MODEL_LLM
# 单幕旁白：理想字数带内则采纳；否则最多生成这么多次，仍不达标则取「最接近 seg_target 字数」的一条（不采纳极简梗概兜底）
SEGMENT_LENGTH_MAX_ATTEMPTS = 4
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


def _polish_user_script_system_prompt() -> str:
    n_act = _synopsis_act_target_n()
    return f"""你是一位专业的资深编剧与剧本医生。
任务：请阅读用户提供的原始素材（梗概、片段或小说节选均可），在【完全保留用户原始创意、情节走向和核心设定】的前提下，进行专业润色，并补充与盲盒梗概同规格的结构化字段。

润色要求：
1. 语言风格：使文字更具画面感（Visual Thinking），多用具象动词，少用空泛形容词；**禁止**强行套用「阶层跃迁」「利益算计」等固定套路，除非用户原文已包含类似内核。
2. 节奏与体量：优化起承转合与悬念，整体梗概总长度须符合后续约 1700 字旁白体量的信息密度，且 **synopsis 与 synopsis_acts 拼接总字符数不得超过 {int(SYNOPSIS_BODY_MAX_CHARS)}**（汉字+标点）。
3. 分幕结构：必须输出 synopsis_acts 数组，长度**恰好**为 **{n_act}**；每幕为连续叙事，幕内不要写「第X幕」小标题，按时间顺序串成一条故事线。
4. **行业潜规则 industry_rules**：与盲盒大纲一致，输出 1～4 条数组，概括本作可被影像化的矛盾机制或环境张力（非教条）。

输出：**仅** JSON（键名固定）：
{{
  "synopsis_acts": [共{n_act}个字符串，依次为第1幕…第{n_act}幕],
  "synopsis": "将 synopsis_acts 用两个换行符拼接的全文，与各幕一致",
  "short_title": "12字以内的短片标题，用于飞书卡片抬头",
  "era": "时代背景",
  "identity": "主角身份或称谓",
  "industry_rules": ["……"]
}}"""


def polish_user_script_synopsis(
    raw_user_input: str,
    *,
    feedback: str = "",
    previous_synopsis: dict | None = None,
) -> dict | None:
    """
    投喂剧本润色：返回已通过 normalize_synopsis_payload 前的原始 dict（调用方再 normalize + 打标签）。
    feedback 非空时应在 previous_synopsis 中带入上一轮梗概以便对照修改。
    """
    raw_user_input = (raw_user_input or "").strip()
    if not raw_user_input and not feedback:
        return None
    client = get_client()
    sys_p = _polish_user_script_system_prompt()
    parts: list[str] = []
    if raw_user_input:
        parts.append(f"【用户原始素材】\n{raw_user_input}")
    if feedback.strip():
        parts.append(f"【用户修改意见】\n{feedback.strip()}")
    if previous_synopsis and feedback.strip():
        try:
            slim = {
                "synopsis": previous_synopsis.get("synopsis"),
                "synopsis_acts": previous_synopsis.get("synopsis_acts"),
                "era": previous_synopsis.get("era"),
                "identity": previous_synopsis.get("identity"),
                "industry_rules": previous_synopsis.get("industry_rules"),
            }
            parts.append(f"【当前润色版梗概（供对照修订）】\n{json.dumps(slim, ensure_ascii=False)}")
        except Exception:
            pass
    user_p = "\n\n".join(parts)
    if not user_p.strip():
        return None
    try:
        response = log_llm_chat(
            PHASE_SYNOPSIS,
            "polish_user_script_synopsis",
            MODEL_LLM,
            lambda: client.chat.completions.create(
                model=MODEL_LLM,
                messages=[
                    {"role": "system", "content": sys_p},
                    {"role": "user", "content": user_p},
                ],
                response_format={"type": "json_object"},
            ),
        )
        raw = json.loads(response.choices[0].message.content)
        if not isinstance(raw, dict):
            return None
        return raw
    except Exception as e:
        print(f"❌ 剧本润色失败: {e}")
        return None


def get_client():
    return OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, timeout=60.0)


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


def _is_pure_narration(text: str, min_chars: int, max_chars: int | None = None) -> bool:
    if not text:
        return False
    if re.search(r"\[CUT_?\d+\]", text, re.IGNORECASE):
        return False
    if "<subshot>" in text.lower():
        return False
    s = text.strip()
    if len(s) < min_chars:
        return False
    if max_chars is not None and len(s) > max_chars:
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


def _flatten_assistant_content(msg) -> str:
    """兼容 content 为 str 或 Chat Completions 的多段 text 块（部分网关/SDK）。"""
    if msg is None:
        return ""
    c = getattr(msg, "content", None)
    if c is None:
        return ""
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts: list[str] = []
        for block in c:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
                elif "text" in block:
                    parts.append(str(block.get("text") or ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(c)


def _parse_json_dict_loose(raw: str) -> dict:
    """从模型原文中尽量解析出 JSON 对象（去围栏、截取首尾大括号）。"""
    s = (raw or "").strip().lstrip("\ufeff")
    if not s:
        raise ValueError("empty assistant content after strip")
    candidates: list[str] = []
    seen: set[str] = set()
    for cand in (s, _strip_ai_fences(s)):
        t = cand.strip()
        if t and t not in seen:
            candidates.append(t)
            seen.add(t)
    lo = s.find("{")
    hi = s.rfind("}")
    if lo >= 0 and hi > lo:
        sub = s[lo : hi + 1].strip()
        if sub and sub not in seen:
            candidates.append(sub)
            seen.add(sub)
    last_err: Exception | None = None
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError as e:
            last_err = e
            continue
    tail = repr(last_err) if last_err else "no JSON candidate"
    raise ValueError(f"JSON 解析失败: {tail}")


def _response_to_full_narration_bundle(resp) -> dict:
    """
    从 chat completion 解析 full_narration。
    返回 {"text": str, "finish_reason": ..., "raw_content_chars": int, "out_chars": int}
    """
    choice = resp.choices[0] if resp and resp.choices else None
    if not choice:
        raise ValueError("completion 无 choices")
    msg = choice.message
    finish_reason = getattr(choice, "finish_reason", None)
    refusal = getattr(msg, "refusal", None) if msg is not None else None
    if refusal:
        rf = str(refusal).strip()
        raise ValueError(f"模型拒绝(refusal)，前 400 字：{rf[:400]}")
    raw = _flatten_assistant_content(msg)
    raw_st = raw.strip()
    if not raw_st:
        raise ValueError(f"模型返回空 content（finish_reason={finish_reason!r}）")
    obj = _parse_json_dict_loose(raw_st)
    fn = str(obj.get("full_narration") or "").strip()
    fn = _strip_ai_fences(fn).strip()
    if not fn:
        raise ValueError("JSON 内 full_narration 缺失或为空")
    return {
        "text": fn,
        "finish_reason": finish_reason,
        "raw_content_chars": len(raw_st),
        "out_chars": len(fn),
    }


def _chat_json_full_narration(
    client: OpenAI,
    *,
    sys_p: str,
    user_p: str,
    max_tokens: int,
    temperature: float,
) -> dict:
    """
    chat.completions + 解析 full_narration。
    若 json_object 模式下 content 为空，自动去掉 response_format 再请求一次（兼容部分网关）。
    """
    common: dict = dict(
        model=MODEL_WRITER,
        messages=[
            {"role": "system", "content": sys_p},
            {"role": "user", "content": user_p},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    resp = client.chat.completions.create(
        **common,
        response_format={"type": "json_object"},
    )
    try:
        return _response_to_full_narration_bundle(resp)
    except ValueError as e:
        err_s = str(e)
        if "空 content" in err_s or "empty assistant content" in err_s.lower():
            print(
                "     ⚠️ response_format=json_object 时 content 为空，"
                "重试一次（不传 response_format）…"
            )
            resp2 = client.chat.completions.create(**common)
            return _response_to_full_narration_bundle(resp2)
        raise


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


def _pick_user_opening_line(synopsis_data: dict) -> str:
    """投喂路径可选：用户指定的首句（没有则空）。"""
    line = str((synopsis_data or {}).get("opening_line_user") or "").strip()
    if not line:
        return ""
    # 去掉包裹引号，避免模型输出双引号开头
    return line.strip("“”\"'").strip()


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
    强制输出【衔接点】+【起手建议】+【本幕任务】，确保段间无缝连接。
    """
    sys_p = """你是编剧统筹。根据故事梗概与**已写旁白正文**，为下一位「旁白写手」写一段**续写指令**。

请严格按以下三段式输出（约 100～300 个汉字，禁止 markdown 分条，用连续文字）：

【衔接点】精确描述上一段结尾的场景状态：主角此刻在何处？正在做什么？处于什么情绪/处境？最近完成了什么动作？（让写手清楚知道自己从哪开始接）

【起手建议】给下一段写手一个具体的「第一句话」建议——下一段第一句应该写什么动作、什么画面（不是直接给旁白正文，而是描述起手方向，例如「从他推开办公室门、面试官头也没抬开始写」）

【本幕任务】根据梗概，下一幕「{label_hint}」必须推进的剧情节点（含具体事件、数字、转折）；禁止另起无关故事或改人设。""".replace("{label_hint}", next_label)
    tail = text_so_far[-3000:] if len(text_so_far) > 3000 else text_so_far
    syn_s = json.dumps(synopsis_data, ensure_ascii=False)[:4500]
    user_p = (
        f"主题：{topic}\n\n"
        f"【梗概 JSON 节选】\n{syn_s}\n\n"
        f"【已写旁白共 {len(text_so_far)} 字，下为近文】\n…{tail}\n\n"
        f"【下一任务】第 {next_1based}/{total_mo} 幕「{next_label}」。"
        f"请按【衔接点】+【起手建议】+【本幕任务】三段式输出续写指令。"
    )
    t0 = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=MODEL_LLM,
            messages=[
                {"role": "system", "content": sys_p},
                {"role": "user", "content": user_p},
            ],
            max_tokens=600,
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
        return h[:1000]
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
            f"【衔接点】上一段结尾的场景与情绪请自行从上文末尾推断。\n"
            f"【起手建议】从上文最后一个动作或画面自然延伸，避免另起场景。\n"
            f"【本幕任务】进入第 {next_1based} 幕「{next_label}」："
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
    emergency=True 时进一步缩短 excerpt（保留供其它调用场景）。
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


def _segment_system_prompt(seg_target: int, *, neutral: bool = False) -> str:
    if neutral:
        return f"""你是一位专业、克制的短视频旁白写手（中性叙事气质）。
任务：按用户指示写出**一段**沉浸式旁白（不是全文，只是连续叙事中的一段）。

【写作铁律】
1. **一镜到底**：禁止使用段落小标题。用具体场景、动作与因果推进；语气中性、可读性强，**避免**堆砌冷酷算计话术。
2. **第二人称**：全程使用「你」，句子长短相间，口语化但忌浮夸。
3. **纯净文本**：禁止 <subshot>、禁止 [CUT]、禁止任何分镜标签。
4. **本段体量**：本段目标约 **{seg_target}** 字（允许 ±10%）。

输出要求：**只输出旁白正文**，不要标题、不要 JSON、不要代码围栏、不要解释。"""
    return f"""你是一个极其冷峻、犀利的短视频旁白文案大师。
任务：按用户指示写出**一段**沉浸式旁白（不是全文，只是连续叙事中的一段）。

【写作铁律】
1. **一镜到底**：禁止使用段落小标题（如 Level、第一阶段）。用时间流逝、场景升级、数字与利益推进。
2. **第二人称**：全程使用「你」，极简冷峻，少用形容词。
3. **纯净文本**：禁止 <subshot>、禁止 [CUT]、禁止任何分镜标签。
4. **本段体量**：本段目标约 **{seg_target}** 字（允许 ±10%）。

输出要求：**只输出旁白正文**，不要标题、不要 JSON、不要代码围栏、不要解释。"""


def _segment_length_retry_addon(
    *,
    lo: int,
    hi: int,
    seg_target: int,
    prev_ln: int,
    prev_too_long: bool,
) -> str:
    """字数未命中理想带时的追加指令：收紧篇幅但不删情节，少修饰、叙事更直接。"""
    if prev_too_long:
        return (
            f"\n\n【字数修正（重试）】你上一稿约 **{prev_ln}** 字，超出理想上限 **{hi}** 字。"
            f"请重写本幕正文，使全文汉字数落在 **{lo}～{hi}** 之间（目标约 **{seg_target}** 字）。\n"
            "**禁止删减情节主干与梗概中的关键事实**；只能压缩篇幅：少用形容词与堆砌修辞，句子写短，叙事更直接，"
            "不写重复评价句；保持第二人称与开篇格式要求不变。\n"
            "只输出正文。"
        )
    return (
        f"\n\n【字数修正（重试）】你上一稿约 **{prev_ln}** 字，低于理想下限 **{lo}** 字。"
        f"请重写本幕正文，使全文汉字数落在 **{lo}～{hi}** 之间（目标约 **{seg_target}** 字）。\n"
        "在**不编造与梗概矛盾的新剧情**前提下，补足必要的过程与因果；仍须避免灌水重复句。\n"
        "只输出正文。"
    )


def _pick_closest_segment_candidate(
    candidates: list[tuple[str, int]], seg_target: int
) -> str:
    if not candidates:
        return ""
    return min(candidates, key=lambda item: abs(item[1] - seg_target))[0]


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
    neutral_narration: bool = False,
) -> str | None:
    sys_p = _segment_system_prompt(seg_target, neutral=neutral_narration)
    # max_tokens：按「目标汉字 + 缓冲」× 字/token 粗估，显著低于旧版 max(2048, seg*2.6)，机械抑制超长输出
    _tok_est = (seg_target + NARRATION_SEGMENT_MAX_TOKENS_CHAR_BUFFER) * float(
        NARRATION_SEGMENT_CH_TO_TOKEN_RATIO
    )
    max_tokens = min(16384, max(128, int(_tok_est)))
    n_mo = len(all_labels)
    mo_road = _format_mo_roadmap(all_labels)
    syn_block = _compact_synopsis_json_for_writer(
        synopsis_data, synopsis_excerpt=synopsis_excerpt
    )
    hard_floor = max(200, int(seg_target * 0.55))
    opening_line_user = _pick_user_opening_line(synopsis_data)
    base_ctx = (
        f"主题：{topic}\n\n"
        f"【本幕相关梗概节选（JSON）】\n{syn_block}\n\n"
        f"【全剧共 {n_mo} 幕（勿跳幕、勿提前写后几幕才发生的事）】\n{mo_road}\n\n"
        f"【当前】第 {segment_index + 1}/{n_mo} 幕「{segment_label}」\n"
    )

    if segment_index == 0:
        if neutral_narration:
            if opening_line_user:
                user_p = (
                    base_ctx
                    + f"你只写**第 1 幕**正文。\n"
                    + f"【开篇固定句（必须逐字一致）】第一句只能是：{opening_line_user}\n"
                    + "该句输出后，必须从**第二句**开始自然续写，不得改写、扩写或重复第一句。\n"
                    f"本幕目标约 {seg_target} 字，须落实梗概里开局阶段的关键事实。\n"
                    f"【硬性】本段须输出不少于 {hard_floor} 个汉字的连贯旁白正文（不是提纲、不是对话、不要 JSON）。\n"
                )
            else:
                user_p = (
                    base_ctx
                    + f"你只写**第 1 幕**正文。\n"
                    + "【开篇】第一句必须是**单独一句**开场钩子（不超过 40 个汉字），紧贴梗概、有画面感，"
                    "**禁止**使用固定句式「今天你要体验的人生副本是」。写完第一句后立刻展开叙事。\n"
                    f"本幕目标约 {seg_target} 字，须落实梗概里开局阶段的关键事实。\n"
                    f"【硬性】本段须输出不少于 {hard_floor} 个汉字的连贯旁白正文（不是提纲、不是对话、不要 JSON）。\n"
                )
        else:
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
    length_candidates: list[tuple[str, int]] = []
    prev_ln: int | None = None
    prev_too_long: bool | None = None
    while True:
        attempt += 1
        try:
            user_content = user_p
            if prev_ln is not None and prev_too_long is not None:
                lo_hint = int(seg_target * 0.78)
                hi_hint = int(seg_target * 1.18)
                user_content = user_p + _segment_length_retry_addon(
                    lo=lo_hint,
                    hi=hi_hint,
                    seg_target=seg_target,
                    prev_ln=prev_ln,
                    prev_too_long=prev_too_long,
                )
            t_req = time.perf_counter()
            response = client.chat.completions.create(
                model=MODEL_WRITER,
                messages=[
                    {"role": "system", "content": sys_p},
                    {"role": "user", "content": user_content},
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
            length_candidates.append((text, ln))
            prev_ln = ln
            prev_too_long = ln > hi
            if length_failures >= SEGMENT_LENGTH_MAX_ATTEMPTS:
                chosen = _pick_closest_segment_candidate(length_candidates, seg_target)
                pick_ln = len(chosen)
                print(
                    f"     ⚠️ 第 {segment_index + 1} 幕已尝试 {SEGMENT_LENGTH_MAX_ATTEMPTS} 次仍未落入 [{lo},{hi}]；"
                    f"采纳最接近目标 **{seg_target}** 字的一稿（约 **{pick_ln}** 字）。"
                )
                return chosen
            print(
                f"     🔄 第 {segment_index + 1} 段字数 {ln} 不在 [{lo},{hi}]，"
                f"字数重试 {length_failures}/{SEGMENT_LENGTH_MAX_ATTEMPTS}"
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
    neutral: bool = False,
) -> str | None:
    """全文略低于下限时，仅在尾部做一次扩写补丁。"""
    if need_chars <= 0:
        return text
    if neutral:
        sys_p = """你是旁白写手。在下列正文**末尾**自然续写，保持第二人称与上文中性叙事气质一致，禁止重复开篇句。
只输出**续写部分**（不要重复已有正文）。"""
    else:
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


def _build_one_shot_acts_system_prompt(
    topic: str,
    synopsis_data: dict,
    *,
    target_chars: int,
    char_lo: int,
    char_hi: int,
    n_acts: int,
    neutral_narration: bool,
) -> str:
    """一次性按 synopsis_acts 顺序扩写全文的系统提示（与分段路径的开篇/气质对齐）。"""
    opening_user = _pick_user_opening_line(synopsis_data)
    op = opening_topic_phrase(topic)

    plot_lock = f"""【剧情锁（必须遵守）】
- 你必须严格按照用户消息中的【分幕梗概】从第 1 幕依次写到第 {n_acts} 幕；不得跳幕、不得合并两幕、不得调换顺序。
- 每一幕只扩写该幕梗概内的情节与因果；不得引入与任一幕梗概矛盾的重大设定；不得用「第X幕」等小标题分段。
- 幕与幕之间仅用时间流逝、场景升级、状态与数字变化自然衔接；禁止 Level/阶段 类小标题。"""

    size_rule = f"""【字数】全文汉字与标点总字符数必须落在 **{char_lo}～{char_hi}** 之间，**目标约 {target_chars} 字**（与成片时长预设一致）。"""

    person_rule = (
        "3. **第二人称**：全程使用「你」；极简冷峻，少用形容词，多用短句、动作、数字与利益推进。"
        if not neutral_narration
        else "3. **第二人称**：全程使用「你」。"
    )
    common_tail = f"""{plot_lock}

【写作铁律】
2. **一镜到底**：用具体场景、动作与因果推进；禁止段落小标题。
{person_rule}
4. **纯净文本**：禁止 <subshot>、禁止 [CUT]、禁止任何分镜标签；只输出 JSON 中的正文。
5. {size_rule}

【输出】仅 JSON（键名固定）：
{{
  "full_narration": "逐幕扩写后的完整旁白（纯净文本，无小标题）"
}}"""

    if neutral_narration:
        if opening_user:
            rule1 = (
                f"1. **开篇固定句**：正文第一句必须逐字为：{opening_user}\n"
                "   输出该句后从第二句起续写，不得改写、扩写或重复第一句。"
            )
            tone = "语气中性、克制、可读性强，避免堆砌冷酷算计话术。"
        else:
            rule1 = (
                "1. **开篇**：第一句必须是**单独一句**开场钩子（不超过 40 个汉字），紧贴梗概、有画面感，"
                "**禁止**使用固定句式「今天你要体验的人生副本是」。第二句起立刻展开叙事。"
            )
            tone = "语气中性、克制、可读性强，避免堆砌冷酷算计话术。"
        return f"""你是一位专业、克制的短视频旁白写手（中性叙事气质）。
任务：根据用户消息中的【分幕梗概】，将故事扩写为**一篇**沉浸式旁白，并输出 JSON。

{tone}

{rule1}
{common_tail}"""

    rule1 = (
        "1. **唯一合法开头**：正文第一句必须且仅能是："
        f"「今天你要体验的人生副本是，{op}。」"
        "不许有其他前缀或后缀；随后立刻接着写，不要复述主题。"
    )
    return f"""你是一个极其冷峻、犀利的短视频旁白文案大师。
任务：根据用户消息中的【分幕梗概】，将「你」在副本中的这一生扩写为**一篇**沉浸式纯净长文案，并输出 JSON。

{rule1}

{common_tail}

【视觉与美术】人物定妆英文提示词由定妆流水线写入 scripts/refs-prompt.json；勿在 JSON 中输出 character_anchors。"""


def _build_user_content_one_shot_acts(
    topic: str,
    synopsis_data: dict,
    acts_norm: list[str],
    *,
    char_lo: int,
    char_hi: int,
    target_chars: int,
) -> str:
    lines = [f"第{i}幕梗概：{act}" for i, act in enumerate(acts_norm, start=1)]
    acts_block = "\n".join(lines)
    slim = {
        "era": synopsis_data.get("era"),
        "identity": synopsis_data.get("identity"),
        "duration": synopsis_data.get("duration"),
    }
    slim_s = json.dumps(slim, ensure_ascii=False)
    n = len(acts_norm)
    return (
        f"主题：{topic}\n\n"
        f"【结构化辅助信息】\n{slim_s}\n\n"
        f"【分幕梗概】（共 {n} 幕，请严格按第 1 幕→第 {n} 幕顺序逐幕扩写为**一篇连贯旁白**，"
        f"不得跳幕或合并；全文总字符数须在 {char_lo}～{char_hi} 之间，目标约 {target_chars} 字）\n"
        f"{acts_block}\n\n"
        "请输出 JSON（仅含 full_narration）。"
    )


def _one_shot_length_retry_addon(
    *,
    prev_ln: int,
    char_lo: int,
    char_hi: int,
    target_chars: int,
    prev_too_long: bool,
) -> str:
    if prev_too_long:
        return (
            f"\n\n【字数修正（重试）】上一稿约 {prev_ln} 字，超过上限 {char_hi}。"
            f"请重写 JSON，使 full_narration 总字符数落在 **{char_lo}～{char_hi}**（目标约 **{target_chars}** 字）。\n"
            "**禁止删减或改写分幕梗概中的剧情主干与关键事实**；只能删繁就简、压缩修辞与重复句；逐幕顺序与开篇铁律不变。\n"
            "只输出 JSON。"
        )
    return (
        f"\n\n【字数修正（重试）】上一稿约 {prev_ln} 字，低于下限 {char_lo}。"
        f"请重写 JSON，使 full_narration 落在 **{char_lo}～{char_hi}**（目标约 **{target_chars}** 字）。\n"
        "在**不编造与梗概矛盾的新剧情**前提下补足过程与因果；逐幕顺序与开篇铁律不变。\n"
        "只输出 JSON。"
    )


def _pick_closest_one_shot_candidate(
    candidates: list[tuple[str, int]],
    *,
    target_chars: int,
    char_lo: int,
    char_hi: int,
) -> str:
    if not candidates:
        return ""
    in_band = [c for c in candidates if char_lo <= c[1] <= char_hi]
    if in_band:
        return min(in_band, key=lambda x: abs(x[1] - target_chars))[0]
    return min(candidates, key=lambda x: abs(x[1] - target_chars))[0]


def _compress_full_narration_overflow(
    client: OpenAI,
    topic: str,
    synopsis_data: dict,
    text: str,
    char_hi: int,
    *,
    neutral: bool,
) -> str | None:
    """超长时单次压缩到不超过 char_hi（不改变第二人称与梗概事实）。"""
    if len(text) <= char_hi:
        return text
    if neutral:
        sys_p = f"""你是编辑。下列旁白超过 {char_hi} 字。在不改变剧情顺序与梗概事实、保持第二人称与中性气质的前提下压缩删繁，
使 full_narration 总字符数**不超过 {char_hi}**。禁止新增重大情节。只输出 JSON：{{"full_narration":"..."}}。"""
    else:
        sys_p = f"""你是编辑。下列旁白超过 {char_hi} 字。在不改变剧情顺序与梗概事实、保持第二人称与冷峻风格的前提下压缩删繁，
使 full_narration 总字符数**不超过 {char_hi}**。禁止新增重大情节。只输出 JSON：{{"full_narration":"..."}}。"""
    user_p = f"主题：{topic}\n\n【须压缩的旁白】\n{text}"
    max_tokens = min(8192, int(char_hi * float(NARRATION_SEGMENT_CH_TO_TOKEN_RATIO) * 1.4))
    try:

        def _inner():
            return _chat_json_full_narration(
                client,
                sys_p=sys_p,
                user_p=user_p,
                max_tokens=max_tokens,
                temperature=0.2,
            )["text"]

        out = log_llm_chat(
            PHASE_NARRATION,
            "expand_narration_one_shot_compress",
            MODEL_WRITER,
            _inner,
        )
        return out if out else None
    except Exception as e:
        print(f"     ⚠️ 超长压缩失败: {e}")
        return None


def _generate_one_shot_narration_from_acts(
    client: OpenAI,
    topic: str,
    synopsis_data: dict,
    acts_norm: list[str],
    *,
    target_chars: int,
    char_lo: int,
    char_hi: int,
    neutral_narration: bool,
) -> str | None:
    n_acts = len(acts_norm)
    sys_p = _build_one_shot_acts_system_prompt(
        topic,
        synopsis_data,
        target_chars=target_chars,
        char_lo=char_lo,
        char_hi=char_hi,
        n_acts=n_acts,
        neutral_narration=neutral_narration,
    )
    base_user = _build_user_content_one_shot_acts(
        topic,
        synopsis_data,
        acts_norm,
        char_lo=char_lo,
        char_hi=char_hi,
        target_chars=target_chars,
    )
    max_tokens = min(
        16384,
        max(
            512,
            int(
                (char_hi + NARRATION_SEGMENT_MAX_TOKENS_CHAR_BUFFER)
                * float(NARRATION_SEGMENT_CH_TO_TOKEN_RATIO)
            ),
        ),
    )
    candidates: list[tuple[str, int]] = []
    user_p = base_user
    prev_ln: int | None = None
    prev_too_long: bool | None = None
    chosen: str | None = None

    for attempt in range(1, ONE_SHOT_LENGTH_MAX_ATTEMPTS + 1):
        print(f"     · 一次性按幕扩写（尝试 {attempt}/{ONE_SHOT_LENGTH_MAX_ATTEMPTS}）…")
        if prev_ln is not None and prev_too_long is not None:
            user_p = base_user + _one_shot_length_retry_addon(
                prev_ln=prev_ln,
                char_lo=char_lo,
                char_hi=char_hi,
                target_chars=target_chars,
                prev_too_long=prev_too_long,
            )
        try:

            def _do_one_shot_llm():
                b = _chat_json_full_narration(
                    client,
                    sys_p=sys_p,
                    user_p=user_p,
                    max_tokens=max_tokens,
                    temperature=0.35,
                )
                print(
                    "     · LLM 返回 "
                    f"raw {b['raw_content_chars']} 字，旁白 {b['out_chars']} 字，"
                    f"finish_reason={b['finish_reason']!r}"
                )
                return b

            bundle = log_llm_chat(
                PHASE_NARRATION,
                "expand_narration_one_shot_acts",
                MODEL_WRITER,
                _do_one_shot_llm,
                attempt=attempt,
                extra={
                    "char_lo": char_lo,
                    "char_hi": char_hi,
                    "max_tokens": max_tokens,
                },
            )
            text = bundle["text"]
            finish_reason = bundle.get("finish_reason")
            ln = len(text)
            if finish_reason == "length":
                print(
                    f"     ⚠️ 一次性扩写返回 finish_reason=length（可能撞 max_tokens），"
                    f"本稿 {ln} 字"
                )
            candidates.append((text, ln))
            if char_lo <= ln <= char_hi:
                chosen = text
                break
            prev_ln = ln
            prev_too_long = ln > char_hi
            if attempt >= ONE_SHOT_LENGTH_MAX_ATTEMPTS:
                chosen = _pick_closest_one_shot_candidate(
                    candidates,
                    target_chars=target_chars,
                    char_lo=char_lo,
                    char_hi=char_hi,
                )
                print(
                    f"     ⚠️ 已尝试 {ONE_SHOT_LENGTH_MAX_ATTEMPTS} 次仍未落入 [{char_lo},{char_hi}]；"
                    f"采纳最接近目标 **{target_chars}** 字的一稿（约 **{len(chosen)}** 字）。"
                )
                break
            print(
                f"     🔄 全文 {ln} 字不在 [{char_lo},{char_hi}]，"
                f"字数重试 {attempt}/{ONE_SHOT_LENGTH_MAX_ATTEMPTS}"
            )
        except Exception as e:
            print(f"     ❌ 一次性扩写失败: {e}")
            return None

    if not chosen or not chosen.strip():
        return None
    if len(chosen) > char_hi:
        print(f"     · 全文 {len(chosen)} 字超过上限 {char_hi}，尝试压缩到区间内…")
        compressed = _compress_full_narration_overflow(
            client, topic, synopsis_data, chosen, char_hi, neutral=neutral_narration
        )
        if compressed and len(compressed) <= char_hi:
            chosen = compressed
        elif compressed:
            print(f"     ⚠️ 压缩后仍 {len(compressed)} 字，保留压缩稿继续后处理。")
            chosen = compressed
    return chosen


def _stitch_segment_seams(
    client: OpenAI,
    topic: str,
    full_narration: str,
    neutral_narration: bool,
) -> str:
    """
    分段拼接后，对全文做一次衔接润色：修复段间可能存在的场景跳跃、重复、人称不一致等问题。
    不改变剧情主干与事实，只打磨段缝。
    """
    if neutral_narration:
        sys_p = """你是一位专业文字编辑。下面是一篇由多个段落拼接而成的旁白全文。请只做一件事：找出段落衔接处存在的不顺之处，并修顺。

可修复的问题包括（但不限于）：
- 场景突然跳跃（上一句在A地，下一句突然跳到B地，中间缺过渡）
- 同一件事或同一个动作说了两次（如「他举起枪举起枪」）
- 人称/主语突然消失或混乱
- 两个段落拼接处读起来像两篇文章的断口

修复规则：
1. 只在衔接不顺处做最小修改，不要重写整篇
2. 保持第二人称、叙事语气和原文风格不变
3. 不新增剧情、不删改梗概事实
4. 输出修复后的**完整全文**（不是只输出修改部分）"""
    else:
        sys_p = """你是一位专业文字编辑。下面是一篇由多个段落拼接而成的冷峻风格旁白全文。请只做一件事：找出段落衔接处存在的不顺之处，并修顺。

可修复的问题包括（但不限于）：
- 场景突然跳跃（上一句在A地，下一句突然跳到B地，中间缺过渡）
- 同一件事或同一个动作说了两次（如「他举起枪举起枪」）
- 人称/主语突然消失或混乱
- 两个段落拼接处读起来像两篇文章的断口

修复规则：
1. 只在衔接不顺处做最小修改，不要重写整篇
2. 保持第二人称、冷峻叙事语气和原文风格不变
3. 不新增剧情、不删改梗概事实
4. 输出修复后的**完整全文**（不是只输出修改部分）"""

    user_p = f"主题：{topic}\n\n【待修复的衔接不顺处】\n{full_narration}"

    # 输入可能很长，max_tokens 按原文长度 1.2 倍估算
    est_tokens = min(16384, max(512, int(len(full_narration) * float(NARRATION_SEGMENT_CH_TO_TOKEN_RATIO) * 1.3)))
    t0 = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=MODEL_WRITER,
            messages=[
                {"role": "system", "content": sys_p},
                {"role": "user", "content": user_p},
            ],
            max_tokens=est_tokens,
            temperature=0.2,
        )
        ch = response.choices[0] if response.choices else None
        result = _strip_ai_fences(ch.message.content if ch and ch.message else "") or ""
        log_event(
            PHASE_NARRATION,
            "stitch_segment_seams",
            "llm_chat",
            ok=True,
            duration_ms=(time.perf_counter() - t0) * 1000,
            model=MODEL_WRITER,
            extra={"in_chars": len(full_narration), "out_chars": len(result)},
        )
        if not result or len(result) < len(full_narration) * 0.6:
            print("     ⚠️ 衔接润色返回过短，保留原文。")
            return full_narration
        return result.strip()
    except Exception as e:
        log_event(
            PHASE_NARRATION,
            "stitch_segment_seams",
            "llm_chat",
            ok=False,
            duration_ms=(time.perf_counter() - t0) * 1000,
            model=MODEL_WRITER,
            error=str(e),
            extra={"in_chars": len(full_narration)},
        )
        print(f"     ⚠️ 衔接润色失败（{e}），保留原文继续。")
        return full_narration


def _finalize_narration_after_draft(
    client: OpenAI,
    topic: str,
    synopsis_data: dict,
    full_narration: str,
    min_chars: int,
    target_chars: int,
    patch_stub: str,
    neutral_narration: bool,
    *,
    max_chars: int | None,
    draft_label: str,
    success_label: str,
) -> dict | None:
    """尾部扩写、软下限、句末收尾与纯净校验（分段与一次性共用）。"""
    full_narration = full_narration.strip()
    print(f"     · {draft_label}，全文约 {len(full_narration)} 字")

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
            neutral=neutral_narration,
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
            client,
            topic,
            synopsis_data,
            full_narration,
            ask,
            synopsis_excerpt=patch_stub,
            neutral=neutral_narration,
        )
        if not patched2 or len(patched2.strip()) <= len(full_narration):
            break
        full_narration = patched2.strip()

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
            neutral=neutral_narration,
        )
        if not patched_close or len(patched_close.strip()) <= len(full_narration):
            print("     ⚠️ 收尾扩写未生效或失败，保留当前正文。")
            break
        full_narration = patched_close.strip()

    if max_chars is not None and len(full_narration) > max_chars:
        print(
            f"     · 后处理后全文 {len(full_narration)} 字仍超过上限 {max_chars}，尝试压缩…"
        )
        compressed = _compress_full_narration_overflow(
            client, topic, synopsis_data, full_narration, max_chars, neutral=neutral_narration
        )
        if compressed:
            full_narration = compressed.strip()

    if not _is_pure_narration(full_narration, min_chars, max_chars):
        hi_msg = f"、上限 {max_chars}" if max_chars is not None else ""
        print(
            f"     ❌ 全文校验未通过（字数 {len(full_narration)} / 下限 {min_chars}{hi_msg}，"
            f"或含违禁标记）。可缩短目标时长或放宽 MIN_NARRATION 比例后重试；"
            f"分段模式可设置环境变量 NARRATION_EXPAND_MODE=segmented。"
        )
        return None

    print(success_label)
    return {"full_narration": full_narration}


def expand_narration(synopsis_data: dict, topic: str, duration_min: float = DEFAULT_STORY_DURATION_MINUTES):
    """阶段 2：旁白扩写。默认按 synopsis_acts 一次性扩写；可选分段模式（见 style_config.NARRATION_EXPAND_MODE）。"""
    synopsis_data = normalize_synopsis_payload(dict(synopsis_data))
    neutral_narration = str(synopsis_data.get("story_source") or "") == "user_script"
    syn_dur = synopsis_data.get("duration")
    try:
        eff_dur = float(syn_dur) if syn_dur is not None else float(duration_min)
    except (TypeError, ValueError):
        eff_dur = float(duration_min)
    target_chars, min_chars = _compute_narration_targets(eff_dur)
    char_lo = max(1, int(target_chars * ONE_SHOT_NARRATION_LO_RATIO))
    char_hi = max(char_lo + 1, int(target_chars * ONE_SHOT_NARRATION_HI_RATIO))
    acts_norm = [str(x).strip() for x in (synopsis_data.get("synopsis_acts") or []) if str(x).strip()]

    if NARRATION_EXPAND_MODE == "one_shot_acts":
        if not acts_norm:
            print("❌ [FATAL] synopsis_acts 为空，无法按幕一次性扩写。")
            return None
        patch_stub = _patch_synopsis_excerpt_from_mo(acts_norm)
        print(
            f"\n[Step 2] 一次性按幕扩写旁白（NARRATION_EXPAND_MODE=one_shot_acts；"
            f"目标成片约 {eff_dur:g} 分钟 → 全文目标约 {target_chars} 字，"
            f"理想区间 {char_lo}～{char_hi} 字，下限 {min_chars} 字，共 {len(acts_norm)} 幕梗概）..."
        )
        client = get_client()
        draft = _generate_one_shot_narration_from_acts(
            client,
            topic,
            synopsis_data,
            acts_norm,
            target_chars=target_chars,
            char_lo=char_lo,
            char_hi=char_hi,
            neutral_narration=neutral_narration,
        )
        if not draft:
            print("❌ [FATAL] 一次性按幕扩写失败。")
            return None
        return _finalize_narration_after_draft(
            client,
            topic,
            synopsis_data,
            draft,
            min_chars,
            target_chars,
            patch_stub,
            neutral_narration,
            max_chars=char_hi,
            draft_label="一次性扩写初稿就绪",
            success_label="     ✅ 一次性按幕扩写已完成（定妆提示词见 ref_generator → scripts/refs-prompt.json）",
        )

    weights, labels = _pick_segment_plan(target_chars)
    seg_chars = _allocate_segment_chars(target_chars, weights)
    n_seg = len(seg_chars)
    acts_all = [str(x).strip() for x in (synopsis_data.get("synopsis_acts") or [])]
    mo_slices = _bucket_strings_for_n_segments(acts_all, n_seg)
    if len(mo_slices) != n_seg or not any(mo_slices):
        mo_slices = _fallback_split_synopsis_text(str(synopsis_data.get("synopsis") or ""), n_seg)
    patch_stub = _patch_synopsis_excerpt_from_mo(mo_slices)
    print(
        f"\n[Step 2] 分段扩写旁白（NARRATION_EXPAND_MODE=segmented；目标成片约 {eff_dur:g} 分钟 → 全文目标约 {target_chars} 字，"
        f"下限 {min_chars} 字，共 {n_seg} 段）..."
    )
    client = get_client()
    accumulated = ""
    parts: list[str] = []
    tail_n = max(500, int(NARRATION_SEGMENT_TAIL_CHARS))
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
            neutral_narration=neutral_narration,
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
    print("     · 分段拼接完成，执行衔接润色（修复段间可能的断层与重复）…")
    full_narration = _stitch_segment_seams(client, topic, full_narration, neutral_narration)
    return _finalize_narration_after_draft(
        client,
        topic,
        synopsis_data,
        full_narration,
        min_chars,
        target_chars,
        patch_stub,
        neutral_narration,
        max_chars=None,
        draft_label="分段拼接完成",
        success_label="     ✅ 分段扩写已完成（定妆提示词见 ref_generator → scripts/refs-prompt.json）",
    )


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
                "story_source": syn_result.get("story_source") or "blind_box",
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
