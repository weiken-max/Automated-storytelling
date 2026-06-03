# -*- coding: utf-8 -*-
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
filepath = os.path.join(BASE_DIR, "scratch", "test_assets_refactor.py")

with open(filepath, "r", encoding="utf-8") as f:
    c = f.read()

# 进行简单精准的单句替换，绕过任何缩进和换行符匹配的干扰
c = c.replace("bridge_obj = MagicMock()", "bridge_obj = app.DesktopApiBridge()")
c = c.replace("app.start_app.generate_assets(bridge_obj, payload)", "bridge_obj.generate_assets(payload)")
c = c.replace("app.start_app.render_single_frame(bridge_obj, payload)", "bridge_obj.render_single_frame(payload)")

with open(filepath, "w", encoding="utf-8") as f:
    f.write(c)

print("Test file corrected!")
