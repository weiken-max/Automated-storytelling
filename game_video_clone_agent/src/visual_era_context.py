"""
分镜与宫格生图共用的「时代背景」短片段：仅使用 metadata.era 截断后的文案，不写死古代/现代禁令，
避免与现代题材冲突。
"""
from __future__ import annotations

from typing import Any

# 用户约定：时代摘要宜短，防止 prompt 过长
MAX_ERA_CHARS = 56


def clip_era_text(era_raw: Any, max_chars: int = MAX_ERA_CHARS) -> str:
    """
    将 JSON 中的 era 安全转为短字符串。
    - None / 空串 / 仅空白：返回 ""
    - 数字等非 str：str() 后再 strip，避免 .strip() 在 int 上 AttributeError
    - bool：JSON 里误写 true/false 时视为无效，返回 ""（避免 "True"/"False" 进 prompt）
    """
    if era_raw is None or isinstance(era_raw, bool):
        s = ""
    else:
        s = str(era_raw).strip()
    if not s:
        return ""
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1] + "…"


def build_writer_era_section(era_raw: Any) -> str:
    """Step1 写 visual_prompt 时注入 system_prompt；无 era 则不注入。"""
    clipped = clip_era_text(era_raw)
    if not clipped:
        return ""
    return (
        "【时代背景】\n"
        f"本片时空设定如下，各分镜的环境、服饰、器物须与此一致：{clipped}\n\n"
    )


def build_image_global_prefix(era_raw: Any) -> str:
    """Step2 宫格生图极短前缀；无 era 则不添加。"""
    clipped = clip_era_text(era_raw)
    if not clipped:
        return ""
    return f"Global setting for all panels: {clipped}\n\n"
