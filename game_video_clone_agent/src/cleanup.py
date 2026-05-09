"""
🧹 安全清理工具 (src/cleanup.py)
================================
职能：清理运行中产生的中间碎片、历史 run、旧口径目录内容和飞书临时状态文件。
默认行为：先 dry-run 预览；真正删除需显式指定 --apply。
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

# 锁定项目根目录，避免开机自启/非项目 cwd 下路径漂移
BASE_DIR = Path(__file__).resolve().parent.parent

# ── Windows GBK 终端编码修复 ──────────────────────────────────────
if hasattr(sys.stdout, "buffer"):
    from io import TextIOWrapper
    sys.stdout = TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 旧口径目录：只清空目录内容，保留目录和 .gitkeep，避免兼容逻辑报错
LEGACY_DATA_DIRS = [
    BASE_DIR / "data" / "audio",
    BASE_DIR / "data" / "output",
    BASE_DIR / "data" / "scripts",
    BASE_DIR / "data" / "storyboards",
    BASE_DIR / "data" / "exports",
    BASE_DIR / "data" / "cache",
    BASE_DIR / "data" / "temp",
]

# 明确可清理的临时目录
TRANSIENT_DIRS = [
    BASE_DIR / "tmp",
    BASE_DIR / "data" / "storyboards" / "candidates",
    BASE_DIR / "data" / "rw_horizontal",
]

RUNS_ROOT = BASE_DIR / "data" / "runs"
CURRENT_RUN_FILE = RUNS_ROOT / "current_run.json"
FEISHU_DIR = BASE_DIR / "feishu"

# 飞书运行时临时文件（可安全清理）
FEISHU_EXACT_FILES = [
    "hub.pid",
    "run_pid_registry.json",
    "last_error_context.json",
    "temp_synopsis.json",
    "synopsis_duration_draft.json",
    "visual_card_mid.txt",
    "synopsis_card_mid.txt",
]

def clean_pycache(root_dir: Path, apply: bool) -> int:
    """递归清理 __pycache__ 文件夹"""
    count = 0
    for p in list(root_dir.rglob("__pycache__")):
        try:
            if apply:
                shutil.rmtree(p)
            count += 1
        except Exception:
            pass
    return count

def _is_keep_file(path: Path) -> bool:
    return path.name == ".gitkeep"


def _remove_path(path: Path, apply: bool) -> bool:
    try:
        if apply:
            if path.is_file() or path.is_symlink():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
        return True
    except Exception:
        return False


def _clear_dir_contents(target_dir: Path, apply: bool) -> int:
    removed = 0
    if not target_dir.exists():
        return removed
    for p in target_dir.iterdir():
        if _is_keep_file(p):
            continue
        if _remove_path(p, apply):
            removed += 1
    return removed


def _load_current_run_id() -> str | None:
    if not CURRENT_RUN_FILE.exists():
        return None
    try:
        data = json.loads(CURRENT_RUN_FILE.read_text(encoding="utf-8"))
        run_id = data.get("run_id")
        return str(run_id).strip() if run_id else None
    except Exception:
        return None


def _collect_run_dirs() -> list[Path]:
    if not RUNS_ROOT.exists():
        return []
    run_dirs: list[Path] = []
    for p in RUNS_ROOT.iterdir():
        if p.is_dir() and p.name.startswith("Run_"):
            run_dirs.append(p)
    # Run_YYYYMMDD_HHMMSS_xxx，按名字倒序可近似按时间新->旧
    run_dirs.sort(key=lambda x: x.name, reverse=True)
    return run_dirs


def _clean_old_runs(keep_recent: int, apply: bool) -> tuple[int, int]:
    run_dirs = _collect_run_dirs()
    if not run_dirs:
        return 0, 0

    current_run_id = _load_current_run_id()
    keep_set = set()
    if keep_recent > 0:
        for p in run_dirs[:keep_recent]:
            keep_set.add(p.name)
    if current_run_id:
        keep_set.add(current_run_id)

    removed_runs = 0
    skipped_runs = 0
    for p in run_dirs:
        if p.name in keep_set:
            skipped_runs += 1
            continue
        if _remove_path(p, apply):
            removed_runs += 1
    return removed_runs, skipped_runs


def _clean_feishu_runtime_files(apply: bool) -> int:
    if not FEISHU_DIR.exists():
        return 0
    removed = 0
    for name in FEISHU_EXACT_FILES:
        p = FEISHU_DIR / name
        if p.exists() and _remove_path(p, apply):
            removed += 1

    for p in FEISHU_DIR.glob("temp_*.json"):
        if p.exists() and _remove_path(p, apply):
            removed += 1
    return removed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="安全清理工具：默认 dry-run；加 --apply 才会真实删除。"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="执行真实删除（默认仅预览）。",
    )
    parser.add_argument(
        "--keep-runs",
        type=int,
        default=2,
        help="保留最近 N 个 Run_* 目录（默认 2）。",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    apply = args.apply
    keep_runs = max(0, int(args.keep_runs))
    mode = "APPLY" if apply else "DRY-RUN"

    print(f"\n[🧹 清理器] 模式: {mode}")
    print(f"[🧹 清理器] 保留最近 runs 数量: {keep_runs}")
    print("[🧹 清理器] 开始执行目录瘦身...")

    total_removed = 0

    # 1) 清理明确临时目录
    for d in TRANSIENT_DIRS:
        removed = _clear_dir_contents(d, apply)
        if d.exists():
            print(f"  └─ 清理临时目录 {d.relative_to(BASE_DIR)} : {removed} 项")
        total_removed += removed

    # 2) 清空旧口径目录内容（保留目录和 .gitkeep）
    for d in LEGACY_DATA_DIRS:
        removed = _clear_dir_contents(d, apply)
        if d.exists():
            print(f"  └─ 清理旧口径目录 {d.relative_to(BASE_DIR)} : {removed} 项")
        total_removed += removed

    # 3) 清理历史 runs（保留当前 run + 最近 N 个）
    removed_runs, skipped_runs = _clean_old_runs(keep_runs, apply)
    print(f"  └─ 清理历史 runs: 删除 {removed_runs} 个，保留 {skipped_runs} 个")
    total_removed += removed_runs

    # 4) 清理飞书运行时临时文件
    feishu_removed = _clean_feishu_runtime_files(apply)
    print(f"  └─ 清理 feishu 临时文件: {feishu_removed} 项")
    total_removed += feishu_removed

    # 5) 清理 __pycache__
    pycache_count = clean_pycache(BASE_DIR, apply)
    print(f"  └─ 清理 Python 编译缓存目录 (__pycache__): {pycache_count} 个")
    total_removed += pycache_count

    # 6) 清理旧账单 JSON 原始日志
    billing_removed = 0
    billing_dir = BASE_DIR / "data" / "billing"
    if billing_dir.exists():
        for f in billing_dir.glob("log_*.json"):
            if _remove_path(f, apply):
                billing_removed += 1
        print(f"  └─ 清理 billing 原始 JSON 日志: {billing_removed} 项")
    total_removed += billing_removed

    print("=" * 60)
    print(f"[OK] 清理完成（{mode}）。预计处理 {total_removed} 项。")
    if not apply:
        print("[TIP] 当前为预览模式；确认无误后可加 --apply 执行真实删除。")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
