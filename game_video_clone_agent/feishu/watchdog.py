import subprocess
import time
import sys
import os
import psutil
from pathlib import Path

# 获取当前路径
BASE_DIR = Path(__file__).resolve().parent.parent
HUB_PATH = BASE_DIR / "feishu" / "hub.py"

PID_FILE = BASE_DIR / "feishu" / "hub.pid"

def is_hub_running():
    """检查 hub.pid 对应的进程是否存在且为 python（psutil 版，兼容 Win11 和非中文系统）"""
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        if not pid:
            return False
        proc = psutil.Process(pid)
        # 判断是 python 进程且 hub.py 在命令行中
        cmdline = ' '.join(proc.cmdline()).lower()
        return proc.is_running() and ("python" in cmdline or "hub.py" in cmdline)
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError, FileNotFoundError):
        return False

def start_hub():
    """冷启动或重启 hub.py (静默模式, 优先使用 venv)"""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🚨 正在开启隐身守护...")
    try:
        # NEW-BUG-03 修复：psutil 替代 wmic 清理残余进程
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                if "hub.py" in ' '.join(proc.info.get('cmdline') or []):
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        time.sleep(2)
        
        # 🛡️ 智能寻找 Python：优先用虚拟环境里的那个
        python_exe = sys.executable 
        venv_python = BASE_DIR / "venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            python_exe = str(venv_python)
            
        # 🚀 绝招：CREATE_NO_WINDOW 让小黑窗彻底消失
        subprocess.Popen([python_exe, str(HUB_PATH)], creationflags=0x08000000)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ✅ 隐身指挥部已上线（使用：{os.path.basename(python_exe)}）")
    except Exception as e:
        print(f"  -> 重启失败: {e}")

def keep_alive():
    """不眨眼的保安轮询"""
    print("🛡️ 【离线自愈保安】已上线，正在监控指挥部状态...")
    while True:
        if not is_hub_running():
            start_hub()
            # 重启后给老板发个平安信 (可选：通过直接调用 hub 内的接口或等它上线)
        else:
            # print(".", end="", flush=True) # 心跳打印
            pass
        time.sleep(15) # 每 15 秒扫一次，性能消耗极低

if __name__ == "__main__":
    keep_alive()
