# -*- coding: utf-8 -*-
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 1. 修理 start_app.py 里面的局部 json 局部作用域编译问题
start_app_path = os.path.join(BASE_DIR, "start_app.py")
with open(start_app_path, "r", encoding="utf-8") as f:
    content = f.read()

# 移除 _extract_entities_manually 和 _generate_cast_prompts_via_llm 函数里的局部 import json
content_fixed = content.replace("        import json\n        res = json.loads(content)", "        res = json.loads(content)")
content_fixed = content_fixed.replace("    import json\n    sys_prompt += f\"\"\"", "    sys_prompt += f\"\"\"")

with open(start_app_path, "w", encoding="utf-8") as f:
    f.write(content_fixed)
print("✅ Removed local import json from start_app.py successfully!")


# 2. 修理 test_assets_refactor.py 里面调用 DesktopApiBridge 方法的格式
test_file_path = os.path.join(BASE_DIR, "scratch", "test_assets_refactor.py")
with open(test_file_path, "r", encoding="utf-8") as f:
    test_content = f.read()

# 替换 DesktopApiBridge 调用
old_call_4 = """        bridge_obj = MagicMock()
        payload = {
            "entities": ["老钟表匠", "反派赛博霸主", "废土飞升车间", "纳米源表芯片"],
            "global_style_prompt": "vector art",
            "seed": 4098
        }
        
        # 调用 generate_assets
        res = app.start_app.generate_assets(bridge_obj, payload)"""

new_call_4 = """        bridge_obj = app.DesktopApiBridge()
        payload = {
            "entities": ["老钟表匠", "反派赛博霸主", "废土飞升车间", "纳米源表芯片"],
            "global_style_prompt": "vector art",
            "seed": 4098
        }
        
        # 调用 generate_assets
        res = bridge_obj.generate_assets(payload)"""

test_content_fixed = test_content.replace(old_call_4, new_call_4)

old_call_5_1 = """            # 我们只是测试类型路由到 character 时执行 generate_ref_sheet_at，不需要真实执行
            try:
                app.start_app.render_single_frame(bridge_obj, payload)
            except Exception:
                pass"""

new_call_5_1 = """            bridge_obj = app.DesktopApiBridge()
            try:
                bridge_obj.render_single_frame(payload)
            except Exception:
                pass"""

test_content_fixed = test_content_fixed.replace(old_call_5_1, new_call_5_1)

old_call_5_2 = """            payload = {
                "target_id": "cast_03",
                "prompt": "new scene prompt",
                "seed": 4098
            }
            
            try:
                app.start_app.render_single_frame(bridge_obj, payload)
            except Exception:
                pass"""

new_call_5_2 = """            bridge_obj = app.DesktopApiBridge()
            payload = {
                "target_id": "cast_03",
                "prompt": "new scene prompt",
                "seed": 4098
            }
            
            try:
                bridge_obj.render_single_frame(payload)
            except Exception:
                pass"""

test_content_fixed = test_content_fixed.replace(old_call_5_2, new_call_5_2)

with open(test_file_path, "w", encoding="utf-8") as f:
    f.write(test_content_fixed)
print("✅ Fixed method calls in test_assets_refactor.py successfully!")
