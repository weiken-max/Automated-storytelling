# -*- coding: utf-8 -*-
import json
import time
import subprocess
import os
import urllib.request

print("[TEST] Starting local API Server to perform universal compile tests...")

# 启动 api_server.py 进程 (使用虚拟环境下的解释器)
python_executable = os.path.join("venv", "Scripts", "python.exe")
server_proc = subprocess.Popen(
    [python_executable, "api_server.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

# 等待服务加载 (FastAPI 需要 5 秒启动并完成本地环境绑定)
time.sleep(5)

url = "http://127.0.0.1:8000/api/story/v1/compile"

def send_compile_request(mode, text):
    payload = {
        "app_id": "palette-cinema-id",
        "mode_path": mode,
        "original_text": text,
        "pipeline_config": {
            "polish_flow": {"enabled": False, "system_prompt": "", "immutable_lock": True},
            "voiceover_flow": {"system_prompt": ""},
            "render_flow": {"style_presets": "flat cartoon", "seed": 12345}
        }
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode("utf-8"))
            return data
    except Exception as e:
        print(f"HTTP request failed: {e}")
        return None

try:
    # ── 1. 验证 CH_SCIENCE 模式 (硬核科普频道 - 原厂) ──
    print("\n[TEST 1] Testing CH_SCIENCE mode (Hardcore Science Channel)...")
    text_sci = "生命的奥秘在于DNA的双螺旋结构。当细胞分裂时，DNA双链解开，每个单链作为模板合成新的互补链，实现遗传信息的完美复制。"
    res_sci = send_compile_request("CH_SCIENCE", text_sci)
    
    if res_sci and res_sci.get("status") == "success":
        entities = res_sci["data"]["extracted_entities"]
        print(f"Success! Extracted Entities: {entities}")
        assert len(entities) == 1, f"Expected exactly 1 entity, got {len(entities)}"
        print("[PASSED] Science Channel (CH_SCIENCE) decoupled to exactly 1 entity card!")
    else:
        print("[FAILED] Science Channel test failed or returned error.")
        exit(1)

    # ── 2. 验证 CH_FOOD 模式 (美食解说频道 - 用户新建) ──
    print("\n[TEST 2] Testing CH_FOOD mode (Custom Gourmet Channel)...")
    text_foo = "今天教大家做一道经典的红烧肉。精选上等五花肉，慢火细炖两小时，出锅时肉质红亮诱人，软烂浓郁，令人垂涎欲滴。"
    res_foo = send_compile_request("CH_FOOD", text_foo)
    
    if res_foo and res_foo.get("status") == "success":
        entities = res_foo["data"]["extracted_entities"]
        print(f"Success! Extracted Entities: {entities}")
        assert len(entities) == 1, f"Expected exactly 1 entity, got {len(entities)}"
        print("[PASSED] Custom Gourmet Channel (CH_FOOD) decoupled to exactly 1 entity card!")
    else:
        print("[FAILED] Custom Gourmet Channel test failed or returned error.")
        exit(1)

    # ── 3. 验证 RED 模式 (剧情故事频道) ──
    print("\n[TEST 3] Testing RED mode (Drama Story Channel)...")
    text_dra = "老钟表匠坐在静谧的机械工坊中，他颤抖着双手，缓缓拿出一块闪烁着神秘金光的逆动怀表。这块表有着操控时光的古老魔力。"
    res_dra = send_compile_request("RED", text_dra)
    
    if res_dra and res_dra.get("status") == "success":
        entities = res_dra["data"]["extracted_entities"]
        print(f"Success! Extracted Entities: {entities}")
        assert len(entities) == 3, f"Expected exactly 3 entities, got {len(entities)}"
        print("[PASSED] Drama Channel (RED) decoupled to exactly 3 entity cards!")
    else:
        print("[FAILED] Drama Channel test failed or returned error.")
        exit(1)

    print("\n[SUCCESS] All Universal API Decouple Tests passed perfectly!")

finally:
    # 物理终止后台测试服务器
    print("\nCleaning up test API Server process...")
    server_proc.terminate()
    server_proc.wait()
    print("Exit.")
