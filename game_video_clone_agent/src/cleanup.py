"""
🧹 全自动三通清理工具 (src/cleanup.py)
=====================================
职能：清理生产过程中产生的中间碎片和临时缓存。
范围：tmp/, storyboards/candidates/, __pycache__
"""

import shutil
import os
import sys
from pathlib import Path

# 锁定项目根目录，避免开机自启/非项目 cwd 下路径漂移
BASE_DIR = Path(__file__).resolve().parent.parent

# ── Windows GBK 终端编码修复 ──────────────────────────────────────
if hasattr(sys.stdout, "buffer"):
    from io import TextIOWrapper
    sys.stdout = TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# --- 🎯 需要清理的目录清单 ---
TARGET_DIRS = [
    BASE_DIR / "tmp",
    BASE_DIR / "data" / "storyboards" / "candidates",
    BASE_DIR / "data" / "rw_horizontal",  # 之前生成的横屏参考副本也清理掉
]

def clean_pycache(root_dir: Path):
    """递归清理 __pycache__ 文件夹"""
    count = 0
    for p in list(root_dir.rglob("__pycache__")):
        try:
            shutil.rmtree(p)
            count += 1
        except Exception:
            pass
    return count

def main():
    print("\n[🧹 清洁工] 正在进行全项目深度除尘...")
    total_files_removed = 0
    
    # 1. 清理指定资产目录
    for d in TARGET_DIRS:
        if d.exists():
            print(f"  └─ 🚀 正在清空目录: {d.name}/")
            for f in d.iterdir():
                try:
                    if f.is_file():
                        f.unlink()
                        total_files_removed += 1
                    elif f.is_dir():
                        shutil.rmtree(f)
                        total_files_removed += 1
                except Exception as e:
                    print(f"     [WARN] 无法删除 {f.name}: {e}")

    # 2. 清理 __pycache__
    pycache_count = clean_pycache(BASE_DIR)
    print(f"  └─ ⚙️  清理了 {pycache_count} 个 Python 编译缓存目录 (__pycache__)。")
    
    # 3. 清理旧日志 (保留 markdown 账单，只清理 JSON 原始长日志)
    billing_dir = BASE_DIR / "data" / "billing"
    if billing_dir.exists():
        print(f"  └─ 📜 正在清理历史 JSON 原始日志...")
        for f in billing_dir.glob("log_*.json"):
            try:
                f.unlink()
                total_files_removed += 1
            except Exception:
                pass

    print("=" * 60)
    print(f"[OK] 大扫除完毕！总计清理了 {total_files_removed} 个中间状态文件。")
    print("[OK] 项目熵值已恢复至健康水平。")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
