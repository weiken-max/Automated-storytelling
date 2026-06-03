# -*- coding: utf-8 -*-
import subprocess
import sys

# 🎬 调色板电影平台 - 快捷方式创建工具
# 采用 powershell 命令管道参数，彻底避开 os.system 导致的中文乱码 (mojibake) 问题
# 将快捷方式指向“启动调色板.bat”诊断控制台，提供最稳定可靠的启动路径，并方便导演实时查阅 AI 生成日志！

powershell_script = """
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("C:\\Users\\86198\\Desktop\\调色板AI电影平台.lnk")
$Shortcut.TargetPath = "c:\\Users\\86198\\Desktop\\Automated-storytelling-main\\game_video_clone_agent\\启动调色板.bat"
$Shortcut.WorkingDirectory = "c:\\Users\\86198\\Desktop\\Automated-storytelling-main\\game_video_clone_agent"
$Shortcut.IconLocation = "shell32.dll,79"
$Shortcut.Save()
"""

def main():
    try:
        print("[快捷方式] 正在为您创建桌面直连快捷方式...")
        subprocess.run(["powershell", "-Command", powershell_script], check=True)
        print("[快捷方式] 🎉 调色板AI电影平台 桌面快捷方式创建成功！")
    except Exception as e:
        print(f"❌ [快捷方式] 创建失败: {e}")

if __name__ == "__main__":
    main()
