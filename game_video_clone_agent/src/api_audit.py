"""
当前 Run 目录下「后台」API 调用审计：按成片阶段分子文件夹，追加 JSON Lines。
路径：data/runs/<run_id>/后台/<阶段>/calls.jsonl；若无激活 Run，则写入 feishu/后台/… 兜底。

阶段常量（与文件夹名一一对应）及典型写入来源（便于检索 calls.jsonl 的 step 字段）：

- 000-飞书助手  PHASE_FEISHU_BOT
  feishu/hub_old 通用对话、message_router 对话
- 001-梗概  PHASE_SYNOPSIS
  story_planner_v6.generate_synopsis 等
- 002-旁白  PHASE_NARRATION
  分段写手 step「segment_writer_*」、handoff_next_segment、尾部扩写 narration_tail_patch
  （story_planner_v6 内上述 LLM 均用本阶段，与「梗概/定妆」分离）
- 003-定妆  PHASE_CASTING
  ref_generator 中 LLM / 生图
- 004-音频与节拍  PHASE_AUDIO_BEATS
  Beat 切分、TTS 等
- 005-分镜与画面  PHASE_STORYBOARD
  auto_stage_map、phase3 等
- 006-宫格生图  PHASE_GRID
  image_engine、Step2 宫格等
- 007-组装成片  PHASE_ASSEMBLE
  step3 中 ffmpeg 等
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()

BASE_DIR = Path(__file__).resolve().parent.parent

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
    """追加一行 JSON 到对应阶段的 calls.jsonl。"""
    path = _resolve_calls_path(phase)
    if path is None:
        return
    rec: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        "step": step,
        "kind": kind,
        "ok": ok,
        "duration_ms": round(duration_ms, 2),
        "attempt": attempt,
    }
    if model:
        rec["model"] = model
    if error:
        rec["error"] = error[:800]
    if extra:
        rec["extra"] = extra
    line = json.dumps(rec, ensure_ascii=False) + "\n"
    try:
        with _LOCK:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
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
