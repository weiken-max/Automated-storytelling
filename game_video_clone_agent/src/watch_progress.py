"""
实时进度监控器 - 在独立的终端窗口运行本脚本
每隔1秒自动读取并显示 progress_monitor.txt 中的最新状态
"""
import time
import os
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent

if hasattr(sys.stdout, "buffer"):
    from io import TextIOWrapper
    sys.stdout = TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROGRESS_LOG = BASE_DIR / "data" / "billing" / "progress_monitor.txt"

def clear():
    os.system("cls" if os.name == "nt" else "clear")

print("🔭 进度监控器已启动... (按 Ctrl+C 退出)")
time.sleep(1)

try:
    last_status = "⏳ 等待生产任务启动..."
    while True:
        try:
            if PROGRESS_LOG.exists():
                text = PROGRESS_LOG.read_text(encoding="utf-8").strip()
                if text:
                    last_status = text
            
            os.system("cls" if os.name == "nt" else "clear")
            print("═" * 50)
            print("   🎬 视频生产线 · 实时进度监控器")
            print("═" * 50)
            print(f"   ⏰ 刷新时间: {datetime.now().strftime('%H:%M:%S')}")
            
            # 画进度条
            if "进度:" in last_status:
                try:
                    pct_str = last_status.split("%")[0].split("进度:")[-1].strip()
                    pct = float(pct_str)
                    bar_len = 30
                    filled = int(bar_len * pct / 100)
                    bar = "█" * filled + "░" * (bar_len - filled)
                    print(f"\n   [{bar}] {pct:.1f}%")
                except:
                    pass
            
            print(f"\n   📌 {last_status}")
            print("\n" + "═" * 50)
            print("   提示: 先运行生产脚本再开此监控器")
            print("═" * 50)

        except Exception:
            pass
            
        time.sleep(3) # 降低刷新率，杜绝高频闪烁
        
except KeyboardInterrupt:
    print("\n👋 监控器已退出。")
        
except KeyboardInterrupt:
    print("\n👋 监控器已退出。")