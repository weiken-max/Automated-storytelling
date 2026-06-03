# -*- coding: utf-8 -*-
"""
🎬 “调色板” AI 电影级独立桌面 APP - 窗口管理器 (start_app.py)
======================================================
- 使用 pywebview 轻量桌面渲染引擎拉起独立桌面窗口。
- 初始尺寸 1360x850，居中，支持右上角控制，支持边缘拖拽缩放。
- 后台以子进程形式拉起本地 API 中控服务 (api_server.py)。
- 通过 JS Bridge 绑定 Windows 原生“另存为”保存对话框。
- 窗口关闭时自动物理清理所有后台 Python 临时进程。
"""

import os
import sys

# ── 🌐 强制指定全局终端流为 UTF-8 编码，彻底扫清 Windows 平台下任何子进程的 Emoji/中文字符 GBK 编码报错 ──
os.environ["PYTHONIOENCODING"] = "utf-8"

# ── 🔑 加载本地中转站 .env 环境变量 ──
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import time
import subprocess
import socket

# ── 💡 极高容错：在 Python 内部自动智能诊断并补齐缺失的轻量级桌面依赖库 ──
try:
    import webview
    import fastapi
    import uvicorn
except ImportError:
    print("[系统] 检测到桌面运行依赖项不全，正在为您自动联网下载补齐...")
    python_exe = sys.executable
    if not python_exe:
        python_exe = "python"
    # 调用当前 python 环境的 pip 静默下载
    subprocess.run(
        [python_exe, "-m", "pip", "install", "pywebview", "fastapi", "uvicorn", "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    # 补齐后重新导入
    import webview
    import fastapi
    import uvicorn

# ── 确保能找到同级和上级目录 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)


def is_port_open(port=8000, host="127.0.0.1"):
    """检测本地端口是否已被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False  # 端口未被占用（说明服务还没开）
        except socket.error:
            return True  # 端口已被占用（说明服务已经开了，或者被抢占了）


# 全局窗口引用，避免挂在 bridge 实例属性上导致递归序列化超限报错
GLOBAL_WINDOW = None

class DesktopApiBridge:
    """
    🌉 前后端交互桥梁 (JS Bridge)
    - 允许前台 JavaScript 能够直接调用 Python 原生底层能力（如弹窗、拷文件）。
    """
    def select_save_path(self, default_filename="my_epic_story.mp4"):
        """
        💾 唤起 Windows 系统原生的“另存为”保存对话框
        """
        global GLOBAL_WINDOW
        if not GLOBAL_WINDOW:
            print("[JS Bridge] 错误：未检测到全局窗口实例！")
            return ""
        
        print("[JS Bridge] 收到前台指令：正在弹起 Windows 保存文件对话框...")
        
        # 弹起系统原生对话框
        file_path = GLOBAL_WINDOW.create_file_dialog(
            webview.SAVE_DIALOG,
            directory='',
            save_filename=default_filename,
            file_types=('MP4 视频文件 (*.mp4)', '所有文件 (*.*)')
        )
        
        print(f"[JS Bridge] 用户选定的保存路径: {file_path}")
        return file_path


def main():
    server_process = None
    api_port = 8000
    
    # 1. 自动判定当前 python 解释器路径
    python_exe = sys.executable
    if not python_exe:
        python_exe = "python"
        
    print(f"[系统] 使用的 Python 解释器: {python_exe}")

    try:
        # 2. 如果 8000 端口未被占用，在后台静默拉起 api_server.py 服务
        if not is_port_open(api_port):
            print("[系统] 正在后台启动本地 API 中控服务 (api_server.py)...")
            # 使用 sys.executable 确保与当前 venv 虚拟环境 100% 保持一致
            server_process = subprocess.Popen(
                [python_exe, os.path.join(BASE_DIR, "api_server.py")],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=BASE_DIR
            )
            
            # 等待 1.5 秒，让后台 API 彻底跑起来
            time.sleep(1.5)
            print("[系统] 本地 API 中控服务启动完成。")
        else:
            print("[系统] 检测到本地 8000 端口已被占用，默认直接复用现有服务。")

        # 3. 准备 JS Bridge 和原生窗口参数
        bridge = DesktopApiBridge()
        
        # 定义窗口渲染的 HTML 网页路径（可以是绝对路径）
        html_path = os.path.join(BASE_DIR, "palette_studio.html")
        print(f"[系统] 正在装载可视化前端文件: {html_path}")

        # 创建精致的 Windows 原生桌面窗口
        window = webview.create_window(
            title="“调色板” AI 电影级多大模型联调总控台",
            url=html_path,
            js_api=bridge,      # 绑定 JS 桥梁
            width=1360,
            height=850,
            resizable=True,     # 允许拉伸
            min_size=(1024, 700) # 限制最小尺寸，防止排版挤压
        )
        
        global GLOBAL_WINDOW
        GLOBAL_WINDOW = window

        # 4. 启动桌面客户端主循环
        print("[系统] 正在为您弹开独立软件窗口...")
        webview.start(debug=True) # 开启 debug=True，允许用户在窗口中右键检查元素调试

    except Exception as e:
        print(f"❌ [系统] 运行发生致命错误: {e}")
        
    finally:
        # 5. 退出 APP 时，安全无残留地清理后台子进程，拒绝占用系统内存
        if server_process:
            print("[系统] 软件正在安全退出，正在为您利索清理后台中控进程...")
            try:
                server_process.kill()
                server_process.wait()
                print("[系统] 后台进程清理干净。再见，导演！")
            except Exception as e:
                print(f"⚠️ 清理进程发生警告: {e}")


if __name__ == "__main__":
    main()
