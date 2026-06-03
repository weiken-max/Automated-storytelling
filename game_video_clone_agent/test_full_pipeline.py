# -*- coding: utf-8 -*-
"""
E2E Palette Cinema - End-to-End API Pipeline Test Script
======================================================
This script sequentially triggers the five stages of the FastAPI middleware server,
simulating a real user run through the frontend to verify the entire pipeline works perfectly.
"""

import json
import urllib.request
import urllib.error
import time
import sys

API_BASE = "http://127.0.0.1:8000"

def make_post_request(endpoint, payload):
    url = f"{API_BASE}{endpoint}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"}
    )
    try:
        with urllib.request.urlopen(req) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"[HTTP Error] endpoint={endpoint} code={e.code} reason={e.reason}")
        print(e.read().decode("utf-8", errors="ignore"))
        raise
    except Exception as e:
        print(f"[Connection Error] endpoint={endpoint} error={e}")
        raise

def main():
    print("=============================================================")
    print("STARTING END-TO-END PALETTE CINEMA API PIPELINE TEST")
    print("=============================================================")

    # STAGE 1: Compile Story
    print("\n[STAGE 1] Triggering Script Compilation...")
    compile_payload = {
        "app_id": "palette-cinema-id",
        "mode_path": "RED",
        "original_text": "在霓虹交织的未来都市，你是一个落魄却天赋异禀的赛博黑客。为了给生病的妹妹买药，你冒险接下了一个九死一生的委托，去潜入科技巨头的总部大楼，窃取机密的意识芯片。夜幕降临，你避开巡逻无人机成功得手，却在撤离时警报大作，无数机甲卫兵将你重重包围。最终你引爆了自制电磁脉冲，在废土黑市商人的协助下杀出重围，成功拯救了妹妹，也开启了反抗巨头的传奇序幕。",
        "pipeline_config": {
            "polish_flow": {
                "enabled": True,
                "system_prompt": "你是一位专业的资深编剧与剧本医生。\n任务：请阅读用户提供的原始素材（梗概、片段或小说节选均可），在【完全保留用户原始创意、情节走向和核心设定】的前提下，进行专业润色，并补充与盲盒梗概同规格的结构化字段。\n\n润色要求：\n1. 语言风格：使文字更具画面感（Visual Thinking），多用具象动词，少用空泛形容词；**禁止**强行套用「阶层跃迁」「利益算计」等固定套路，除非用户原文已包含类似内核。\n2. 节奏与体量：优化起承转合与悬念，整体梗概总长度须符合后续约 1700 字旁白体量的信息密度，且 synopsis 与 synopsis_acts 拼接总字符数不得超过 1500（汉字+标点）。\n3. 分幕结构：必须输出 synopsis_acts 数组，长度恰好为 6；每幕为连续叙事，幕内不要写「第X幕」小标题，按时间顺序串成一条故事线。\n4. **行业潜规则 industry_rules**：与盲盒大纲一致，输出 1～4 条数组，概括本作可被影像化的矛盾机制或环境张力（非教条）。\n\n输出：**仅** JSON（键名固定）：\n{\n  \"synopsis_acts\": [共6个字符串，依次为第1幕…第6幕],\n  \"synopsis\": \"将 synopsis_acts 用两个换行符拼接的全文，与各幕一致\",\n  \"short_title\": \"12字以内的短片标题，用于飞书卡片抬头\",\n  \"era\": \"时代背景\",\n  \"identity\": \"主角身份或称谓\",\n  \"industry_rules\": [\"……\"]\n}"
            },
            "voiceover_flow": {
                "system_prompt": "你是一个极其冷峻、犀利的短视频旁白文案大师。\n任务：按用户指示写出**一段**沉浸式旁白（不是全文，只是连续叙事中的一段）。\n\n【写作铁律】\n1. **一镜到底**：禁止使用段落小标题（如 Level、第一阶段）。用时间流逝、场景升级、数字与利益推进。\n2. **第二人称**：全程使用「你」，极简冷峻，少用形容词。\n3. **纯净文本**：禁止 <subshot>、禁止 [CUT]、禁止任何分镜标签。\n4. **本段体量**：本段目标约 {seg_target} 字（允许 ±10%）。\n\n输出要求：**只输出旁白正文**，不要标题、不要 JSON、不要代码围栏、不要解释。"
            },
            "render_flow": {
                "style_presets": "High-quality 2D vector cartoon, bold black outlines, vibrant flat colors with soft cel-shading. Style inspired by Cyanide and Happiness but with professional lighting and detailed illustrated backgrounds. Character proportions: stick figure limbs, round bean heads.",
                "seed": 12345
            }
        }
    }

    t0 = time.time()
    compile_res = make_post_request("/api/story/v1/compile", compile_payload)
    print(f"[OK] STAGE 1 Complete! (Duration: {time.time() - t0:.2f}s)")
    
    compiled_voiceover = compile_res["data"]["compiled_voiceover"]
    extracted_entities = compile_res["data"]["extracted_entities"]
    print(f"Entities: {extracted_entities}")
    print(f"Compiled Voiceover: {compiled_voiceover[:120]}...")
    
    # STAGE 2: Generate Visual Assets (Cast Sheet)
    print("\n[STAGE 2] Generating Cast Sheet Visual Assets...")
    asset_payload = {
        "entities": extracted_entities,
        "global_style_prompt": "High-quality 2D vector cartoon, bold black outlines, vibrant flat colors with soft cel-shading. Style inspired by Cyanide and Happiness but with professional lighting and detailed illustrated backgrounds. Character proportions: stick figure limbs, round bean heads.",
        "seed": 12345
    }
    
    t0 = time.time()
    asset_res = make_post_request("/api/assets/v1/generate", asset_payload)
    print(f"[OK] STAGE 2 Complete! (Duration: {time.time() - t0:.2f}s)")
    for ass in asset_res.get("assets", []):
        print(f"Asset ID: {ass['id']}, Name: {ass['name']}, URL: {ass['image_url']}")

    # STAGE 3: Generate Storyboard & Visual Prompts
    print("\n[STAGE 3] Generating Storyboard and Time Cues (Calling Step 1 & 2)...")
    t0 = time.time()
    storyboard_res = make_post_request("/api/story/v1/generate-storyboard", {})
    print(f"[OK] STAGE 3 Complete! (Duration: {time.time() - t0:.2f}s)")
    print(f"Generated {len(storyboard_res.get('frames', []))} storyboard frames.")
    
    # STAGE 4: Synthesize Final Video
    print("\n[STAGE 4] Synthesizing Final Video (Calling FFmpeg Assembler)...")
    t0 = time.time()
    synthesis_res = make_post_request("/api/story/v1/synthesize", {})
    print(f"[OK] STAGE 4 Complete! (Duration: {time.time() - t0:.2f}s)")
    
    print("\n=============================================================")
    print("PALETTE CINEMA PIPELINE TEST SUCCESSFUL!")
    print(f"Video URL: {synthesis_res['video_url']}")
    print("=============================================================")

if __name__ == "__main__":
    main()
