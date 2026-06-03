# -*- coding: utf-8 -*-
"""
🎬 "调色板" AI 电影级独立桌面 APP - 窗口管理器 (start_app.py)
======================================================
重构版 v2.0：
- 废弃 api_server.py HTTP 通信层，彻底解决 CORS 跨域拦截问题。
- 全面改用 pywebview 原生 JS Bridge (pywebview.api) 进行前后端通信。
- 使用 http_server=True 托管本地静态资源（图片、视频），支持相对路径访问。
- 窗口关闭即完全退出，无任何残留后台进程。
"""

import os
import sys
import json
import shutil
import asyncio
import subprocess
import time
from pathlib import Path

# ── 🌐 强制指定全局终端流为 UTF-8 编码 ──
os.environ["PYTHONIOENCODING"] = "utf-8"

# ── 🔑 加载本地 .env 环境变量 ──
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ── 💡 自动补齐缺失的轻量级桌面依赖库 ──
try:
    import webview
except ImportError:
    print("[系统] 检测到 pywebview 缺失，正在自动补齐...")
    python_exe = sys.executable or "python"
    subprocess.run(
        [python_exe, "-m", "pip", "install", "pywebview", "-i",
         "https://pypi.tuna.tsinghua.edu.cn/simple"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    import webview

# ── 路径定位 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR_PATH = Path(BASE_DIR)
sys.path.insert(0, BASE_DIR)

# ── 导入项目核心模块 ──
import src.style_config as config
from src.run_context import start_new_run, get_paths, get_current_run_id
from src.ref_generator import generate_ref_sheet_at
from src.image_engine import generate_image as _gen_img

# story_planner_v6 可能在 src/ 中，尝试两种导入方式
try:
    import story_planner_v6 as planner
except ImportError:
    from src import story_planner_v6 as planner

# ── 全局会话状态（从 api_server.py 迁移）──
GLOBAL_STATE = {
    "current_run_id": "",
    "topic": "my_epic_story",
    "mode_path": "RED",
    "original_text": "",
    "compiled_voiceover": "",
    "entities": [],
    "style_presets": "cinematic realism, commercial grading, 35mm photograph",
    "seed": 40984180,
    "polish_enabled": False,
    "last_compiled_synopsis": {},
    "cast_prompt": (
        "[character]\n"
        "A cute cartoon stickman style representation of {entity}. Flat colors, strong outline, white background.\n\n"
        "[scene]\n"
        "A flat 2D vector style minimalist cartoon background scenery depicting {entity}. Flat shades, no character.\n\n"
        "[prop]\n"
        "A flat 2D vector icon cartoon object depicting {entity}. Primitive shape, flat color fill, white background."
    ),
    "storyboard_prompt": (
        "【画风锚点】\n"
        "Cyanide and Happiness comic style, 2D vector / flat graphic cartoon, bold black outlines, vivid flat color fills, "
        "pure 2D, no photoreal skin texture, no 3D/CGI. 允许卡通级光向（key direction, warm/cool, simple hard-edge shadow shapes），"
        "禁止电影级体积光与写实 subsurface skin。\n\n"
        "【分镜表现规则】\n"
        "★ 动态表情与肢体（核心要求：打破参考图的呆滞感！）：必须深度解析当前分镜的故事情节，"
        "强制赋予角色强烈且符合情境的情绪反应。\n"
        "1. 必须采用【核心情绪词 + 氰化物式五官拆解】组合。例如不要只写 mouth line，必须写："
        "terrified expression, sharply angled frowning eyebrows, wide dilated dot eyes, screaming jagged mouth shape.\n"
        "2. 明确指令：绝不允许角色保持中立或被参考图的默认表情带偏"
        "（DO NOT copy the neutral expression from reference）。\n"
        "3. 肢体辅助：情绪必须配合夸张的肢体动作"
        "（如 recoiling in horror, pointing aggressively, slumping in defeat）。\n"
        "4. 脸部特写：当情绪是当前帧重点时，明确写明 close-up on explicit facial expression。"
    )
}

# ── 全局窗口引用 ──
GLOBAL_WINDOW = None


def _to_relative_url(abs_path: Path) -> str:
    """
    将绝对路径转换为相对于 BASE_DIR 的 URL 路径（正斜杠）。
    配合 http_server=True 时，前端可以直接用此相对路径作为 img/video src。
    """
    try:
        rel = abs_path.relative_to(BASE_DIR_PATH)
        return str(rel).replace("\\", "/")
    except ValueError:
        return abs_path.as_uri()


def _is_drama_mode(mode_path: str) -> bool:
    """
    判断当前频道是否为剧情/叙事模式（生成 3 张人-景-物大卡）。
    - 只有 ch_drama（含 RED/BLUE/ROLEPLAY 兼容别名）返回 True。
    - 科普、美食、财经、历史等一切解说类频道返回 False（生成 1 张背景底图）。
    """
    m = str(mode_path).upper()
    return "DRAMA" in m or m in ("RED", "BLUE", "ROLEPLAY")


def _get_channel_assets_config(mode_path: str) -> list:
    """
    根据 mode_path 返回其对应的资产配置数组。
    每个资产对象包含:
      {
        "label": "主角",
        "type": "character"  # character | scene | prop
      }
    - 兼容经典 "DRAMA": 3卡 (主角 [character], 场景 [scene], 道具 [prop])
    - 兼容经典 "SCIENCE" / 其他默认: 1卡 (视觉基调背景 [scene])
    - 自定义频道: 从 data/channels_presets.json 中加载
    """
    m = str(mode_path).upper()
    
    # 兼容经典剧情模式
    if "DRAMA" in m or m in ("RED", "BLUE", "ROLEPLAY"):
        return [
            {"label": "主角", "type": "character"},
            {"label": "核心场景", "type": "scene"},
            {"label": "线索道具", "type": "prop"}
        ]
    
    # 尝试从 channels_presets.json 读取自定义频道的 assets_config
    try:
        channels_file = os.path.join(BASE_DIR, "data", "channels_presets.json")
        if os.path.exists(channels_file):
            import json
            with open(channels_file, "r", encoding="utf-8") as f:
                channels = json.load(f)
            for ch in channels:
                if str(ch.get("id", "")).upper() == m:
                    if ch.get("channelType") == "custom" and ch.get("assets_config"):
                        return ch["assets_config"]
                    break
    except Exception as e:
        print(f"[Warning] Failed to load custom channel config for {mode_path}: {e}")

    # 默认科普/解说模式兜底 (1张卡)
    return [
        {"label": "视觉基调背景", "type": "scene"}
    ]


def _extract_entities_manually(text: str, mode_path: str = "RED"):
    """提炼核心视觉实体词，根据频道类型与卡片配置智能切换。
    - 剧情模式 → 提炼 3 词 [角色, 场景, 道具]
    - 自定义资产模式 → 根据自定义的 assets_config 列表数量和标签名动态提炼
    - 科普/解说/其他模式 → 提炼 1 词 [视觉背景底板]
    """
    client = planner.get_client()

    assets_config = _get_channel_assets_config(mode_path)
    N = len(assets_config)
    
    labels = [ast["label"] for ast in assets_config]
    types = [ast["type"] for ast in assets_config]
    
    print(f"[Bridge] 正在为 {mode_path} 提炼 {N} 个核心视觉要素: {labels}...")
    
    sys_prompt = f"""你是一个专业的剧本视频制作分析师。请读下方文本，根据当前频道的画面元素配置，精确提炼出【{N}个最核心视觉元素】。
我们需要的元素依次是：
"""
    for idx, (lbl, typ) in enumerate(zip(labels, types)):
        typ_ch = "人物角色" if typ == "character" else ("背景场景" if typ == "scene" else "实体道具")
        sys_prompt += f"{idx + 1}. 【{lbl}】({typ_ch})\n"
        
    sys_prompt += f"""
请严格按顺序和要求进行提炼，仅返回一个中文 JSON 数组（包含这 {N} 个词，例如：{json.dumps([f"{lbl}示例" for lbl in labels], ensure_ascii=False)}），不要包含任何解释、分析或 markdown 语法包裹的围栏。
"""
    fallback = [f"核心_{lbl}" for lbl in labels]

    try:
        response = client.chat.completions.create(
            model=config.MODEL_LLM,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.3,
            max_tokens=250
        )
        content = response.choices[0].message.content.strip()
        if "```" in content:
            content = content.split("```")[1].replace("json", "").strip()
        
        res = json.loads(content)
        if isinstance(res, list) and len(res) >= N:
            return res[:N]
        elif isinstance(res, list) and len(res) > 0:
            while len(res) < N:
                res.append(fallback[len(res)])
            return res
        else:
            return fallback
    except Exception as e:
        print(f"⚠️ [Bridge] 提炼实体词失败: {e}，将采用兜底词。")
        return fallback


def _generate_cast_prompts_via_llm(topic: str, synopsis_text: str, entities: list, custom_template: str = ""):
    """根据故事简介与提取出的资产词，并参考定制风格模板，调用大模型动态构思符合该故事背景的定妆照提示词"""
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
            match_lbl = re.search(rf"\\[{re.escape(lbl)}\\](.*?)(\\[|$)", custom_template, re.DOTALL | re.IGNORECASE)
            if match_lbl:
                tpl = match_lbl.group(1).strip()
            else:
                match_typ = re.search(rf"\\[{re.escape(typ)}\\](.*?)(\\[|$)", custom_template, re.DOTALL | re.IGNORECASE)
                if match_typ:
                    tpl = match_typ.group(1).strip()
        baseline_prompts.append(tpl)
        
    # 3. 构造大模型 Prompt
    sys_prompt = f"""You are a master concept designer and visual storyteller for a vector comic pipeline.
Your job is to write detailed narrative-driven visual prompt descriptions for {N} elements based on the topic "{topic}" and the story:
"""
    for idx, (lbl, typ, ent) in enumerate(zip(labels, types, ents)):
        sys_prompt += f"{idx + 1}. Element [{lbl}]: representing \"{ent}\" (Type: {typ})\n"
        
    sys_prompt += f"""
Output ONLY a raw JSON object where keys are the EXACT labels: {json.dumps(labels, ensure_ascii=False)}.
Each value must be a highly detailed English paragraph (60-90 words, no bullet lists, no markdown) containing rich, story-specific visual details.
You MUST follow the style and structure constraints of these baseline templates, and expand/infuse the {{entity}} descriptions with rich narrative details:
"""
    for lbl, tpl, ent in zip(labels, baseline_prompts, ents):
        sys_prompt += f"- For element \"{lbl}\" (representing \"{ent}\"\): Expand upon the baseline template: \"{tpl}\"\n"
        
    sys_prompt += f"""
Format:
{{
"""
    for idx, lbl in enumerate(labels):
        comma = "," if idx < N - 1 else ""
        sys_prompt += f'  "{lbl}": "..."{comma}\n'
    sys_prompt += "}"
    
    user_content = f"Story Synopsis:\n{synopsis_text}"
    
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
            cast_prompt_parts.append(f"[{lbl}]\\n{desc}")
            
        cast_prompt = "\\n\\n".join(cast_prompt_parts)
        print("[Bridge] 动态定妆提示词大模型构思成功！")
        return cast_prompt
    except Exception as e:
        print(f"⚠️ [Bridge] 动态构思定妆提示词失败: {e}，将采用备用默认模板。")
        cast_prompt_parts = []
        for lbl, tpl, ent in zip(labels, baseline_prompts, ents):
            desc = tpl.replace("{entity}", ent).replace("{ent}", ent)
            cast_prompt_parts.append(f"[{lbl}]\\n{desc}")
        return "\\n\\n".join(cast_prompt_parts)


class DesktopApiBridge:
    """
    🌉 前后端交互桥梁 v2.0 (pywebview JS Bridge)
    ================================================
    - 替代 api_server.py 的全部 HTTP 接口
    - 前端通过 window.pywebview.api.method() 直接调用
    - 完全免疫 CORS 跨域拦截，零端口依赖
    - 每个方法统一 try/except，出错时返回 {"status": "error", "detail": "..."}
    """

    # ──────────────────────────────────────────────
    # ❤️ 心跳检测  替代 GET /api/health
    # ──────────────────────────────────────────────
    def health_check(self):
        return {"status": "success", "msg": "Palette Cinema Bridge v2.0 is live!"}

    # ──────────────────────────────────────────────
    # 📊 实时审计大盘日志数据读取
    # ──────────────────────────────────────────────
    def get_realtime_audit_logs(self):
        """
        📊 从 7 个阶段文件夹中读取 calls.jsonl，返回执行快照
        """
        import re
        run_id = GLOBAL_STATE.get("current_run_id", "")
        if not run_id:
            run_id = get_current_run_id()
        if not run_id:
            return {"status": "success", "stages": []}

        run_dir = BASE_DIR_PATH / "data" / "runs" / run_id
        backstage_dir = run_dir / "后台"

        stages = [
            {"dir": "001-梗概", "name": "电影大纲梗概设计"},
            {"dir": "003-定妆", "name": "核心资产定妆绘制"},
            {"dir": "002-旁白", "name": "电影旁白文案扩写"},
            {"dir": "004-音频与节拍", "name": "配音合成与音轨节拍"},
            {"dir": "005-分镜与画面", "name": "镜头画面描述设计"},
            {"dir": "006-宫格生图", "name": "分镜底片大图绘制"},
            {"dir": "007-组装成片", "name": "超分高清与后期拼装"}
        ]

        active_stage = GLOBAL_STATE.get("active_stage", "")
        results = []

        for stage in stages:
            stage_dir = backstage_dir / stage["dir"]
            stage_status = "pending"
            calls = []

            if stage_dir.exists():
                calls_file = stage_dir / "calls.jsonl"
                if calls_file.exists():
                    try:
                        content = calls_file.read_text(encoding="utf-8")
                        blocks = re.split(r'#\s*={10,}\s*#', content)
                        for block in blocks:
                            block = block.strip()
                            if not block:
                                continue
                            try:
                                item = json.loads(block)
                                calls.append({
                                    "time": item.get("时间_UTC", ""),
                                    "step": item.get("步骤标识", ""),
                                    "step_cn": item.get("步骤说明", "") or item.get("步骤标识", ""),
                                    "ok": item.get("是否成功", True),
                                    "duration": item.get("耗时_秒", 0.0),
                                    "attempt": item.get("本步骤内第几次请求", 1),
                                    "model": item.get("模型", ""),
                                    "error": item.get("错误摘要", "")
                                })
                            except Exception:
                                pass
                    except Exception:
                        pass

                if active_stage == stage["dir"]:
                    stage_status = "running"
                elif len(calls) > 0:
                    last_ok = calls[-1]["ok"]
                    stage_status = "success" if last_ok else "failed"
                else:
                    stage_status = "running"
            else:
                if active_stage == stage["dir"]:
                    stage_status = "running"
                else:
                    stage_status = "pending"

            results.append({
                "id": stage["dir"],
                "name": stage["name"],
                "status": stage_status,
                "calls": calls
            })

        return {"status": "success", "stages": results}

    # ──────────────────────────────────────────────
    # 🔍 探测历史会话恢复现场
    # ──────────────────────────────────────────────
    def get_restorable_session(self):
        """
        🔍 扫描 current_run.json，对活跃的 Run-ID 执行分级物理存在探测，并拼装自愈 Payload 返回
        """
        print("[Bridge] 正在扫描检查是否存在可恢复的历史现场...")
        run_id = get_current_run_id()
        if not run_id:
            return {"status": "none", "msg": "No previous session found."}

        run_dir = BASE_DIR_PATH / "data" / "runs" / run_id
        if not run_dir.exists():
            return {"status": "none", "msg": "Run directory does not exist."}

        temp_synopsis_path = run_dir / "scripts" / "temp_synopsis.json"
        full_story_path = run_dir / "scripts" / "full_story_v6.json"
        narrative_path = run_dir / "scripts" / "narrative_v6_final.json"
        video_path = run_dir / "output" / "narrative_v6_final_epic.mp4"

        synopsis_data = {}
        if temp_synopsis_path.exists():
            try:
                synopsis_data = json.loads(temp_synopsis_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        # 1. 恢复基本变量，包括核心视觉词实体
        # 从 run_id 中推断频道类型（topic = "director_cut_" + mode_path.lower()）
        mode_path = GLOBAL_STATE.get("mode_path", "RED")
        if not mode_path or mode_path == "RED":
            # 尝试从 run_id 进一步推断
            run_id_lower = run_id.lower()
            if "drama" in run_id_lower:
                mode_path = "CH_DRAMA"
            elif "science" in run_id_lower or "yellow" in run_id_lower:
                mode_path = "CH_SCIENCE"
            elif "blue" in run_id_lower:
                mode_path = "BLUE"
            else:
                mode_path = "RED"

        entities = GLOBAL_STATE.get("entities") or []
        if not entities and synopsis_data:
            compiled_text = synopsis_data.get("synopsis", "")
            if compiled_text:
                entities = _extract_entities_manually(compiled_text, mode_path)
                GLOBAL_STATE["entities"] = entities

        # 2. 恢复定妆卡片（支持自定义及兜底通道的资产配置）
        assets = []
        assets_config = _get_channel_assets_config(mode_path)
        labels = [ast["label"] for ast in assets_config]
        types = [ast["type"] for ast in assets_config]
        has_assets = True

        for idx, (label, t) in enumerate(zip(labels, types)):
            card_id = f"cast_0{idx + 1}"
            img_file = run_dir / "refs" / card_id / "triple_view.png"
            if img_file.exists():
                img_url = _to_relative_url(img_file)
                prompt = ""
                # 如果有提炼的实体，高精构思还原 prompts
                if idx < len(entities):
                    ent = entities[idx]
                    name_str = f"{label}：{ent}"
                    
                    cast_template = GLOBAL_STATE.get("cast_prompt", "")
                    char_prompt = "A cute cartoon stickman style representation of {entity}. Flat colors, strong outline, white background."
                    scene_prompt = "A flat 2D vector style minimalist cartoon background scenery depicting {entity}. Flat shades, no character."
                    prop_prompt = "A flat 2D vector icon cartoon object depicting {entity}. Primitive shape, flat color fill, white background."

                    if cast_template.strip():
                        import re
                        lbl_match = re.search(rf"\[{re.escape(label)}\](.*?)(\[|$)", cast_template, re.DOTALL | re.IGNORECASE)
                        if lbl_match:
                            matched_prompt = lbl_match.group(1).strip()
                            if t == "character": char_prompt = matched_prompt
                            elif t == "scene": scene_prompt = matched_prompt
                            elif t == "prop": prop_prompt = matched_prompt
                        else:
                            typ_match = re.search(rf"\[{re.escape(t)}\](.*?)(\[|$)", cast_template, re.DOTALL | re.IGNORECASE)
                            if typ_match:
                                matched_prompt = typ_match.group(1).strip()
                                if t == "character": char_prompt = matched_prompt
                                elif t == "scene": scene_prompt = matched_prompt
                                elif t == "prop": prop_prompt = matched_prompt

                    if t == "scene":
                        prompt = scene_prompt.replace("{entity}", ent).replace("{ent}", ent)
                    elif t == "prop":
                        prompt = prop_prompt.replace("{entity}", ent).replace("{ent}", ent)
                    else:
                        prompt = char_prompt.replace("{entity}", ent).replace("{ent}", ent)
                else:
                    name_str = f"{label}"

                assets.append({
                    "id": card_id,
                    "name": name_str,
                    "prompt": prompt,
                    "svgType": t,
                    "image_url": img_url
                })
            else:
                has_assets = False

        grids = []
        frames = []
        if narrative_path.exists():
            try:
                with open(narrative_path, "r", encoding="utf-8") as f:
                    narr_data = json.load(f)
                timeline = narr_data.get("timeline") or narr_data.get("shots") or []
                total_shots = len(timeline)
                
                # Reconstruct grids
                batches = [timeline[i:i + 16] for i in range(0, len(timeline), 16)]
                storyboards_dir = run_dir / "storyboards"
                for idx, batch_shots in enumerate(batches):
                    batch_index = idx + 1
                    batch_start = (batch_index - 1) * 16 + 1
                    batch_end = min(batch_start + len(batch_shots) - 1, total_shots)
                    
                    grid_filename = f"grid_batch_{batch_index:03d}.png"
                    grid_file = storyboards_dir / grid_filename
                    if grid_file.exists():
                        img_url = _to_relative_url(grid_file)
                        
                        prompt_lines = []
                        for shot_idx, shot in enumerate(batch_shots, start=batch_start):
                            prompt_lines.append(f"F-{shot_idx:02d}: {shot.get('visual_prompt', '')}")
                        prompt_str = "\n".join(prompt_lines)
                        
                        grids.append({
                            "id": f"grid_batch_{batch_index:03d}",
                            "batch_index": batch_index,
                            "image_url": img_url,
                            "range_text": f"分镜 F-{batch_start:02d} ~ F-{batch_end:02d}",
                            "prompt": prompt_str
                        })

                # Reconstruct sliced frames (if they exist)
                for idx, shot in enumerate(timeline):
                    frame_num = idx + 1
                    frame_id = f"frame_0{frame_num}"
                    img_filename = f"S_00{frame_num}.png"
                    img_file = storyboards_dir / img_filename
                    img_url = _to_relative_url(img_file) if img_file.exists() else ""
                    frames.append({
                        "id": frame_id,
                        "text": shot.get("voiceover_text", "电影叙事中..."),
                        "prompt": shot.get("visual_prompt", "cinematic shot"),
                        "image_url": img_url,
                        "time_range": f"{shot.get('trigger_time', 0):.1f}s - {shot.get('trigger_time', 0) + 3.5:.1f}s"
                    })
            except Exception as parse_err:
                print(f"Error parsing grids/frames for recovery: {parse_err}")
                pass

        has_video = video_path.exists()
        video_url = _to_relative_url(video_path) if has_video else ""
        relative_video_path = f"{run_id}/output/narrative_v6_final_epic.mp4" if has_video else ""

        stage = "C"
        if has_video:
            stage = "F"
        elif len(grids) > 0 or len(frames) > 0:
            stage = "E"
        elif len(assets) > 0 and has_assets:
            stage = "D1"
        elif synopsis_data:
            stage = "C"
        else:
            return {"status": "none", "msg": "Empty session"}

        # 恢复全局 Python 状态树
        GLOBAL_STATE["current_run_id"] = run_id
        GLOBAL_STATE["mode_path"] = mode_path
        if synopsis_data:
            GLOBAL_STATE["original_text"] = synopsis_data.get("synopsis", "")
            GLOBAL_STATE["compiled_voiceover"] = synopsis_data.get("synopsis", "")

        # 恢复 seed 与 润色标记 
        seed = 40984180
        polish_enabled = False
        if synopsis_data:
            polish_enabled = synopsis_data.get("story_source") != "user_script"

        print(f"[Bridge] 成功定位并完全恢复活跃的历史批次 {run_id}。推荐恢复阶段：{stage}，模式：{mode_path}")
        return {
            "status": "success",
            "run_id": run_id,
            "stage": stage,
            "mode_path": mode_path,
            "seed": seed,
            "entities": entities,
            "polish_enabled": polish_enabled,
            "synopsis": synopsis_data,
            "assets": assets,
            "frames": frames,
            "grids": grids,
            "video_url": video_url,
            "relative_video_path": relative_video_path
        }

    # ──────────────────────────────────────────────
    # 📝 剧本编译  替代 POST /api/story/v1/compile
    # ──────────────────────────────────────────────
    def compile_story(self, payload):
        print("\n[Bridge] 收到剧本编译请求。")
        try:
            GLOBAL_STATE["active_stage"] = "001-梗概"
            mode_path = payload.get("mode_path", "RED")
            original_text = payload.get("original_text", "")
            pipeline_config = payload.get("pipeline_config", {})
            polish_flow = pipeline_config.get("polish_flow", {})
            voiceover_flow = pipeline_config.get("voiceover_flow", {})
            render_flow = pipeline_config.get("render_flow", {})

            print(f"[Bridge] 模式: {mode_path}，润色: {polish_flow.get('enabled', False)}")

            # 开启全新隔离批次
            topic = "director_cut_" + mode_path.lower()
            run_dir = start_new_run(topic=topic)
            run_id = run_dir.name
            paths = get_paths(create_if_missing=True)
            scripts_dir = paths["scripts_dir"]

            GLOBAL_STATE["current_run_id"] = run_id
            GLOBAL_STATE["topic"] = topic
            GLOBAL_STATE["mode_path"] = mode_path
            GLOBAL_STATE["original_text"] = original_text
            GLOBAL_STATE["style_presets"] = render_flow.get("style_presets", "")
            GLOBAL_STATE["seed"] = render_flow.get("seed", 40984180)
            GLOBAL_STATE["polish_enabled"] = polish_flow.get("enabled", False)
            if render_flow.get("cast_prompt"):
                GLOBAL_STATE["cast_prompt"] = render_flow.get("cast_prompt")
            if render_flow.get("storyboard_prompt"):
                GLOBAL_STATE["storyboard_prompt"] = render_flow.get("storyboard_prompt")

            # 动态覆盖后台提示词
            custom_style = render_flow.get("style_presets", "")
            if custom_style.strip():
                config.STYLE_ANCHOR = custom_style
                config.REF_STYLE_ANCHOR = custom_style
                os.environ["STYLE_ANCHOR"] = custom_style
                os.environ["REF_STYLE_ANCHOR"] = custom_style

            custom_polish = polish_flow.get("system_prompt", "")
            if custom_polish.strip():
                planner.SYNOPSIS_SYSTEM_PROMPT = custom_polish

            compiled_voiceover = ""
            syn_result = {}

            if polish_flow.get("enabled", False):
                print("[Bridge] ✨ 润色开关已打开，呼唤编剧大模型加工剧本...")
                feedback_str = polish_flow.get("feedback", "")
                syn_result = planner.polish_user_script_synopsis(
                    raw_user_input=original_text, feedback=feedback_str
                )
                if not syn_result:
                    GLOBAL_STATE["active_stage"] = ""
                    return {"status": "error", "detail": "大模型剧本润色失败，请重试。"}
                syn_result = planner.normalize_synopsis_payload(syn_result)
                compiled_voiceover = syn_result.get("synopsis", "")
            else:
                print("[Bridge] 🔒 锁死原著直出！")
                paras = [p.strip() for p in original_text.split("\n") if p.strip()]
                if len(paras) < 4:
                    paras = [s.strip() + "。" for s in original_text.split("。") if s.strip()]
                acts = planner._bucket_strings_for_n_segments(paras, 4)
                syn_result = {
                    "synopsis_acts": acts,
                    "synopsis": original_text,
                    "era": "",  # 改为空白，防止硬编码“霓虹雨夜”污染用户自建频道的定制风格
                    "identity": "主角",
                    "industry_rules": ["保留用户原著不可篡改"],
                    "story_source": "user_script",
                    "duration": 1.0
                }
                compiled_voiceover = original_text

            # 写入本地大纲缓存
            temp_synopsis_path = scripts_dir / "temp_synopsis.json"
            with open(temp_synopsis_path, "w", encoding="utf-8") as f:
                json.dump(syn_result, f, ensure_ascii=False, indent=2)

            GLOBAL_STATE["last_compiled_synopsis"] = syn_result

            # 提炼视觉实体（按频道类型分区：剧情→3词，科普/解说→1词）
            entities = _extract_entities_manually(compiled_voiceover, mode_path)
            GLOBAL_STATE["entities"] = entities
            GLOBAL_STATE["compiled_voiceover"] = compiled_voiceover

            # 动态生成定妆照提示词（仅剧情频道需要三卡提示词，科普频道跳过）
            if _is_drama_mode(mode_path) and entities:
                custom_tpl = GLOBAL_STATE.get("cast_prompt", "")
                dynamic_cast_prompt = _generate_cast_prompts_via_llm(topic, compiled_voiceover, entities, custom_template=custom_tpl)
                GLOBAL_STATE["cast_prompt"] = dynamic_cast_prompt
            else:
                dynamic_cast_prompt = ""
                GLOBAL_STATE["cast_prompt"] = ""

            print(f"[Bridge] ✅ 剧本编译成功！Run ID: {run_id}，实体: {entities}")
            GLOBAL_STATE["active_stage"] = ""
            return {
                "status": "success",
                "data": {
                    "compiled_voiceover": compiled_voiceover,
                    "extracted_entities": entities,
                    "cast_prompt": dynamic_cast_prompt
                }
            }
        except Exception as e:
            GLOBAL_STATE["active_stage"] = ""
            import traceback
            print(f"❌ [Bridge] 编译剧本失败: {traceback.format_exc()}")
            return {"status": "error", "detail": f"剧本编译失败: {str(e)}"}

    # ──────────────────────────────────────────────
    # 🎨 定妆照生成  替代 POST /api/assets/v1/generate
    # ──────────────────────────────────────────────
    def generate_assets(self, payload):
        run_id = GLOBAL_STATE.get("current_run_id", "")
        topic = GLOBAL_STATE.get("topic", "")
        if not run_id:
            return {"status": "error", "detail": "未检测到活跃的 Run-ID，请先提交剧本。"}

        print(f"\n[Bridge] 为批次 {run_id} 渲染定妆画资产...")
        try:
            GLOBAL_STATE["active_stage"] = "003-定妆"
            entities = payload.get("entities", [])
            global_style_prompt = payload.get("global_style_prompt", "")
            seed = payload.get("seed", 40984180)

            paths = get_paths()
            refs_dir = paths["refs_dir"]

            config.REF_STYLE_ANCHOR = global_style_prompt
            config.STYLE_ANCHOR = global_style_prompt
            os.environ["REF_STYLE_ANCHOR"] = global_style_prompt
            os.environ["STYLE_ANCHOR"] = global_style_prompt

            # ── 按频道类型确定卡片配置 ──
            mode_path = GLOBAL_STATE.get("mode_path", "RED")
            assets_config = _get_channel_assets_config(mode_path)
            labels = [ast["label"] for ast in assets_config]
            types  = [ast["type"] for ast in assets_config]
            print(f"[Bridge] 频道 ({mode_path}) 配置的资产卡片共 {len(assets_config)} 张卡片。")

            assets_res = []

            for idx, (ent, label, t) in enumerate(zip(entities, labels, types)):
                card_id = f"cast_0{idx + 1}"
                out_dir = refs_dir / card_id
                out_dir.mkdir(parents=True, exist_ok=True)

                cast_template = GLOBAL_STATE.get("cast_prompt", "")
                char_prompt = "A cute cartoon stickman style representation of {entity}. Flat colors, strong outline, white background."
                scene_prompt = "A flat 2D vector style minimalist cartoon background scenery depicting {entity}. Flat shades, no character."
                prop_prompt = "A flat 2D vector icon cartoon object depicting {entity}. Primitive shape, flat color fill, white background."

                if cast_template.strip():
                    import re
                    lbl_match = re.search(rf"\[{re.escape(label)}\](.*?)(\[|$)", cast_template, re.DOTALL | re.IGNORECASE)
                    if lbl_match:
                        matched_prompt = lbl_match.group(1).strip()
                        if t == "character": char_prompt = matched_prompt
                        elif t == "scene": scene_prompt = matched_prompt
                        elif t == "prop": prop_prompt = matched_prompt
                    else:
                        typ_match = re.search(rf"\[{re.escape(t)}\](.*?)(\[|$)", cast_template, re.DOTALL | re.IGNORECASE)
                        if typ_match:
                            matched_prompt = typ_match.group(1).strip()
                            if t == "character": char_prompt = matched_prompt
                            elif t == "scene": scene_prompt = matched_prompt
                            elif t == "prop": prop_prompt = matched_prompt

                if t == "scene":
                    prompt = scene_prompt.replace("{entity}", ent).replace("{ent}", ent)
                elif t == "prop":
                    prompt = prop_prompt.replace("{entity}", ent).replace("{ent}", ent)
                else:
                    prompt = char_prompt.replace("{entity}", ent).replace("{ent}", ent)

                print(f"[Bridge] 渲染定妆卡片 [{label} - {ent}]...")

                img_file = out_dir / "triple_view.png"

                if t in ("scene", "prop"):
                    # 场景/背景/道具：直接生图，不走三视图流程
                    if t == "scene":
                        lines = [
                            "A flat 2D vector style minimalist cartoon background scenery, WIDE ANGLE CINEMATIC BACKGROUND, No characters, no people.",
                            "Lighting: flat even cartoon lighting—no dramatic cast shadows, rim light, or studio volumetrics.",
                            f"Style (summary): {global_style_prompt}",
                            f"Scenery Details: {prompt}"
                        ]
                    else:
                        lines = [
                            "A flat 2D vector icon cartoon object on a flat pure white #FFFFFF background only—no floor, horizon, or environment.",
                            "Lighting: flat even cartoon lighting—no dramatic cast shadows, rim light, or studio volumetrics.",
                            f"Style (summary): {global_style_prompt}",
                            f"Object Details: {prompt}"
                        ]
                    full_prompt = "\n".join(lines)

                    from src.api_audit import PHASE_CASTING
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        img_bytes = loop.run_until_complete(_gen_img(
                            prompt=full_prompt,
                            size="2k",
                            standalone_prompt=True,
                            audit_phase=PHASE_CASTING,
                            audit_step=f"triple_view/{card_id}"
                        ))
                        if img_bytes:
                            img_file.write_bytes(img_bytes)
                            try:
                                from src.project_vault import backup as vault_backup
                                rel = str(img_file.relative_to(BASE_DIR)).replace("\\", "/")
                                vault_backup(img_file, rel)
                            except Exception:
                                pass
                    finally:
                        loop.close()
                        asyncio.set_event_loop(None)
                else:
                    # 角色：走 generate_ref_sheet_at 保留三视图
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(generate_ref_sheet_at(
                            out_dir=out_dir,
                            english_prompt=prompt,
                            ref_image_path=None
                        ))
                    finally:
                        loop.close()
                        asyncio.set_event_loop(None)

                img_url = _to_relative_url(img_file) + f"?t={int(time.time())}" \
                    if img_file.exists() else ""

                assets_res.append({
                    "id": card_id,
                    "name": f"{label}：{ent}",
                    "prompt": prompt,
                    "svgType": t,
                    "image_url": img_url
                })

            # 回写 full_story_v6.json 锚点（支持任意自定义卡片数量与类型）
            full_story_path = paths["scripts_dir"] / "full_story_v6.json"
            physical_anchors = {}
            char_idx = 0
            scene_idx = 0
            prop_idx = 0

            for idx, ast in enumerate(assets_res):
                card_t = ast.get("svgType", "character")
                path_str = str(refs_dir / f"cast_0{idx + 1}" / "triple_view.png")

                if card_t == "character":
                    if char_idx == 0:
                        physical_anchors["middle"] = path_str
                    else:
                        physical_anchors[f"supporting_character_{char_idx}"] = path_str
                    char_idx += 1
                elif card_t == "scene":
                    if scene_idx == 0:
                        physical_anchors["supporting_scene"] = path_str
                    else:
                        physical_anchors[f"supporting_scene_{scene_idx}"] = path_str
                    scene_idx += 1
                elif card_t == "prop":
                    if prop_idx == 0:
                        physical_anchors["supporting_prop"] = path_str
                    else:
                        physical_anchors[f"supporting_prop_{prop_idx}"] = path_str
                    prop_idx += 1
            story_data = {
                "metadata": {
                    "topic": topic,
                    "project_name": topic,
                    "era": "",  # 改为空白，防止硬编码“霓虹雨夜”污染用户自建频道的定制风格
                    "duration": 1.0,
                    "run_id": run_id,
                    "story_source": "user_script"
                },
                "master_design": {
                    "full_narration": GLOBAL_STATE["compiled_voiceover"],
                    "cast_registry": {
                        "protagonist": {
                            "display_name_en": "Protagonist",
                            "stages": ["middle"],
                            "stage_prompts": {}
                        },
                        "supporting": []
                    },
                    "physical_char_anchors": physical_anchors
                }
            }
            with open(full_story_path, "w", encoding="utf-8") as f:
                json.dump(story_data, f, ensure_ascii=False, indent=2)

            print("[Bridge] ✅ 定妆照渲染与剧本锚点回写成功！")
            GLOBAL_STATE["active_stage"] = ""
            return {"status": "success", "assets": assets_res}

        except Exception as e:
            GLOBAL_STATE["active_stage"] = ""
            import traceback
            print(f"❌ [Bridge] 定妆资产渲染失败: {traceback.format_exc()}")
            return {"status": "error", "detail": f"定妆资产渲染失败: {str(e)}"}

    # ──────────────────────────────────────────────
    # 🎞️ 分镜生成  替代 POST /api/story/v1/generate-storyboard
    # ──────────────────────────────────────────────
    def generate_storyboard(self):
        run_id = GLOBAL_STATE.get("current_run_id", "")
        if not run_id:
            return {"status": "error", "detail": "未检测到活跃 of Run-ID。"}

        print(f"\n[Bridge] 为批次 {run_id} 启动分镜插值与 16 宫格大图生成...")

        def _push(stage, pct, msg):
            if GLOBAL_WINDOW:
                safe_msg = msg.replace("'", "\\'")
                GLOBAL_WINDOW.evaluate_js(
                    f"onBackendProgress('{stage}', {pct}, '{safe_msg}')"
                )

        try:
            GLOBAL_STATE["active_stage"] = "002-旁白"
            _push("phase2", 20, "[第1步] Phase 2 旁白配音与时间轴微切...")

            env = dict(os.environ)
            env["STORYBOARD_PROMPT_TEMPLATE"] = GLOBAL_STATE.get("storyboard_prompt", "")
            proc2 = subprocess.run(
                [sys.executable, "-m", "src.step1_writer_v6", "--phase", "phase2"],
                cwd=BASE_DIR, capture_output=True, encoding="utf-8", env=env
            )
            if proc2.returncode != 0:
                GLOBAL_STATE["active_stage"] = ""
                print(f"❌ [Phase2]: {proc2.stderr[-800:]}")
                return {"status": "error", "detail": f"旁白时间轴切分失败:\n{proc2.stderr[-400:]}"}

            GLOBAL_STATE["active_stage"] = "005-分镜与画面"
            _push("phase3", 45, "[第2步] Phase 3 实体提炼与分镜插值...")

            proc3 = subprocess.run(
                [sys.executable, "-m", "src.step1_writer_v6", "--phase", "phase3"],
                cwd=BASE_DIR, capture_output=True, encoding="utf-8", env=env
            )
            if proc3.returncode != 0:
                GLOBAL_STATE["active_stage"] = ""
                print(f"❌ [Phase3]: {proc3.stderr[-800:]}")
                return {"status": "error", "detail": f"分镜插值失败:\n{proc3.stderr[-400:]}"}

            GLOBAL_STATE["active_stage"] = "006-宫格生图"
            _push("step2", 70, "[第3步] Step 2 正在绘制全部 16 宫格分镜大图...")

            env["GRID_SKIP_LAYOUT_VALIDATE"] = "1"
            proc_s2 = subprocess.run(
                [sys.executable, "-m", "src.step2_comic_generator_v6", "--phase", "grid-only"],
                cwd=BASE_DIR, capture_output=True, encoding="utf-8", env=env
            )
            if proc_s2.returncode != 0:
                GLOBAL_STATE["active_stage"] = ""
                print(f"❌ [Step2]: {proc_s2.stderr[-800:]}")
                return {"status": "error", "detail": f"分镜生图失败:\n{proc_s2.stderr[-400:]}"}

            _push("step2", 95, "[第4步] 读取分镜大宫格图集...")

            # 读取分镜大底片
            paths = get_paths()
            final_json_path = paths["scripts_dir"] / "narrative_v6_final.json"
            grids_res = []

            if final_json_path.exists():
                with open(final_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                timeline = data.get("timeline") or data.get("shots") or []
                total_shots = len(timeline)
                
                # Chunk list by 16:
                batches = [timeline[i:i + 16] for i in range(0, len(timeline), 16)]
                
                for idx, batch_shots in enumerate(batches):
                    batch_index = idx + 1
                    batch_start = (batch_index - 1) * 16 + 1
                    batch_end = min(batch_start + len(batch_shots) - 1, total_shots)
                    
                    grid_filename = f"grid_batch_{batch_index:03d}.png"
                    grid_file = paths["storyboards_dir"] / grid_filename
                    img_url = _to_relative_url(grid_file) if grid_file.exists() else ""
                    
                    prompt_lines = []
                    for shot_idx, shot in enumerate(batch_shots, start=batch_start):
                        prompt_lines.append(f"F-{shot_idx:02d}: {shot.get('visual_prompt', '')}")
                    prompt_str = "\n".join(prompt_lines)
                    
                    grids_res.append({
                        "id": f"grid_batch_{batch_index:03d}",
                        "batch_index": batch_index,
                        "image_url": img_url,
                        "range_text": f"分镜 F-{batch_start:02d} ~ F-{batch_end:02d}",
                        "prompt": prompt_str
                    })

            print("[Bridge] ✅ 16 宫格大图生成完毕！")
            GLOBAL_STATE["active_stage"] = ""
            return {"status": "success", "grids": grids_res}

        except Exception as e:
            GLOBAL_STATE["active_stage"] = ""
            import traceback
            print(f"❌ [Bridge] 分镜大图生成失败: {traceback.format_exc()}")
            return {"status": "error", "detail": f"分镜大图生成失败: {str(e)}"}

    # ──────────────────────────────────────────────
    # 🔄 批次打回重绘
    # ──────────────────────────────────────────────
    def regenerate_single_batch(self, payload):
        run_id = GLOBAL_STATE.get("current_run_id", "")
        if not run_id:
            return {"status": "error", "detail": "未检测到活跃的 Run-ID。"}
        
        batch_index = int(payload.get("batch_index", 1))
        prompts_str = payload.get("prompts", "")
        print(f"\n[Bridge] 收到第 {batch_index} 批次分镜重画请求...")
        
        try:
            # 解析 textarea 的 prompts_str 并更新到 narrative_v6_final.json
            import re
            prompts_map = {}
            for line in prompts_str.split("\n"):
                line = line.strip()
                if not line:
                    continue
                m = re.match(r"^F[-_](\d+)\s*:\s*(.*)$", line, re.IGNORECASE)
                if m:
                    shot_idx = int(m.group(1))
                    new_prompt = m.group(2).strip()
                    prompts_map[shot_idx] = new_prompt
            
            paths = get_paths()
            final_json_path = paths["scripts_dir"] / "narrative_v6_final.json"
            if final_json_path.exists():
                with open(final_json_path, "r", encoding="utf-8") as f:
                    narrative_data = json.load(f)
                
                timeline = narrative_data.get("timeline") or narrative_data.get("shots") or []
                for shot_idx, new_prompt in prompts_map.items():
                    idx_0 = shot_idx - 1
                    if 0 <= idx_0 < len(timeline):
                        timeline[idx_0]["visual_prompt"] = new_prompt
                
                with open(final_json_path, "w", encoding="utf-8") as f:
                    json.dump(narrative_data, f, ensure_ascii=False, indent=2)
            
            # 调用 step2_comic_generator_v6 进行单批次重画
            env = dict(os.environ)
            env["STORYBOARD_PROMPT_TEMPLATE"] = GLOBAL_STATE.get("storyboard_prompt", "")
            env["GRID_SKIP_LAYOUT_VALIDATE"] = "1"
            proc_s2 = subprocess.run(
                [sys.executable, "-m", "src.step2_comic_generator_v6", "--single-batch", str(batch_index)],
                cwd=BASE_DIR, capture_output=True, encoding="utf-8", env=env
            )
            if proc_s2.returncode != 0:
                print(f"❌ [Step2-Regen]: {proc_s2.stderr[-800:]}")
                return {"status": "error", "detail": f"重画分镜失败:\n{proc_s2.stderr[-400:]}"}
            
            # 读取更新后的数据返回
            with open(final_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            timeline = data.get("timeline") or data.get("shots") or []
            total_shots = len(timeline)
            
            batch_start = (batch_index - 1) * 16 + 1
            batch_shots = timeline[batch_start - 1 : batch_start - 1 + 16]
            batch_end = min(batch_start + len(batch_shots) - 1, total_shots)
            
            grid_filename = f"grid_batch_{batch_index:03d}.png"
            grid_file = paths["storyboards_dir"] / grid_filename
            img_url = _to_relative_url(grid_file) if grid_file.exists() else ""
            
            prompt_lines = []
            for shot_idx, shot in enumerate(batch_shots, start=batch_start):
                prompt_lines.append(f"F-{shot_idx:02d}: {shot.get('visual_prompt', '')}")
            prompt_str = "\n".join(prompt_lines)
            
            return {
                "status": "success",
                "grid": {
                    "id": f"grid_batch_{batch_index:03d}",
                    "batch_index": batch_index,
                    "image_url": img_url + f"?t={int(time.time())}",
                    "range_text": f"分镜 F-{batch_start:02d} ~ F-{batch_end:02d}",
                    "prompt": prompt_str
                }
            }
            
        except Exception as e:
            import traceback
            print(f"❌ [Bridge] 重画分镜发生异常: {traceback.format_exc()}")
            return {"status": "error", "detail": f"重画分镜发生异常: {str(e)}"}

    # ──────────────────────────────────────────────
    # 🎬 视频合成  替代 POST /api/story/v1/synthesize
    # ──────────────────────────────────────────────
    def synthesize_video(self):
        run_id = GLOBAL_STATE.get("current_run_id", "")
        if not run_id:
            return {"status": "error", "detail": "未检测到活跃的 Run-ID。"}

        print(f"\n[Bridge] 呼唤 FFmpeg 拼装大师，开启批次 {run_id} 全盘合成...")

        def _push(pct, msg):
            if GLOBAL_WINDOW:
                safe_msg = msg.replace("'", "\\'")
                GLOBAL_WINDOW.evaluate_js(
                    f"onBackendProgress('synthesis', {pct}, '{safe_msg}')"
                )

        try:
            GLOBAL_STATE["active_stage"] = "007-组装成片"
            _push(5, "[第1步/共2步] 正在对分镜大宫格执行自动裁切与超分高清...")

            # 先调用 step2 slice-only 裁切并高清
            env = dict(os.environ)
            proc_slice = subprocess.run(
                [sys.executable, "-m", "src.step2_comic_generator_v6", "--phase", "slice-only"],
                cwd=BASE_DIR, capture_output=True, encoding="utf-8", env=env
            )
            if proc_slice.returncode != 0:
                GLOBAL_STATE["active_stage"] = ""
                print(f"❌ [Step2 Slice]: {proc_slice.stderr[-800:]}")
                return {"status": "error", "detail": f"分镜裁切高清失败:\n{proc_slice.stderr[-400:]}"}

            _push(50, "[第2步/共2步] 正在启动 FFmpeg 拼装大师进行视频和旁白合成...")

            proc = subprocess.run(
                [sys.executable, "-m", "src.step3_assembler_v6"],
                cwd=BASE_DIR, capture_output=True, encoding="utf-8", env=env
            )
            if proc.returncode != 0:
                GLOBAL_STATE["active_stage"] = ""
                print(f"❌ [FFmpeg]: {proc.stderr[-800:]}")
                return {"status": "error", "detail": f"视频合成失败:\n{proc.stderr[-400:]}"}

            paths = get_paths()
            epic_mp4 = paths["output_dir"] / "narrative_v6_final_epic.mp4"
            if not epic_mp4.exists():
                GLOBAL_STATE["active_stage"] = ""
                return {"status": "error", "detail": "合成器完成，但未找到最终视频文件。"}

            # 返回相对路径（配合 http_server=True）
            video_url = _to_relative_url(epic_mp4)
            relative_path = f"{run_id}/output/narrative_v6_final_epic.mp4"

            _push(100, "🎬 全盘合成大获成功！")
            print(f"[Bridge] 🎬 合成成功！视频: {epic_mp4}")
            GLOBAL_STATE["active_stage"] = ""
            return {
                "status": "success",
                "video_url": video_url,
                "relative_path": relative_path
            }

        except Exception as e:
            GLOBAL_STATE["active_stage"] = ""
            import traceback
            print(f"❌ [Bridge] 视频合成失败: {traceback.format_exc()}")
            return {"status": "error", "detail": f"视频合成失败: {str(e)}"}

    # ──────────────────────────────────────────────
    # 🖌️ 单帧重绘  替代 POST /api/render/v1/single-frame
    # ──────────────────────────────────────────────
    def render_single_frame(self, payload):
        run_id = GLOBAL_STATE.get("current_run_id", "")
        if not run_id:
            return {"status": "error", "detail": "未检测到活跃的 Run-ID。"}

        try:
            target_id = payload.get("target_id", "")
            prompt = payload.get("prompt", "")
            seed = payload.get("seed", 40984180)

            print(f"\n[Bridge] 单帧重绘请求。目标: {target_id}")
            paths = get_paths()

            if target_id.startswith("cast_"):
                # 定妆卡重绘
                out_dir = paths["refs_dir"] / target_id
                out_dir.mkdir(parents=True, exist_ok=True)

                # 动态映射属性：根据当前激活频道的 assets_config 获取该卡片的物理分类。
                mode_path = GLOBAL_STATE.get("mode_path", "RED")
                assets_config = _get_channel_assets_config(mode_path)
                try:
                    idx = int(target_id.split("_")[-1]) - 1
                    t = assets_config[idx]["type"] if idx < len(assets_config) else "character"
                except Exception:
                    t = "character"
                img_file = out_dir / "triple_view.png"

                if t in ("scene", "prop"):
                    global_style_prompt = GLOBAL_STATE.get("style_presets", "cinematic realism, commercial grading, 35mm photograph")
                    if t == "scene":
                        lines = [
                            "A flat 2D vector style minimalist cartoon background scenery, WIDE ANGLE CINEMATIC BACKGROUND, No characters, no people.",
                            "Lighting: flat even cartoon lighting—no dramatic cast shadows, rim light, or studio volumetrics.",
                            f"Style (summary): {global_style_prompt}",
                            f"Scenery Details: {prompt}"
                        ]
                    else:
                        lines = [
                            "A flat 2D vector icon cartoon object on a flat pure white #FFFFFF background only—no floor, horizon, or environment.",
                            "Lighting: flat even cartoon lighting—no dramatic cast shadows, rim light, or studio volumetrics.",
                            f"Style (summary): {global_style_prompt}",
                            f"Object Details: {prompt}"
                        ]
                    full_prompt = "\n".join(lines)
                    
                    from src.api_audit import PHASE_CASTING
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        img_bytes = loop.run_until_complete(_gen_img(
                            prompt=full_prompt,
                            size="2k",
                            standalone_prompt=True,
                            audit_phase=PHASE_CASTING,
                            audit_step=f"triple_view/{target_id}"
                        ))
                        if img_bytes:
                            img_file.write_bytes(img_bytes)
                            try:
                                from src.project_vault import backup as vault_backup
                                rel = str(img_file.relative_to(BASE_DIR)).replace("\\", "/")
                                vault_backup(img_file, rel)
                            except Exception:
                                pass
                    finally:
                        loop.close()
                        asyncio.set_event_loop(None)
                else:
                    # character character character
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(generate_ref_sheet_at(
                            out_dir=out_dir,
                            english_prompt=prompt,
                            ref_image_path=None
                        ))
                    finally:
                        loop.close()
                        asyncio.set_event_loop(None)

                img_url = _to_relative_url(img_file) + f"?t={int(time.time())}" \
                    if img_file.exists() else ""
                svg_type = t
                return {"status": "success", "render_url": img_url, "svgType": svg_type}

            else:
                # 分镜单帧重绘
                frame_idx = 0
                try:
                    frame_idx = int(target_id.split("_")[-1]) - 1
                except Exception:
                    pass

                # 更新 narrative_v6_final.json 中该帧的 prompt
                final_json_path = paths["scripts_dir"] / "narrative_v6_final.json"
                if final_json_path.exists():
                    with open(final_json_path, "r", encoding="utf-8") as f:
                        narrative_data = json.load(f)
                    shots = narrative_data.get("shots", [])
                    if frame_idx < len(shots):
                        shots[frame_idx]["visual_prompt"] = prompt
                        with open(final_json_path, "w", encoding="utf-8") as f:
                            json.dump(narrative_data, f, ensure_ascii=False, indent=2)

                # 调用生图引擎
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    img_bytes = loop.run_until_complete(_gen_img(
                        prompt=prompt,
                        size="1080p",
                        standalone_prompt=True
                    ))
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)

                frame_filename = f"S_00{frame_idx + 1}.png"
                storyboard_path = paths["storyboards_dir"] / frame_filename
                if img_bytes:
                    storyboard_path.write_bytes(img_bytes)

                img_url = _to_relative_url(storyboard_path) + f"?t={int(time.time())}" \
                    if storyboard_path.exists() else ""
                return {"status": "success", "render_url": img_url, "svgType": "storyboard"}

        except Exception as e:
            import traceback
            print(f"❌ [Bridge] 单帧重绘失败: {traceback.format_exc()}")
            return {"status": "error", "detail": f"单帧重绘失败: {str(e)}"}

    # ──────────────────────────────────────────────
    # 💾 另存为对话框 (子进程 STA 独占高自愈通道，100% 免疫 COM 线程冲突)
    # ──────────────────────────────────────────────
    def select_save_path(self, default_filename="my_epic_story.mp4"):
        """唤起 Windows 原生"另存为"保存对话框 (子进程 STA 通道)"""
        print("[Bridge] 正在唤起 Windows 原生'另存为'保存文件对话框 (安全子进程)...")
        try:
            import subprocess
            import sys
            
            code = f"""
import tkinter as tk
from tkinter import filedialog
import sys

try:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    
    file_path = filedialog.asksaveasfilename(
        initialfile={repr(default_filename)},
        defaultextension=".mp4",
        filetypes=[("MP4 视频文件", "*.mp4"), ("所有文件", "*.*")]
    )
    if file_path:
        print(file_path.strip())
except Exception as e:
    sys.exit(1)
"""
            res = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                encoding="utf-8"
            )
            if res.returncode == 0:
                file_path = res.stdout.strip()
                print(f"[Bridge] 安全子进程选定保存路径: {file_path}")
                return file_path
            else:
                print(f"❌ [Bridge] 安全子进程对话框运行失败: {res.stderr}")
        except Exception as err:
            print(f"❌ [Bridge] 唤起安全子进程另存为对话框失败: {err}")
            
        # 👑 备用兜底 pywebview 对话框通道
        try:
            global GLOBAL_WINDOW
            if GLOBAL_WINDOW:
                file_path = GLOBAL_WINDOW.create_file_dialog(
                    webview.SAVE_DIALOG,
                    directory="",
                    save_filename=default_filename,
                    file_types=("MP4 视频文件 (*.mp4)", "所有文件 (*.*)")
                )
                print(f"[Bridge] 备用 pywebview 选定保存路径: {file_path}")
                return file_path or ""
        except Exception as pyw_err:
            print(f"❌ [Bridge] 所有的另存为对话框通道均已失效: {pyw_err}")
        return ""

    # ──────────────────────────────────────────────
    # ⚙️ 预设目录选择对话框 (子进程 STA 独占通道，100% 免疫 COM 线程冲突)
    # ──────────────────────────────────────────────
    def select_download_dir(self):
        """唤起 Windows 原生文件夹选择对话框，预设默认下载目录 (安全子进程 STA 通道)"""
        print("[Bridge] 正在唤起 Windows 默认下载目录选择对话框 (安全子进程)...")
        try:
            import subprocess
            import sys
            
            code = """
import tkinter as tk
from tkinter import filedialog
import sys

try:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    
    dir_path = filedialog.askdirectory()
    if dir_path:
        print(dir_path.strip())
except Exception as e:
    sys.exit(1)
"""
            res = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                encoding="utf-8"
            )
            if res.returncode == 0:
                dir_path = res.stdout.strip()
                print(f"[Bridge] 安全子进程选定预设目录: {dir_path}")
                return dir_path
            else:
                print(f"❌ [Bridge] 安全子进程目录选择运行失败: {res.stderr}")
        except Exception as err:
            print(f"❌ [Bridge] 唤起安全子进程目录选择对话框失败: {err}")
        return ""

    # ──────────────────────────────────────────────
    # 📺 频道预设持久化  get_channels / save_channels
    # ──────────────────────────────────────────────
    def get_channels(self):
        """读取频道预设 JSON 文件（前端首次加载时调用）"""
        import json
        channels_file = os.path.join(BASE_DIR, "data", "channels_presets.json")
        try:
            if os.path.exists(channels_file):
                with open(channels_file, "r", encoding="utf-8") as f:
                    channels = json.load(f)
                print(f"[Bridge] 已从文件加载 {len(channels)} 个频道预设。")
                return {"status": "success", "channels": channels}
            else:
                print("[Bridge] 频道预设文件不存在，返回空列表（前端将使用默认频道）。")
                return {"status": "success", "channels": []}
        except Exception as err:
            print(f"❌ [Bridge] 读取频道预设失败: {err}")
            return {"status": "error", "detail": str(err), "channels": []}

    def save_channels(self, channels):
        """将频道预设列表写入 JSON 文件（作为 localStorage 的双轨备份）"""
        import json
        channels_file = os.path.join(BASE_DIR, "data", "channels_presets.json")
        try:
            os.makedirs(os.path.dirname(channels_file), exist_ok=True)
            with open(channels_file, "w", encoding="utf-8") as f:
                json.dump(channels, f, ensure_ascii=False, indent=2)
            print(f"[Bridge] 已保存 {len(channels)} 个频道预设到文件。")
            return {"status": "success"}
        except Exception as err:
            print(f"❌ [Bridge] 保存频道预设失败: {err}")
            return {"status": "error", "detail": str(err)}



    # ──────────────────────────────────────────────
    # 📥 文件拷贝下载  替代 POST /api/story/v1/download (自愈高适应目录与权限)
    # ──────────────────────────────────────────────
    def download_video(self, payload):
        try:
            source_relative = payload.get("source_file_relative_path", "")
            target_absolute = payload.get("target_absolute_path", "")

            runs_dir = BASE_DIR_PATH / "data" / "runs"
            source_abs = runs_dir / source_relative
            if not source_abs.exists():
                return {"status": "error", "detail": "未找到合成好的视频源文件。"}

            # 智能防错自愈处理：如果 target_absolute 是一个已存在的文件夹或以斜杠结尾，或者不包含后缀名
            import os
            target_path = Path(target_absolute)
            if target_path.is_dir() or target_absolute.endswith("/") or target_absolute.endswith("\\") or not target_path.suffix:
                os.makedirs(target_path, exist_ok=True)
                target_path = target_path / source_abs.name
            else:
                os.makedirs(target_path.parent, exist_ok=True)

            shutil.copy(str(source_abs), str(target_path))
            actual_path = str(target_path)
            print(f"🎉 [Bridge] 成功导出至: {actual_path}")
            return {
                "status": "success", 
                "msg": f"保存成功！视频已导出至 {actual_path}",
                "actual_path": actual_path
            }

        except Exception as e:
            print(f"❌ [Bridge] 文件导出失败: {e}")
            return {"status": "error", "detail": f"文件保存失败: {str(e)}"}


def main():
    print(f"[系统] 使用的 Python 解释器: {sys.executable}")

    try:
        bridge = DesktopApiBridge()
        html_path = os.path.join(BASE_DIR, "palette_studio.html")
        print(f"[系统] 正在装载前端文件: {html_path}")

        window = webview.create_window(
            title='"调色板" AI 电影级多大模型联调总控台',
            url=html_path,
            js_api=bridge,      # 绑定 JS Bridge
            width=1360,
            height=850,
            resizable=True,
            min_size=(1024, 700)
        )

        global GLOBAL_WINDOW
        GLOBAL_WINDOW = window

        print("[系统] 正在为您弹开独立软件窗口（JS Bridge 已就绪，无需 HTTP 服务器）...")
        # http_server=True：pywebview 内置 HTTP 服务器，托管 BASE_DIR 下的所有静态资源
        # 这样前端可以用相对路径（如 data/runs/.../image.png）直接访问本地图片/视频
        webview.start(debug=False, http_server=True)

    except Exception as e:
        import traceback
        print(f"❌ [系统] 运行发生致命错误: {traceback.format_exc()}")

    finally:
        print("[系统] 软件已完全退出。再见，导演！")


if __name__ == "__main__":
    main()
