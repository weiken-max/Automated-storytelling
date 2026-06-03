# -*- coding: utf-8 -*-
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
filepath = os.path.join(BASE_DIR, "start_app.py")

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 定位要替换的代码区域
start_marker = "def _generate_cast_prompts_via_llm("
end_marker = "class DesktopApiBridge:"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print(f"Error: Markers not found. start_idx={start_idx}, end_idx={end_idx}")
    exit(1)

# 构建全新、优雅的动态定妆提示词大模型构思函数
new_func = """def _generate_cast_prompts_via_llm(topic: str, synopsis_text: str, entities: list, custom_template: str = ""):
    \"\"\"根据故事简介与提取出的资产词，并参考定制风格模板，调用大模型动态构思符合该故事背景的定妆照提示词\"\"\"
    mode_path = GLOBAL_STATE.get("mode_path", "RED")
    print(f"[Bridge] 正在调用大模型为频道 {mode_path} 动态设计符合故事背景的视觉描述...")
    client = planner.get_client()
    
    # 动态获取当前频道资产配置
    assets_config = _get_channel_assets_config(mode_path)
    N = len(assets_config)
    
    labels = [ast["label"] for ast in assets_config]
    types = [ast["type"] for ast in assets_config]
    
    # 保证 entities 长度对齐
    ents = list(entities)
    while len(ents) < N:
        ents.append(labels[len(ents)])
        
    # 1. 默认模板备用
    default_templates = {
        "character": "Cyanide-and-Happiness web-comic character sheet: 2D vector, oversized round bean head, two dot eyes, arms and legs as pure black stick strokes (matchstick limbs, no realistic anatomy), simple torso block, bold outlines, flat fills, no shading or fabric micro-detail.",
        "scene": "A flat 2D vector style minimalist cartoon background scenery. Flat shades, no character.",
        "prop": "A flat 2D vector icon cartoon object. Primitive shape, flat color fill, white background."
    }
    
    # 2. 从 custom_template 解析用户预设
    baseline_prompts = []
    for lbl, typ in zip(labels, types):
        tpl = default_templates.get(typ, default_templates["character"])
        if custom_template.strip():
            import re
            match_lbl = re.search(rf"\\\\[{re.escape(lbl)}\\\\](.*?)(\\\\[|$)", custom_template, re.DOTALL | re.IGNORECASE)
            if match_lbl:
                tpl = match_lbl.group(1).strip()
            else:
                match_typ = re.search(rf"\\\\[{re.escape(typ)}\\\\](.*?)(\\\\[|$)", custom_template, re.DOTALL | re.IGNORECASE)
                if match_typ:
                    tpl = match_typ.group(1).strip()
        baseline_prompts.append(tpl)
        
    # 3. 构造大模型 Prompt
    sys_prompt = f\"\"\"You are a master concept designer and visual storyteller for a vector comic pipeline.
Your job is to write detailed narrative-driven visual prompt descriptions for {N} elements based on the topic "{topic}" and the story:
\"\"\"
    for idx, (lbl, typ, ent) in enumerate(zip(labels, types, ents)):
        sys_prompt += f"{idx + 1}. Element [{lbl}]: representing \\"{ent}\\" (Type: {typ})\\n"
        
    import json
    sys_prompt += f\"\"\"
Output ONLY a raw JSON object where keys are the EXACT labels: {json.dumps(labels, ensure_ascii=False)}.
Each value must be a highly detailed English paragraph (60-90 words, no bullet lists, no markdown) containing rich, story-specific visual details.
You MUST follow the style and structure constraints of these baseline templates, and expand/infuse the {{entity}} descriptions with rich narrative details:
\"\"\"
    for lbl, tpl, ent in zip(labels, baseline_prompts, ents):
        sys_prompt += f"- For element \\"{lbl}\\" (representing \\"{ent}\\"\\): Expand upon the baseline template: \\"{tpl}\\"\\n"
        
    sys_prompt += f\"\"\"
Format:
{{
\"\"\"
    for idx, lbl in enumerate(labels):
        comma = "," if idx < N - 1 else ""
        sys_prompt += f'  "{lbl}": "..."{comma}\\n'
    sys_prompt += "}"
    
    user_content = f"Story Synopsis:\\n{synopsis_text}"
    
    try:
        response = client.chat.completions.create(
            model=config.MODEL_LLM,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.7,
            max_tokens=1500
        )
        content = response.choices[0].message.content.strip()
        if "```" in content:
            content = content.split("```")[1].replace("json", "").strip()
        res = json.loads(content)
        
        cast_prompt_parts = []
        for lbl in labels:
            desc = res.get(lbl, "").strip()
            if not desc:
                for k, v in res.items():
                    if k.lower() == lbl.lower():
                        desc = v.strip()
                        break
            cast_prompt_parts.append(f"[{lbl}]\\\\n{desc}")
            
        cast_prompt = "\\\\n\\\\n".join(cast_prompt_parts)
        print("[Bridge] 动态定妆提示词大模型构思成功！")
        return cast_prompt
    except Exception as e:
        print(f"⚠️ [Bridge] 动态构思定妆提示词失败: {e}，将采用备用默认模板。")
        cast_prompt_parts = []
        for lbl, tpl, ent in zip(labels, baseline_prompts, ents):
            desc = tpl.replace("{entity}", ent).replace("{ent}", ent)
            cast_prompt_parts.append(f"[{lbl}]\\\\n{desc}")
        return "\\\\n\\\\n".join(cast_prompt_parts)


"""

# 执行替换并写回文件
content_patched = content[:start_idx] + new_func + content[end_idx:]

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content_patched)

print("🎉 start_app.py patched successfully and cleanly!")
