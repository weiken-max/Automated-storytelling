"""
🎭 角色定妆器 (src/ref_generator.py) — v3.0 生产线直供版
==========================================================
流程：构思 → 生成三视图 → 直接存入 data/refs/ → 用户审核
支持按角色类别（主角/配角/其他）独立生成或更新。
"""

import json
import os
import sys
from pathlib import Path
import shutil
import asyncio
from PIL import Image
from openai import OpenAI

# ── Windows GBK 终端编码修复 ──
if hasattr(sys.stdout, "buffer"):
    from io import TextIOWrapper
    sys.stdout = TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 确保能找到 src 目录下的配置 ──
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(BASE_DIR / "src") not in sys.path:
    sys.path.insert(0, str(BASE_DIR / "src"))

import src.style_config as config
from src.model_presets import ACTIVE_IMG_VENDOR
from src.image_engine import generate_image
from src.project_vault import backup as vault_backup  # 🔒 导入金库备份接口

# ================================================================
#  🧠 智能构思 (LLM)
# ================================================================

def design_character(topic: str, role_tag: str):
    """使用 LLM 为给定角色设计具体的视觉特征"""
    print(f"  🧠 [Design] 正在为主题【{topic}】构思角色: {role_tag}...")

    # 修复 URL 拼接逻辑：如果 base_url 已包含 v1，不再叠加
    final_url = config.LLM_BASE_URL.rstrip("/")
    client = OpenAI(api_key=config.LLM_API_KEY, base_url=final_url)

    system_prompt = f"""你是一个顶级的角色设计专家。
你的任务是根据一个视频主题，为一个关键角色构思具体的、易于辨识的视觉特征。

画画风约束（不可违反）：
{config.STYLE_ANCHOR}

输出要求：
1. [english_prompt]：用于生成三视图的英文提示词。必须包含具体的服装和配饰。
2. [anchor_description]：简洁的英文角色描述，用于后续在分镜中引用该角色。
3. 严禁写实细节（头发、肌肉、皮肤纹理等）。

格式（仅输出 JSON）:
{{
  "english_prompt": "...",
  "anchor_description": "..."
}}"""

    user_prompt = f"请为当前主题【{topic}】设计角色类型为 {role_tag} 的【人物】形象。"

    response = client.chat.completions.create(
        model=config.MODEL_LLM,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        temperature=0.7
    )

    try:
        # [SUPER DEFENSE] 兼容各种奇怪的 SDK 返回类型
        content = ""
        if hasattr(response, 'choices') and response.choices:
            content = response.choices[0].message.content.strip()
        elif isinstance(response, str):
            content = response.strip()
        
        # 清理 JSON 标记
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        
        data = json.loads(content)
        return data
    except Exception:
        return {
            "english_prompt": f"A distinctive {role_tag} character for {topic}, 2D vector illustration",
            "anchor_description": f"the distinctive {role_tag} character"
        }

