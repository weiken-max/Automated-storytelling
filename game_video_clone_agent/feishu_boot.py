# -*- coding: utf-8 -*-
import os
import sys
import subprocess

# 获取游戏宣传自动剪辑目录的绝对路径，这可以彻底解决中文路径被吃掉的问题
script_dir = os.path.dirname(os.path.abspath(__file__))
venv_python = os.path.join(script_dir, "venv", "Scripts", "python.exe")
watchdog_py = os.path.join(script_dir, "feishu", "watchdog.py")

# 如果虚拟环境存在，使用虚拟环境，否则使用公共系统环境
python_executable = venv_python if os.path.exists(venv_python) else sys.executable

# 启动看门狗（使用 CREATE_NO_WINDOW 避免黑框出现）
subprocess.Popen(
    [python_executable, watchdog_py],
    cwd=script_dir,
    creationflags=0x08000000  # 隐藏控制台窗口
)
