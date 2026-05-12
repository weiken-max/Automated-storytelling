"""
当前 Run 目录下「后台」API 调用审计：按成片阶段分子文件夹，追加写入 calls.jsonl。

路径：data/runs/<run_id>/后台/<阶段>/calls.jsonl；若无激活 Run，则写入 feishu/后台/… 兜底。

每条记录为「一块」易读 JSON（indent=2），块与块之间用分隔线隔开，便于人眼扫读。
同一条 step 出现多次（attempt 递增）通常表示：分段写手在按「理想字数区间」自动重试，
并非流水线重复跑了整段剧情多遍。

阶段目录与含义：

- 000-飞书助手  PHASE_FEISHU_BOT
- 001-梗概  PHASE_SYNOPSIS
- 002-旁白  PHASE_NARRATION（segment_writer_* / handoff_next_segment / narration_tail_patch 等）
- 003-定妆  PHASE_CASTING
- 004-音频与节拍  PHASE_AUDIO_BEATS
- 005-分镜与画面  PHASE_STORYBOARD
- 006-宫格生图  PHASE_GRID
- 007-组装成片  PHASE_ASSEMBLE
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()

BASE_DIR = Path(__file__).resolve().parent.parent

# 分段写手理想字数带（与 story_planner_v6._generate_one_segment 一致）
_SEGMENT_LO_RATIO = 0.78
_SEGMENT_HI_RATIO = 1.18
_SEGMENT_MAX_LENGTH_ATTEMPTS = 4  # 与 story_planner_v6.SEGMENT_LENGTH_MAX_ATTEMPTS 对齐说明用


def _human_step_cn(step: str) -> str:
    if step.startswith("segment_writer_"):
        m = re.match(r"segment_writer_(\d+)_(.+)", step)
        if m:
            return f"第{m.group(1)}幕旁白写手（幕名：{m.group(2)}）"
        return "分段旁白写手"
    if step == "handoff_next_segment":
        return "统筹：为下一幕生成续写指令"
    if step == "narration_tail_patch":
        return "旁白尾部扩写（补字数）"
    if step == "narration_close_patch":
        return "旁白收尾扩写（句末标点）"
    if step == "polish_user_script_synopsis":
        return "投喂素材·剧本医生结构化润色"
    if step == "expand_narration_one_shot_acts":
        return "旁白：一次性按分幕梗概扩写全文"
    if step == "expand_narration_one_shot_compress":
        return "旁白：超长压缩到字数上限内"


def _enrich_audit_record(
    phase: str,
    step: str,
    kind: str,
    ok: bool,
    duration_ms: float,
    attempt: int,
    model: str | None,
    error: str | None,
    extra: dict[str, Any] | None,
) -> dict[str, Any]:
    """在保留机器可读字段的同时，增加中文说明与字数体检。"""
    extra = dict(extra) if extra else {}
    rec: dict[str, Any] = {
        "时间_UTC": datetime.now(timezone.utc).isoformat(),
        "阶段目录": phase,
        "阶段说明": _PHASE_NAME_CN.get(phase, phase),
        "步骤标识": step,
        "步骤说明": _human_step_cn(step),
        "调用类型": "LLM对话" if kind == "llm_chat" else kind,
        "是否成功": ok,
        "耗时_秒": round(duration_ms / 1000.0, 2),
        "本步骤内第几次请求": attempt,
    }
    if model:
        rec["模型"] = model
    if error:
        rec["错误摘要"] = error[:800]
    if extra:
        rec["附加指标"] = extra

    # 分段写手：解释为何同一幕会记多条
    if "segment_writer" in step and "seg_target" in extra and "out_chars" in extra:
        st = int(extra["seg_target"])
        oc = int(extra["out_chars"])
        lo = int(st * _SEGMENT_LO_RATIO)
        hi = int(st * _SEGMENT_HI_RATIO)
        in_band = lo <= oc <= hi
        fr = extra.get("finish_reason")
        rec["字数体检"] = {
            "本段目标约_字": st,
            "理想产出区间_字": [lo, hi],
            "本次产出_字": oc,
            "是否落在理想区间": in_band,
            "API结束原因_finish_reason": fr,
        }
        rec["说明_为何可能多条"] = (
            "同一幕名出现多条记录，表示模型按「理想字数区间」多次重试（重试时会附带字数修正指令）；"
            f"最多 **{_SEGMENT_MAX_LENGTH_ATTEMPTS}** 次仍不理想时，采纳**最接近本段目标字数**的一稿，再进入下一幕。"
            "不是整段流水线重复执行。"
        )

    # 统筹 handoff
    if step == "handoff_next_segment" and extra:
        rec["说明"] = (
            f"根据已写旁白与梗概，为第 {extra.get('next_mo')} / 共 {extra.get('total_mo')} 幕生成短指令，供下一幕写手衔接。"
        )

    # 兼容：保留英文键供脚本 grep
    rec["_compat"] = {
        "phase": phase,
        "step": step,
        "kind": kind,
        "ok": ok,
        "duration_ms": round(duration_ms, 2),
        "attempt": attempt,
        "model": model,
        "error": error,
        "extra": extra if extra else None,
    }
    return rec


_RECORD_SEPARATOR = "\n# " + "=" * 72 + " #\n\n"

# 与约定一致的中文阶段目录名（审计目录名 = 常量值）
# 飞书侧闲聊/指令解析（非成片必经环节，单独归类便于区分配额）
PHASE_FEISHU_BOT = "000-飞书助手"

PHASE_SYNOPSIS = "001-梗概"
# 旁白扩写全链路：分段写手、统筹 handoff、字数/收尾尾部扩写 → 均写入 后台/002-旁白/calls.jsonl
PHASE_NARRATION = "002-旁白"
PHASE_CASTING = "003-定妆"
PHASE_AUDIO_BEATS = "004-音频与节拍"
PHASE_STORYBOARD = "005-分镜与画面"
PHASE_GRID = "006-宫格生图"
PHASE_ASSEMBLE = "007-组装成片"

_PHASE_NAME_CN: dict[str, str] = {
    PHASE_FEISHU_BOT: "飞书助手对话",
    PHASE_SYNOPSIS: "梗概生成与润色",
    PHASE_NARRATION: "旁白扩写（分段写手等）",
    PHASE_CASTING: "定妆与角色参考",
    PHASE_AUDIO_BEATS: "音频与节拍",
    PHASE_STORYBOARD: "分镜与画面",
    PHASE_GRID: "宫格生图",
    PHASE_ASSEMBLE: "组装成片",
}


def _resolve_calls_path(phase: str) -> Path | None:
    try:
        from src.run_context import get_paths

        paths = get_paths(create_if_missing=False)
        run_dir = paths.get("run_dir") if paths else None
        if run_dir and run_dir.exists():
            p = run_dir / "后台" / phase / "calls.jsonl"
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
    except Exception:
        pass
    try:
        fb = BASE_DIR / "feishu" / "后台" / phase / "calls.jsonl"
        fb.parent.mkdir(parents=True, exist_ok=True)
        return fb
    except Exception:
        return None


def _resolve_summary_path(phase: str) -> Path | None:
    calls = _resolve_calls_path(phase)
    if calls is None:
        return None
    return calls.with_name("summary.md")


def _append_phase_summary(
    phase: str,
    step: str,
    ok: bool,
    duration_ms: float,
    attempt: int,
    error: str | None,
    extra: dict[str, Any] | None,
) -> None:
    """写一行人类可读摘要，便于快速浏览 005/006 等阶段。"""
    sp = _resolve_summary_path(phase)
    if sp is None:
        return
    extra = extra or {}
    try:
        if not sp.exists():
            head = (
                f"# {phase} 阶段摘要\n\n"
                "| 时间(UTC) | 步骤 | 成功 | 尝试 | 耗时(秒) | 关键信息 |\n"
                "|---|---|---:|---:|---:|---|\n"
            )
            sp.write_text(head, encoding="utf-8")
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        mark = "✅" if ok else "❌"
        info_parts: list[str] = []
        if "seg_target" in extra and "out_chars" in extra:
            info_parts.append(f"字数 {extra.get('out_chars')}/{extra.get('seg_target')}")
        if "finish_reason" in extra:
            info_parts.append(f"finish={extra.get('finish_reason')}")
        if error:
            info_parts.append(str(error)[:120].replace("\n", " "))
        info = "；".join(info_parts) if info_parts else "-"
        line = f"| {ts} | `{step}` | {mark} | {attempt} | {duration_ms/1000.0:.2f} | {info} |\n"
        with open(sp, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def log_event(
    phase: str,
    step: str,
    kind: str,
    *,
    ok: bool,
    duration_ms: float,
    model: str | None = None,
    attempt: int = 1,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """追加一条审计记录到 calls.jsonl（缩进 JSON + 中文说明 + 块分隔符）。"""
    path = _resolve_calls_path(phase)
    if path is None:
        return
    rec = _enrich_audit_record(
        phase, step, kind, ok, duration_ms, attempt, model, error, extra
    )
    block = json.dumps(rec, ensure_ascii=False, indent=2) + "\n"
    try:
        with _LOCK:
            with open(path, "a", encoding="utf-8") as f:
                if path.exists() and path.stat().st_size > 0:
                    f.write(_RECORD_SEPARATOR)
                f.write(block)
            _append_phase_summary(phase, step, ok, duration_ms, attempt, error, extra)
    except Exception:
        pass


def log_llm_chat(
    phase: str,
    step: str,
    model: str,
    func,
    *,
    attempt: int = 1,
    extra: dict[str, Any] | None = None,
):
    """执行一次 LLM 调用并记录耗时与成败。"""
    t0 = time.perf_counter()
    try:
        out = func()
        ms = (time.perf_counter() - t0) * 1000
        log_event(
            phase,
            step,
            "llm_chat",
            ok=True,
            duration_ms=ms,
            model=model,
            attempt=attempt,
            extra=extra,
        )
        return out
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        log_event(
            phase,
            step,
            "llm_chat",
            ok=False,
            duration_ms=ms,
            model=model,
            attempt=attempt,
            error=str(e),
            extra=extra,
        )
        raise
