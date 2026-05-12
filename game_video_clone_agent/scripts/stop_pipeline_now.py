#!/usr/bin/env python3
"""紧急停止当前/指定 Run 的流水线子进程（与 hub_old.kill_pipeline_processes 策略一致）。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REGISTRY = BASE_DIR / "feishu" / "run_pid_registry.json"
CURRENT = BASE_DIR / "data" / "runs" / "current_run.json"

# 与 feishu/hub_old.py kill_pipeline_processes 一致：子进程多为 *_v6.py / story_planner
KEYWORDS = ("_v6.py", "story_planner")


def _kill_registry(run_id: str) -> int:
    import psutil

    killed = 0
    if not run_id or not REGISTRY.exists():
        return 0
    try:
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except Exception:
        return 0
    rec = reg.pop(run_id, None)
    if rec is None:
        return 0
    try:
        REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    for pid in rec.get("pids", []):
        try:
            p = psutil.Process(int(pid))
            if p.is_running():
                p.kill()
                killed += 1
                print(f"已终止（注册表）PID {pid}")
        except Exception:
            pass
    return killed


def _kill_by_keywords() -> int:
    import psutil

    killed = 0
    me = os.getpid()
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            if proc.pid == me:
                continue
            cmd = " ".join(proc.info.get("cmdline") or [])
            if any(k in cmd for k in KEYWORDS):
                proc.kill()
                killed += 1
                print(f"已终止（关键字）PID {proc.pid}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return killed


def main() -> None:
    run_id = sys.argv[1] if len(sys.argv) > 1 else ""
    if not run_id and CURRENT.exists():
        try:
            run_id = json.loads(CURRENT.read_text(encoding="utf-8")).get("run_id") or ""
        except Exception:
            run_id = ""
    k1 = _kill_registry(run_id) if run_id else 0
    k2 = _kill_by_keywords()
    print(f"完成：注册表 {k1} 个，关键字匹配 {k2} 个（run_id={run_id!r}）")


if __name__ == "__main__":
    main()