def design_environments(topic: str):
    """使用 LLM 为当前主题构思 4 个核心场景锚点"""
    print(f"  🧠 [Design] 正在为主题【{topic}】构思核心场景锚点...")
    
    final_url = config.LLM_BASE_URL.rstrip("/")
    client = OpenAI(api_key=config.LLM_API_KEY, base_url=final_url)

    system_prompt = f"""你是一个顶级的电影美术指导。
你的任务是根据一个视频主题，构思 4 个最具代表性的电影感核心场景。

画风约束（不可违反）：
{config.STYLE_ANCHOR}

输出要求：
1. 为每个场景起一个简单的英文名（如 office, street, church）。
2. 提供 [english_prompt]：用于生成场景基准图的详细英文提示词。
3. 提供 [anchor_description]：场景的视觉细节描述，用于锁定光影和材质。

格式（仅输出 JSON 列表）:
[
  {{"name": "office", "english_prompt": "...", "anchor_description": "..."}},
  ...
]"""

    user_prompt = f"请为当前主题【{topic}】构思 4 个核心视觉场景。"

    try:
        response = client.chat.completions.create(
            model=config.MODEL_LLM,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.8
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(content)
    except Exception as e:
        print(f"  ⚠️ 场景构思失败: {e}")
        return []

# ================================================================
#  🧠 智能分析：人生阶段探测 (V6.5 Only)
# ================================================================

def get_needed_stages(topic: str):
    """分析剧本，判定主角经历了哪些人生阶段"""
    # 优先读大纲进行阶段探测，因为定妆照是在写剧本之前生成的
    synopsis_path = BASE_DIR / "feishu" / "temp_synopsis.json"
    text_to_analyze = ""
    
    if synopsis_path.exists():
        print(f"  🔍 [Pruning] 找到剧情大纲，正在分析【{topic}】的人生跨度...")
        try:
            syn_data = json.loads(synopsis_path.read_text(encoding="utf-8"))
            text_to_analyze = syn_data.get("synopsis", "")
        except Exception as e:
            print(f"  ⚠️ 读取大纲失败: {e}")
            
    if not text_to_analyze and config.FULL_STORY_V6_PATH.exists():
        print(f"  🔍 [Pruning] 找不到大纲，正退回使用全文分析【{topic}】...")
        try:
            story_data = json.loads(config.FULL_STORY_V6_PATH.read_text(encoding="utf-8"))

            # 优先读取当前主结构：master_design.full_narration
            text_to_analyze = (
                story_data.get("master_design", {}).get("full_narration", "") or ""
            ).strip()

            # 向后兼容：极旧结构才回退到 chapters
            if not text_to_analyze:
                chapters = story_data.get("chapters", [])
                if isinstance(chapters, list):
                    text_to_analyze = "\n".join(
                        [c.get("full_narration", "") for c in chapters if isinstance(c, dict)]
                    ).strip()
        except Exception as e:
            print(f"  ⚠️ 读取 full_story_v6.json 失败: {e}")
        
    if not text_to_analyze:
        print(f"  ⚠️ [Pruning] 大纲和剧本全都没找到，默认生成【幼年/中年/老年】三阶段定妆。")
        return ["child", "middle", "elderly"]
    
    final_url = config.LLM_BASE_URL.rstrip("/")
    client = OpenAI(api_key=config.LLM_API_KEY, base_url=final_url)

    system_prompt = """你是一个专业的剧本分析师。
根据提供的旁白文案，判定主角在整个故事中具体经历了哪些【人生阶段】。
可选阶段包括：
- child (幼年/童年)
- youth (青年/求学期)
- middle (中年/壮年)
- elderly (老年/晚年)

规则：
1. 只能从上述四个英文关键词中选择。
2. 即使跨度很大中途有跳跃，也只选文案中真正【出现】了的阶段。
3. 请以 JSON 列表格式输出。

输出格式示例: ["child", "middle", "elderly"]"""

    try:
        response = client.chat.completions.create(
            model=config.MODEL_LLM,
            messages=[{"role": "system", "content": system_prompt}, 
                      {"role": "user", "content": f"主题: {topic}\n文本摘要: {text_to_analyze[:2000]}"}],
            temperature=0.3
        )
        content = response.choices[0].message.content.strip()
        if "```" in content:
            content = content.split("```")[1].replace("json", "").strip()
        stages = json.loads(content)
        # 兜底：如果完全识别失败，回退到 middle
        if not stages: stages = ["middle"]
        print(f"  🎯 [Pruning] 检测到必要阶段: {stages}")
        return stages
    except Exception as e:
        print(f"  ⚠️ [Pruning] 识别逻辑失败，回退默认阶段: {e}")
        return ["middle"]

def design_character(topic: str, role_tag: str, stage: str = "middle"):
    """使用 LLM 为角色在特定阶段构思视觉特征"""
    # 阶段翻译（增强 LLM 理解）
    stage_name_cn = {"child": "幼年/童年", "youth": "青年/求学期", "middle": "中年/壮年", "elderly": "老年/晚年"}.get(stage, "中年")
    
    print(f"  🧠 [Design] 正在构思角色: {role_tag} (阶段: {stage_name_cn})...")

    final_url = config.LLM_BASE_URL.rstrip("/")
    client = OpenAI(api_key=config.LLM_API_KEY, base_url=final_url)

    system_prompt = f"""你是一个顶级的角色设计专家。
你的任务是根据一个视频主题，为一个关键角色构思具体的、易于辨识的视觉特征。

【当前角色阶段】：{stage_name_cn} ({stage})

画风约束：
{config.STYLE_ANCHOR}

输出要求：
1. [english_prompt]：英文提示词。必须包含【符合年龄阶段】的相貌、服装。
2. [anchor_description]：角色视觉细节摘要。
3. **阶梯式演变 (CRITICAL)**：
   - [child]：必须体现幼年特征（更矮、头身比更大、面庞稚嫩、穿着简朴），绝对不允许直接使用成人的等比例缩小。允许换发型。
   - [elderly]：必须体现明显的衰老（白发、深刻的皱纹、佝偻或缓慢的体态、沉稳或华贵的服饰）。
4. **神髓一致性**：保持眼神或核心五官的一点神似，确保一眼能看出是同一个人的演变即可。不要强求服装发色一模一样。

格式（仅输出 JSON）:
{{ "english_prompt": "...", "anchor_description": "..." }}"""

    user_prompt = f"请为【{topic}】设计角色类型为 {role_tag} 的【{stage_name_cn}】形象。"

    try:
        response = client.chat.completions.create(
            model=config.MODEL_LLM,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.7
        )
        content = response.choices[0].message.content.strip()
        if "```" in content: content = content.split("```")[1].replace("json", "").strip()
        return json.loads(content)
    except:
        return {"english_prompt": f"A {stage} {role_tag} character for {topic}", "anchor_description": f"the {stage} {role_tag}"}

def _archive_and_clean_category(category: str, target_stage: str = None):
    """物理清场：清理工作台子目录"""
    # 支持主角人生阶段清理
    target_dirs = []
    if category == "protagonist":
        if target_stage:
            target_dirs = [config.CHARACTER_REF_MAP.get(target_stage, config.REFS_PROTAGONIST_MIDDLE)]
        else:
            target_dirs = [config.REFS_PROTAGONIST_CHILD, config.REFS_PROTAGONIST_YOUTH, 
                           config.REFS_PROTAGONIST_MIDDLE, config.REFS_PROTAGONIST_ELDERLY]
    elif category == "supporting":
        target_dirs = [config.REFS_SUPPORTING]
    elif category == "other":
        target_dirs = [config.REFS_OTHER]

    for target_dir in target_dirs:
        if not target_dir or not target_dir.exists(): continue
        files = list(target_dir.glob("*"))
        if not files: continue

        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = config.REFS_BACKUP_DIR / f"{timestamp}_{target_dir.name}"
        backup_path.mkdir(parents=True, exist_ok=True)

        for f in files: shutil.move(str(f), str(backup_path / f.name))
        print(f"  🧹 [Clean] {target_dir.name} 目录已物理归档清理。")

# ================================================================
#  🖼️ 核心生成逻辑
# ================================================================

async def generate_ref_sheet(category: str, english_prompt: str, stage: str = "middle", ref_image_path: Path = None):
    """生成并保存到具体的阶段文件夹，支持参考图引用"""
    # 获取目标文件夹
    if category == "protagonist":
        target_dir = config.CHARACTER_REF_MAP.get(stage, config.REFS_PROTAGONIST_MIDDLE)
    else:
        target_dir = config.CHARACTER_REF_MAP.get(category, config.REFS_OTHER)
        
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / "triple_view.png"

    print(f"  🎨 [Generate] 正在生成 {category} ({stage}) 定妆照 (参考图: {ref_image_path.name if ref_image_path else 'None'})...")
    
    full_prompt = (
        f"Background: PURE FLAT WHITE #FFFFFF BACKGROUND, NO ENVIRONMENT, NO shadows. "
        f"CHARACTER DESIGN SHEET, {config.STYLE_ANCHOR} "
        f"SAME character from 3 angles: 1. FRONT view. 2. SIDE profile. 3. BACK view. "
        f"Character appearance: {english_prompt}"
    )

    try:
        # 🧪 V15.0：物理参考图强插 (如果存在参考图，则传给生图引擎)
        img_refs = [str(ref_image_path)] if ref_image_path else None
        img_bytes = await generate_image(prompt=full_prompt, size="2k", image_refs=img_refs)
        if img_bytes:
            out_path.write_bytes(img_bytes)
            # 🔒 实时备份到金库
            vault_backup(out_path, f"refs/{target_dir.name}/triple_view.png")
            print(f"  ✅ [Done] 已存入: {out_path}")
            return out_path
    except Exception as e:
        print(f"  ❌ [Error] 生图失败: {e}")
    return None

# ================================================================
#  ▶️ 入口执行
# ================================================================

async def run_ref_process(topic: str, category: str, target_stage: str = None):
    """多阶段定妆流水线"""
    print(f"\n🚀 [Ref Pipeline] 开始为【{topic}】定制 {category} 流水线...")
    
    _archive_and_clean_category(category, target_stage)

    if category == "other":
        scenes = design_environments(topic)
        # ...执行场景生成 (此处逻辑与原版一致)
        for scene in scenes:
            name, prompt, desc = scene['name'], scene['english_prompt'], scene['anchor_description']
            full_p = f"WIDE ANGLE CINEMATIC BACKGROUND, {config.STYLE_ANCHOR}, No characters, {prompt}"
            img_b = await generate_image(prompt=full_p, size="2k")
            if img_b:
                p = config.REFS_OTHER / f"{name}.png"
                p.write_bytes(img_b)
                d_p = config.REFS_OTHER / f"description_{name}.txt"
                d_p.write_text(desc, encoding="utf-8")
                vault_backup(p, f"refs/other/{name}.png")
                vault_backup(d_p, f"refs/other/description_{name}.txt")
        print("\n✨ 环境锚点全量完成！")
    
    elif category == "protagonist":
        # 🚨 V15.0 主角核心锚点工作流：中年优先 -> 参考式扩散
        stages = get_needed_stages(topic)
        if target_stage:
            stages = [target_stage]
        
        # 1. 优先捕获中年核心形象历史 (MASTER)
        middle_ref_path = config.CHARACTER_REF_MAP.get("middle", config.REFS_PROTAGONIST_MIDDLE) / "triple_view.png"
        if not middle_ref_path.exists():
            middle_ref_path = None

        if "middle" in stages:
            design = design_character(topic, category, "middle")
            gen_path = await generate_ref_sheet(category, design["english_prompt"], "middle")
            if gen_path:
                desc_f = gen_path.parent / "description.txt"
                desc_f.write_text(design["anchor_description"], encoding="utf-8")
                vault_backup(desc_f, f"refs/{gen_path.parent.name}/description.txt")
                middle_ref_path = gen_path
        
        # 2. 派生生成其他阶段 (基于中年的参考图)
        for stage in [s for s in stages if s != "middle"]:
            design = design_character(topic, category, stage)
            # 🧪 关键：将中年的 middle_ref_path 作为参考图传入
            result_path = await generate_ref_sheet(category, design["english_prompt"], stage, middle_ref_path)
            if result_path:
                desc_file = result_path.parent / "description.txt"
                desc_file.write_text(design["anchor_description"], encoding="utf-8")
                vault_backup(desc_file, f"refs/{result_path.parent.name}/description.txt")
        
        print(f"\n✨ 主角 ({len(stages)}个阶段) 锚点式定妆成功合拢！")

        # ✅ BUG-06 修复：将生成的图片物理路径写回 full_story_v6.json
        # 这样 step1_writer_v6.py 才能读到 physical_char_anchors，VLM 才有参考图
        if config.FULL_STORY_V6_PATH.exists():
            try:
                story_data = json.loads(config.FULL_STORY_V6_PATH.read_text(encoding="utf-8"))
                physical_anchors = {}
                for _stage, _dir in [
                    ("child",   config.REFS_PROTAGONIST_CHILD),
                    ("youth",   config.REFS_PROTAGONIST_YOUTH),
                    ("middle",  config.REFS_PROTAGONIST_MIDDLE),
                    ("elderly", config.REFS_PROTAGONIST_ELDERLY),
                ]:
                    _img = _dir / "triple_view.png"
                    if _img.exists():
                        physical_anchors[_stage] = str(_img.resolve())
                master_design = story_data.setdefault("master_design", {})
                master_design["physical_char_anchors"] = physical_anchors
                # 记录本次阶段探测结果，供飞书卡片准确显示“涉及/未涉及”
                master_design["detected_life_stages"] = stages

                existing_stage_map = master_design.get("stage_map")
                # 仅在 stage_map 缺失时兜底；兜底只给一个全范围阶段，避免多阶段重叠覆盖
                if not existing_stage_map:
                    if "middle" in physical_anchors:
                        fallback_stage = "middle"
                    elif physical_anchors:
                        fallback_stage = next(iter(physical_anchors.keys()))
                    else:
                        fallback_stage = "middle"

                    master_design["stage_map"] = [{
                        "stage": fallback_stage,
                        "start_shot": 1,
                        "end_shot": 999
                    }]
                config.FULL_STORY_V6_PATH.write_text(
                    json.dumps(story_data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(f"  ✅ [BUG-06 Fix] physical_char_anchors 已写入 full_story_v6.json: {list(physical_anchors.keys())}")
                vault_backup(config.FULL_STORY_V6_PATH, f"scripts/{config.FULL_STORY_V6_PATH.name}")
            except Exception as _e:
                print(f"  ⚠️ [BUG-06 Fix] 写入 physical_char_anchors 失败: {_e}")
        
    else:
        # 配角模式
        design = design_character(topic, category, "middle")
        result_path = await generate_ref_sheet(category, design["english_prompt"], "middle")
        if result_path:
            desc_f = result_path.parent / "description.txt"
            desc_f.write_text(design["anchor_description"], encoding="utf-8")
            vault_backup(desc_f, f"refs/{category}/description.txt")
        print(f"\n✨ {category} 定妆完成！")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="角色定妆器 v3.1 原子版")
    parser.add_argument("--topic", type=str, required=True, help="视频主题")
    parser.add_argument("--role", type=str, default="protagonist", 
                        choices=["protagonist", "supporting", "other"], help="角色类别")
    parser.add_argument("--stage", type=str, default=None, help="仅重画指定阶段")
    args = parser.parse_args()
    asyncio.run(run_ref_process(args.topic, args.role, args.stage))
