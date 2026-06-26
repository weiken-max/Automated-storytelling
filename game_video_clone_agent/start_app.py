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
from src.ref_generator import generate_ref_sheet_at, _build_ref_display_slots
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
    ref_anchor_lower = str(config.REF_STYLE_ANCHOR or "").lower()
    is_cyanide_style = "cyanide" in ref_anchor_lower or "stickman" in ref_anchor_lower
    if is_cyanide_style:
        char_default = "Cyanide-and-Happiness web-comic character sheet: 2D vector, oversized round bean head, two dot eyes, arms and legs as pure black stick strokes (matchstick limbs, no realistic anatomy), simple torso block, bold outlines, flat fills, no shading or fabric micro-detail."
    else:
        char_default = "Clean 2D flat illustration representation of a character: orthographic sheet, primitive shapes, clear outlines, flat color fills."

    default_templates = {
        "character": char_default,
        "scene": "A flat 2D vector style minimalist cartoon background scenery. Flat shades, no character.",
        "prop": "A flat 2D vector icon cartoon object. Primitive shape, flat color fill, white background."
    }

    # 2. 从 custom_template 解析用户预设
    baseline_prompts = []
    for lbl, typ in zip(labels, types):
        tpl = default_templates.get(typ, default_templates["character"])
        if custom_template.strip():
            if "[" not in custom_template:
                # 智能识别：若预设中无括号，直接将其作为通用模板
                tpl = custom_template.strip()
            else:
                import re
                match_lbl = re.search(rf"\[{re.escape(lbl)}\](.*?)(\[|$)", custom_template, re.DOTALL | re.IGNORECASE)
                if match_lbl:
                    tpl = match_lbl.group(1).strip()
                else:
                    match_typ = re.search(rf"\[{re.escape(typ)}\](.*?)(\[|$)", custom_template, re.DOTALL | re.IGNORECASE)
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
        sys_prompt += f"- For element \"{lbl}\" (representing \"{ent}\"): Expand upon the baseline template: \"{tpl}\"\n"

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


def _stage_ch(st):
    mapping = {
        "child": "童年",
        "youth": "青年",
        "middle": "中年",
        "elderly": "老年"
    }
    return mapping.get(st, st)


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
    # ⚙️ 模型配置接口
    # ──────────────────────────────────────────────
    def get_model_settings(self):
        """
        获取当前模型配置（5卡插槽式，含厂商列表与模型历史）
        """
        try:
            from src.model_presets import (
                MODEL_LLM, MODEL_VLM, MODEL_VLM_ANALYZE, MODEL_IMG_CAST, MODEL_IMG_STORY,
                get_vendor_list, get_active_vendor_keys, get_model_history,
                VENDORS_PRESETS,
            )
            active_vendors = get_active_vendor_keys()
            vendors_list = get_vendor_list(active_vendor_keys=active_vendors)

            # 构建厂商字典（已过滤：只含已配key + 当前在用）
            vendors = {}
            for v in vendors_list:
                vendors[v["vendor_key"]] = v

            # 5 个模型插槽
            SLOT_DEFS = [
                {"key": "llm",         "name": "LLM 文本大模型",   "icon": "🧠",
                 "desc": "剧本润色 / 大纲生成 / Beat 切分"},
                {"key": "vlm",         "name": "VLM 分镜视觉",     "icon": "👁️",
                 "desc": "Phase3 看定妆照写分镜视觉提示词"},
                {"key": "vlm_analyze", "name": "VLM 识图分析",     "icon": "🔍",
                 "desc": "用户上传自定义定妆照后，VLM 识图并写提示词"},
                {"key": "img_cast",    "name": "定妆生图",         "icon": "🖼️",
                 "desc": "生成角色定妆照 / 场景道具底图"},
                {"key": "img_story",   "name": "分镜生图",         "icon": "🎬",
                 "desc": "生成 16 宫格漫画大图"},
            ]
            MODEL_MAP = {
                "llm": MODEL_LLM, "vlm": MODEL_VLM, "vlm_analyze": MODEL_VLM_ANALYZE,
                "img_cast": MODEL_IMG_CAST, "img_story": MODEL_IMG_STORY,
            }

            slots = []
            for sd in SLOT_DEFS:
                vk = active_vendors.get(sd["key"], "")
                v_info = vendors.get(vk, {})
                # 从 VENDORS_PRESETS 获取真实 API Key（本地桌面 APP，安全可控）
                raw_cfg = VENDORS_PRESETS.get(vk, {})
                raw_key = raw_cfg.get("api_key", "")
                slots.append({
                    "key": sd["key"],
                    "name": sd["name"],
                    "icon": sd["icon"],
                    "desc": sd["desc"],
                    "vendor_key": vk,
                    "vendor_name": v_info.get("vendor_name", vk),
                    "base_url": v_info.get("base_url", ""),
                    "model": MODEL_MAP.get(sd["key"], ""),
                    "model_history": get_model_history(sd["key"]),
                    "masked_key": v_info.get("masked_key", ""),
                    "api_key": raw_key,  # 完整 key，前端显示
                })

            return {
                "status": "success",
                "data": {"slots": slots, "vendors": vendors}
            }
        except Exception as e:
            return {"status": "error", "detail": f"获取模型配置失败: {str(e)}"}

    def save_model_settings(self, settings):
        """
        保存模型配置到本地并就地热更新内存变量（合并保存，不覆盖供应商目录等其他字段）
        """
        try:
            settings_dir = BASE_DIR_PATH / "data"
            settings_dir.mkdir(parents=True, exist_ok=True)
            settings_file = settings_dir / "model_settings.json"

            # 合并已有设置，避免把 provider_overrides / custom_providers / active_vendors 等冲掉
            existing = {}
            if settings_file.exists():
                try:
                    existing = json.loads(settings_file.read_text(encoding="utf-8"))
                except Exception:
                    existing = {}
            if isinstance(settings, dict):
                existing.update(settings)

            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=4, ensure_ascii=False)

            settings = existing

            llm = settings.get("MODEL_LLM")
            vlm = settings.get("MODEL_VLM")
            img_cast = settings.get("MODEL_IMG_CAST")
            img_story = settings.get("MODEL_IMG_STORY")

            # 兼容性兜底
            if not img_cast:
                img_cast = settings.get("MODEL_IMG")
            if not img_story:
                img_story = settings.get("MODEL_IMG")
            img = img_story or img_cast

            import sys

            # 1. 更新 src.model_presets
            if "src.model_presets" in sys.modules:
                m = sys.modules["src.model_presets"]
                if llm: m.MODEL_LLM = llm
                if vlm: m.MODEL_VLM = vlm
                if img_cast: m.MODEL_IMG_CAST = img_cast
                if img_story: m.MODEL_IMG_STORY = img_story
                if img: m.MODEL_IMG = img
                if hasattr(m, "MODELS") and isinstance(m.MODELS, dict):
                    if llm: m.MODELS["llm"] = llm
                    if vlm: m.MODELS["vlm"] = vlm
                    if img: m.MODELS["img"] = img

            # 2. 更新 src.style_config
            if "src.style_config" in sys.modules:
                s = sys.modules["src.style_config"]
                if llm: s.MODEL_LLM = llm
                if vlm: s.MODEL_VLM = vlm
                if img: s.MODEL_IMG = img
                if img_cast: s.MODEL_IMG_CAST = img_cast
                if img_story: s.MODEL_IMG_STORY = img_story

            # 3. 更新 src.image_engine
            if "src.image_engine" in sys.modules:
                ie = sys.modules["src.image_engine"]
                if img: ie.MODEL_IMG = img
                if img_cast: ie.MODEL_IMG_CAST = img_cast
                if img_story: ie.MODEL_IMG_STORY = img_story

            # 4. 更新 src.step1_writer_v6
            if "src.step1_writer_v6" in sys.modules:
                sw = sys.modules["src.step1_writer_v6"]
                if llm:
                    sw.MODEL_LLM = llm
                    sw.MODEL_WRITER = llm

            # 5. 更新 src.story_planner_v6
            if "src.story_planner_v6" in sys.modules:
                sp = sys.modules["src.story_planner_v6"]
                if llm:
                    sp.MODEL_LLM = llm
                    sp.MODEL_WRITER = llm

            print(f"[Bridge] Saved split model settings: LLM={llm}, VLM={vlm}, IMG_CAST={img_cast}, IMG_STORY={img_story}")
            return {"status": "success", "msg": "模型配置已保存并生效"}
        except Exception as e:
            return {"status": "error", "detail": f"保存模型配置失败: {str(e)}"}

    # ──────────────────────────────────────────────
    # 🔄 厂商切换 + API Key 管理接口（扩展版）
    # ──────────────────────────────────────────────
    def save_vendor_settings(self, payload):
        """
        一体化保存：slots 结构
        payload = {
            "slots": {
                "llm": {"vendor_key": "deepseek_v4_pro", "api_key": "sk-...", "model": "deepseek-v4-pro"},
                "vlm": {"vendor_key": "volc_ark_vlm", "api_key": "api-key-...", "model": "348cb4e5-..."},
                "vlm_analyze": {...}, "img_cast": {...}, "img_story": {...}
            }
        }
        """
        try:
            from src.model_presets import (
                switch_vendor, VENDOR_ENV_KEY_MAP, VENDORS_PRESETS,
                BUILTIN_VENDOR_KEYS, save_provider as _save_provider,
                save_model_history as _save_hist,
            )
            slots = payload.get("slots", {})
            if not slots:
                return {"status": "error", "detail": "slots 数据为空"}

            # 1. 收集 API Keys：内置厂商写 .env，自定义/覆盖厂商持久化到 settings 目录
            api_keys = {}
            for slot_key, sc in slots.items():
                ak = sc.get("api_key", "").strip()
                vk = sc.get("vendor_key", "")
                if ak and vk:
                    api_keys[vk] = ak
            if api_keys:
                env_keys = {vk: k for vk, k in api_keys.items()
                            if vk in VENDOR_ENV_KEY_MAP}
                if env_keys:
                    self._write_api_keys_to_env(env_keys)
                for vk, new_key in api_keys.items():
                    if vk in VENDORS_PRESETS:
                        VENDORS_PRESETS[vk]["api_key"] = new_key
                    # 没有 .env 映射的厂商（含自定义）→ 持久化进供应商目录
                    if vk not in VENDOR_ENV_KEY_MAP:
                        try:
                            _save_provider({"vendor_key": vk, "api_key": new_key})
                        except Exception as pe:
                            print(f"[Bridge] ⚠️ 持久化 {vk} 的 Key 失败: {pe}")

            # 2. 切换各插槽的厂商
            active_vendors = {}
            for slot_key, sc in slots.items():
                vk = sc.get("vendor_key", "")
                if vk:
                    active_vendors[slot_key] = vk
                    try:
                        switch_vendor(slot_key, vk)
                    except Exception as ve:
                        print(f"[Bridge] ⚠️ 切换 {slot_key}→{vk} 失败: {ve}")

            # 2.5 持久化厂商绑定到 model_settings.json（重启后可恢复）
            self._save_active_vendors(active_vendors)

            # 3. 模型名覆盖并写入历史
            models = {}
            for slot_key, sc in slots.items():
                mn = sc.get("model", "").strip()
                if mn:
                    models[f"MODEL_{slot_key.upper()}"] = mn
                    _save_hist(slot_key, mn)
            if models:
                self._apply_model_overrides(models)

            # 4. 热更新
            self._hot_reload_all_modules()

            # 5. 返回最新快照
            from src.model_presets import (
                MODEL_LLM, MODEL_VLM, MODEL_VLM_ANALYZE, MODEL_IMG_CAST, MODEL_IMG_STORY,
                get_vendor_list, get_active_vendor_keys,
            )
            active = get_active_vendor_keys()
            vendors = {}
            for v in get_vendor_list(active_vendor_keys=active):
                vendors[v["vendor_key"]] = v

            result = {
                "MODEL_LLM": MODEL_LLM, "MODEL_VLM": MODEL_VLM,
                "MODEL_VLM_ANALYZE": MODEL_VLM_ANALYZE,
                "MODEL_IMG_CAST": MODEL_IMG_CAST, "MODEL_IMG_STORY": MODEL_IMG_STORY,
                "active_vendors": active, "vendors": vendors,
            }
            print(f"[Bridge] ✅ 厂商配置已保存")
            return {"status": "success", "msg": "配置已保存并热更新", "data": result}
        except Exception as e:
            import traceback
            print(f"❌ [Bridge] 保存厂商配置失败: {traceback.format_exc()}")
            return {"status": "error", "detail": f"保存失败: {str(e)}"}

    # ──────────────────────────────────────────────
    # 🏪 供应商目录 CRUD（商业版供应商管理面板）
    # ──────────────────────────────────────────────
    def list_providers(self):
        """返回完整供应商目录 + 当前各角色绑定，用于供应商管理面板。"""
        try:
            from src.model_presets import list_all_providers, get_active_vendor_keys
            return {
                "status": "success",
                "data": {
                    "providers": list_all_providers(),
                    "active_vendors": get_active_vendor_keys(),
                },
            }
        except Exception as e:
            return {"status": "error", "detail": f"获取供应商列表失败: {str(e)}"}

    def save_provider(self, cfg):
        """新增/更新供应商（内置走 overrides，自定义走 custom_providers）。"""
        try:
            from src.model_presets import save_provider as _save, list_all_providers
            res = _save(cfg or {})
            self._hot_reload_all_modules()
            return {"status": "success", "data": {
                "vendor_key": res["vendor_key"],
                "builtin": res["builtin"],
                "providers": list_all_providers(),
            }}
        except Exception as e:
            import traceback
            print(f"❌ [Bridge] 保存供应商失败: {traceback.format_exc()}")
            return {"status": "error", "detail": f"保存供应商失败: {str(e)}"}

    def delete_provider(self, vendor_key):
        """删除自定义供应商（内置不可删）。"""
        try:
            from src.model_presets import delete_provider as _del, list_all_providers
            _del(vendor_key)
            return {"status": "success", "data": {"providers": list_all_providers()}}
        except Exception as e:
            return {"status": "error", "detail": str(e)}

    def set_provider_enabled(self, vendor_key, enabled):
        """启用/禁用供应商。"""
        try:
            from src.model_presets import set_provider_enabled as _toggle, list_all_providers
            _toggle(vendor_key, enabled)
            return {"status": "success", "data": {"providers": list_all_providers()}}
        except Exception as e:
            return {"status": "error", "detail": str(e)}

    def test_provider_connection(self, cfg):
        """
        轻量连接测试：对 OpenAI 兼容供应商发 /models 或最小 chat 请求，验证 key+base_url 可用。
        cfg = {"base_url": ..., "api_key": ..., "api_format": ..., "model": ...(可选)}
        """
        cfg = cfg or {}
        base_url = (cfg.get("base_url") or "").strip().rstrip("/")
        api_key = (cfg.get("api_key") or "").strip()
        if not base_url:
            return {"status": "error", "detail": "Base URL 为空"}
        if not api_key:
            return {"status": "error", "detail": "API Key 为空"}
        try:
            import urllib.request
            import urllib.error
            # 优先探测 /models（OpenAI 兼容标准只读端点）
            url = base_url + "/models"
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            })
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    code = resp.getcode()
                    if 200 <= code < 300:
                        return {"status": "success", "msg": f"连接成功（HTTP {code}）"}
                    return {"status": "error", "detail": f"HTTP {code}"}
            except urllib.error.HTTPError as he:
                # 401/403 说明能连通但鉴权失败；404 说明端点不存在但服务可达
                if he.code in (401, 403):
                    return {"status": "error", "detail": f"鉴权失败（HTTP {he.code}），请检查 API Key"}
                if he.code == 404:
                    return {"status": "success", "msg": "服务可达（无 /models 端点，HTTP 404），Key 未验证"}
                return {"status": "error", "detail": f"HTTP {he.code}: {he.reason}"}
        except Exception as e:
            return {"status": "error", "detail": f"连接失败: {str(e)}"}

    def _write_api_keys_to_env(self, api_keys: dict):
        """
        将 API Key 写入 .env 文件（安全更新，不删除其他行）
        """
        from src.model_presets import VENDOR_ENV_KEY_MAP
        env_file = BASE_DIR_PATH / ".env"

        if not env_file.exists():
            print("[Bridge] ⚠️ .env 文件不存在，跳过 API Key 写入")
            return

        content = env_file.read_text(encoding="utf-8")
        lines = content.split("\n")

        for vendor_key, new_key in api_keys.items():
            env_var_name = VENDOR_ENV_KEY_MAP.get(vendor_key)
            if not env_var_name or not new_key:
                continue

            # 查找并更新现有行
            found = False
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith(f"{env_var_name}=") or stripped.startswith(f"{env_var_name} ="):
                    lines[i] = f"{env_var_name}={new_key}"
                    found = True
                    break
                elif stripped == f"{env_var_name}":
                    # 下一行可能有 =
                    if i + 1 < len(lines) and lines[i + 1].strip().startswith("="):
                        lines[i + 1] = f"={new_key}"
                        found = True
                        break

            if not found:
                # 追加到末尾
                lines.append(f"{env_var_name}={new_key}")
                print(f"[Bridge] 📝 新增 {env_var_name} 到 .env")

        env_file.write_text("\n".join(lines), encoding="utf-8")
        print(f"[Bridge] ✅ API Keys 已写入 .env（{len(api_keys)} 个厂商）")

    def _save_active_vendors(self, active_vendors: dict):
        """将厂商绑定持久化到 model_settings.json"""
        settings_file = BASE_DIR_PATH / "data" / "model_settings.json"
        existing = {}
        if settings_file.exists():
            try:
                existing = json.loads(settings_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        existing["active_vendors"] = active_vendors
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=4, ensure_ascii=False)
        print(f"[Bridge] 💾 厂商绑定已持久化: {active_vendors}")

    def _apply_model_overrides(self, models: dict):
        """模型名覆盖：写入 model_settings.json + 热更新内存"""
        import sys
        settings_dir = BASE_DIR_PATH / "data"
        settings_dir.mkdir(parents=True, exist_ok=True)
        settings_file = settings_dir / "model_settings.json"

        # 合并已有设置
        existing = {}
        if settings_file.exists():
            try:
                existing = json.loads(settings_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        existing.update(models)

        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=4, ensure_ascii=False)

        # 热更新 model_presets 内存
        if "src.model_presets" in sys.modules:
            m = sys.modules["src.model_presets"]
            for k, v in models.items():
                if hasattr(m, k) and v:
                    setattr(m, k, v)

        print(f"[Bridge] 📝 模型名覆盖已应用: {models}")

    def _hot_reload_all_modules(self):
        """热更新所有已加载模块中的模型变量"""
        import sys
        from src.model_presets import (
            MODEL_LLM, MODEL_VLM, MODEL_VLM_ANALYZE, MODEL_IMG_CAST, MODEL_IMG_STORY, MODEL_IMG,
            LLM_API_KEY, LLM_BASE_URL, VLM_API_KEY, VLM_BASE_URL,
            IMG_API_KEY, IMG_BASE_URL,
        )

        # 1. src.style_config
        if "src.style_config" in sys.modules:
            s = sys.modules["src.style_config"]
            s.MODEL_LLM = MODEL_LLM
            s.MODEL_VLM = MODEL_VLM
            s.MODEL_VLM_ANALYZE = MODEL_VLM_ANALYZE
            s.MODEL_IMG = MODEL_IMG
            s.MODEL_IMG_CAST = MODEL_IMG_CAST
            s.MODEL_IMG_STORY = MODEL_IMG_STORY
            s.LLM_API_KEY = LLM_API_KEY
            s.LLM_BASE_URL = LLM_BASE_URL
            s.VLM_API_KEY = VLM_API_KEY
            s.VLM_BASE_URL = VLM_BASE_URL
            s.IMG_API_KEY = IMG_API_KEY
            s.IMG_BASE_URL = IMG_BASE_URL

        # 2. src.step1_writer_v6
        if "src.step1_writer_v6" in sys.modules:
            sw = sys.modules["src.step1_writer_v6"]
            sw.MODEL_LLM = MODEL_LLM
            sw.MODEL_WRITER = MODEL_LLM
            sw.MODEL_VLM = MODEL_VLM
            sw.LLM_API_KEY = LLM_API_KEY
            sw.LLM_BASE_URL = LLM_BASE_URL
            sw.VLM_API_KEY = VLM_API_KEY
            sw.VLM_BASE_URL = VLM_BASE_URL

        # 3. src.story_planner_v6
        if "src.story_planner_v6" in sys.modules:
            sp = sys.modules["src.story_planner_v6"]
            sp.MODEL_LLM = MODEL_LLM
            sp.MODEL_WRITER = MODEL_LLM
            sp.LLM_API_KEY = LLM_API_KEY
            sp.LLM_BASE_URL = LLM_BASE_URL

        # 4. src.image_engine
        if "src.image_engine" in sys.modules:
            ie = sys.modules["src.image_engine"]
            ie.MODEL_IMG = MODEL_IMG
            ie.MODEL_IMG_CAST = MODEL_IMG_CAST
            ie.MODEL_IMG_STORY = MODEL_IMG_STORY
            ie.IMG_API_KEY = IMG_API_KEY
            ie.IMG_BASE_URL = IMG_BASE_URL

        print("[Bridge] ✅ 所有模块热更新完成")

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
        has_assets = True

        recovered_assets_to_gen = None
        if full_story_path.exists():
            try:
                with open(full_story_path, "r", encoding="utf-8") as f:
                    fs_data = json.load(f)
                recovered_assets_to_gen = fs_data.get("metadata", {}).get("assets_to_generate")
            except Exception:
                pass

        if recovered_assets_to_gen:
            GLOBAL_STATE["assets_to_generate"] = recovered_assets_to_gen
            for idx, ast in enumerate(recovered_assets_to_gen):
                card_id = f"cast_0{idx + 1}"
                img_file = run_dir / "refs" / card_id / "triple_view.png"
                if img_file.exists():
                    img_url = _to_relative_url(img_file)
                    assets.append({
                        "id": card_id,
                        "name": ast.get("label", card_id),
                        "prompt": ast.get("english_prompt", ""),
                        "svgType": ast.get("type", "character"),
                        "image_url": img_url,
                        "custom_image_path": ast.get("custom_image_path")
                    })
                else:
                    has_assets = False
        else:
            assets_config = _get_channel_assets_config(mode_path)
            labels = [ast["label"] for ast in assets_config]
            types = [ast["type"] for ast in assets_config]
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
                                else:
                                    if t == "scene": scene_prompt = matched_prompt
                                    elif t == "prop": prop_prompt = matched_prompt
                            else:
                                typ_match = re.search(rf"\[{re.escape(t)}\](.*?)(\[|$)", cast_template, re.DOTALL | re.IGNORECASE)
                                if typ_match:
                                    matched_prompt = typ_match.group(1).strip()
                                    if t == "character": char_prompt = matched_prompt
                                    else:
                                        if t == "scene": scene_prompt = matched_prompt
                                        elif t == "prop": prop_prompt = matched_prompt

                        if t == "scene":
                            prompt = scene_prompt.replace("{entity}", ent).replace("{ent}", ent)
                        elif t == "prop":
                            prompt = prop_prompt.replace("{entity}", ent).replace("{ent}", ent)
                        else:
                            prompt = char_prompt.replace("{entity}", ent).replace("{ent}", ent)
                    else:
                        name_str = f"{label}"

                    ast_cfg = assets_config[idx] if idx < len(assets_config) else {}
                    assets.append({
                        "id": card_id,
                        "name": name_str,
                        "prompt": prompt,
                        "svgType": t,
                        "image_url": img_url,
                        "custom_image_path": ast_cfg.get("custom_image_path")
                    })
                else:
                    has_assets = False

        grids = []
        frames = []
        grid_mode = "4x4"  # 默认兜底，避免 narrative 不存在时 UnboundLocalError
        if narrative_path.exists():
            try:
                with open(narrative_path, "r", encoding="utf-8") as f:
                    narr_data = json.load(f)
                timeline = narr_data.get("timeline") or narr_data.get("shots") or []
                total_shots = len(timeline)

                # Reconstruct grids
                grid_mode = (narr_data.get("metadata") or {}).get("grid_mode", "4x4")
                if grid_mode == "2x2":
                    panels_count = 4
                elif grid_mode == "3x3":
                    panels_count = 9
                else:
                    panels_count = 16

                batches = [timeline[i:i + panels_count] for i in range(0, len(timeline), panels_count)]
                storyboards_dir = run_dir / "storyboards"
                for idx, batch_shots in enumerate(batches):
                    batch_index = idx + 1
                    batch_start = (batch_index - 1) * panels_count + 1
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
                    img_filename = f"S_{frame_num:03d}.png"
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
            "grid_mode": grid_mode,
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

            # 开启全新隔离批次或重用未完工的同文本批次
            topic = "director_cut_" + mode_path.lower()

            last_run_id = get_current_run_id()
            reuse_run = False
            RUNS_ROOT = BASE_DIR_PATH / "data" / "runs"
            if last_run_id:
                last_run_dir = RUNS_ROOT / last_run_id
                epic_mp4 = last_run_dir / "output" / "narrative_v6_final_epic.mp4"
                if last_run_dir.exists() and not epic_mp4.exists():
                    orig_text_file = last_run_dir / "scripts" / "original_text.txt"
                    if orig_text_file.exists():
                        try:
                            last_text = orig_text_file.read_text(encoding="utf-8").strip()
                            if last_text == original_text.strip():
                                reuse_run = True
                                run_dir = last_run_dir
                                run_id = last_run_id
                                print(f"[Bridge] 🌟 检测到输入文本与上次一致且未合成最终成片，自动重用当前批次目录: {run_id}")
                        except Exception:
                            pass

            if not reuse_run:
                run_dir = start_new_run(topic=topic)
                run_id = run_dir.name
                print(f"[Bridge] 🆕 开启全新隔离批次目录: {run_id}")
            else:
                # 显式覆盖 current_run.json 确保统一
                CURRENT_RUN_FILE = RUNS_ROOT / "current_run.json"
                CURRENT_RUN_FILE.write_text(json.dumps({"run_id": run_id}, ensure_ascii=False), encoding="utf-8")

            paths = get_paths(create_if_missing=True)
            scripts_dir = paths["scripts_dir"]

            try:
                (scripts_dir / "original_text.txt").write_text(original_text, encoding="utf-8")
            except Exception as e:
                print(f"[Bridge] ⚠️ 保存 original_text.txt 失败: {e}")

            GLOBAL_STATE["current_run_id"] = run_id
            GLOBAL_STATE["topic"] = topic
            GLOBAL_STATE["mode_path"] = mode_path
            GLOBAL_STATE["original_text"] = original_text
            GLOBAL_STATE["style_presets"] = render_flow.get("style_presets", "")
            GLOBAL_STATE["seed"] = render_flow.get("seed", 40984180)
            GLOBAL_STATE["polish_enabled"] = polish_flow.get("enabled", False)
            GLOBAL_STATE["tts_engine"] = voiceover_flow.get("engine", "edge")
            GLOBAL_STATE["tts_voice"] = voiceover_flow.get("voice_role", "")
            GLOBAL_STATE["tts_rate"] = voiceover_flow.get("voice_rate", "")
            GLOBAL_STATE["tts_emotion"] = voiceover_flow.get("voice_emotion", "")
            GLOBAL_STATE["tts_pitch"] = voiceover_flow.get("voice_pitch", 0)
            GLOBAL_STATE["tts_volume"] = voiceover_flow.get("voice_volume", 0)
            GLOBAL_STATE["tts_prompt"] = voiceover_flow.get("voice_prompt", "")
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

            # 检查是否为自定义资产配置频道
            is_custom_channel = False
            try:
                channels_file = os.path.join(BASE_DIR, "data", "channels_presets.json")
                if os.path.exists(channels_file):
                    with open(channels_file, "r", encoding="utf-8") as f:
                        channels = json.load(f)
                    for ch in channels:
                        if str(ch.get("id", "")).upper() == mode_path.upper():
                            if ch.get("channelType") == "custom":
                                is_custom_channel = True
                            break
            except Exception:
                pass

            assets_to_generate = []
            dynamic_cast_prompt = ""
            should_gen_cast = render_flow.get("should_gen_cast", False)
            assets_config = _get_channel_assets_config(mode_path)

            if should_gen_cast and entities and not is_custom_channel:
                from src.ref_generator import llm_plan_cast_from_synopsis
                print("[Bridge] 🧠 正在使用大模型规划多角色多时期定妆设计...")
                plan = llm_plan_cast_from_synopsis(topic, syn_result)
                if plan:
                    GLOBAL_STATE["cast_plan"] = plan
                    # 1. 主角阶段
                    pro = plan.get("protagonist", {})
                    pro_dn = pro.get("display_name_en", "Protagonist")
                    pro_stages = list(pro.get("stages", []))
                    if "middle" in pro_stages:
                        pro_stages.remove("middle")
                        pro_stages.insert(0, "middle")
                    for st in pro_stages:
                        stage_prompt = pro.get("stage_prompts", {}).get(st, {})
                        assets_to_generate.append({
                            "label": f"主角 ({_stage_ch(st)})",
                            "type": "character",
                            "role_id": "protagonist",
                            "stage": st,
                            "english_prompt": stage_prompt.get("english_prompt", ""),
                            "anchor_description": stage_prompt.get("anchor_description", ""),
                            "display_name_en": pro_dn
                        })
                    # 2. 配角阶段
                    for sup in plan.get("supporting", []):
                        rid = sup.get("role_id")
                        sup_dn = sup.get("display_name_en", rid)
                        sup_stages = list(sup.get("stages", []))
                        if "middle" in sup_stages:
                            sup_stages.remove("middle")
                            sup_stages.insert(0, "middle")
                        for st in sup_stages:
                            stage_prompt = sup.get("stage_prompts", {}).get(st, {})
                            assets_to_generate.append({
                                "label": f"配角: {sup_dn} ({_stage_ch(st)})",
                                "type": "character",
                                "role_id": rid,
                                "stage": st,
                                "english_prompt": stage_prompt.get("english_prompt", ""),
                                "anchor_description": stage_prompt.get("anchor_description", ""),
                                "display_name_en": sup_dn
                            })
                    # 3. 场景与道具
                    for idx, ast_cfg in enumerate(assets_config):
                        t = ast_cfg.get("type")
                        lbl = ast_cfg.get("label")
                        if t in ("scene", "prop") and idx < len(entities):
                            ent = entities[idx]
                            if t == "scene":
                                prompt = "A flat 2D vector style minimalist cartoon background scenery. Flat shades, no character."
                            else:
                                prompt = "A flat 2D vector icon cartoon object. Primitive shape, flat color fill, white background."
                            assets_to_generate.append({
                                "label": lbl,
                                "type": t,
                                "role_id": t,
                                "stage": None,
                                "english_prompt": prompt,
                                "anchor_description": f"{lbl}：{ent}",
                                "entity_text": ent
                            })

                    cast_prompt_parts = []
                    for ast in assets_to_generate:
                        lbl = ast["label"]
                        desc = ast["english_prompt"]
                        cast_prompt_parts.append(f"[{lbl}]\n{desc}")
                    dynamic_cast_prompt = "\n\n".join(cast_prompt_parts)
                    GLOBAL_STATE["cast_prompt"] = dynamic_cast_prompt
                else:
                    should_gen_cast = False

            if not should_gen_cast or not assets_to_generate or is_custom_channel:
                custom_tpl = GLOBAL_STATE.get("cast_prompt", "")
                dynamic_cast_prompt = _generate_cast_prompts_via_llm(topic, compiled_voiceover, entities, custom_template=custom_tpl)
                GLOBAL_STATE["cast_prompt"] = dynamic_cast_prompt

                # 双通道智能名字对齐
                matched_entities = {}
                unmatched_entities = list(entities)

                # 第一通道：完全名称对齐
                for idx, ast_cfg in enumerate(assets_config):
                    label = ast_cfg.get("label")
                    if label in unmatched_entities:
                        matched_entities[idx] = label
                        unmatched_entities.remove(label)

                # 第二通道：顺序兜底对齐
                for idx, ast_cfg in enumerate(assets_config):
                    if idx not in matched_entities:
                        if unmatched_entities:
                            matched_entities[idx] = unmatched_entities.pop(0)
                        else:
                            matched_entities[idx] = ast_cfg.get("label", f"Card_{idx+1}")

                char_idx = 0
                for idx, ast_cfg in enumerate(assets_config):
                    label = ast_cfg.get("label", f"Card_{idx+1}")
                    t = ast_cfg.get("type", "character")
                    ent = matched_entities.get(idx, label)

                    role_id = t
                    display_name_en = ent
                    if t == "character":
                        char_idx += 1
                        if char_idx == 1:
                            role_id = "protagonist"
                        else:
                            role_id = f"cast_{char_idx:02d}"

                    prompt = ""
                    if "[" in dynamic_cast_prompt:
                        import re
                        lbl_match = re.search(rf"\[{re.escape(label)}\](.*?)(\[|$)", dynamic_cast_prompt, re.DOTALL | re.IGNORECASE)
                        if lbl_match:
                            prompt = lbl_match.group(1).strip()
                    if not prompt:
                        prompt = dynamic_cast_prompt

                    assets_to_generate.append({
                        "label": label,
                        "type": t,
                        "role_id": role_id,
                        "stage": "middle" if t == "character" else None,
                        "english_prompt": prompt,
                        "anchor_description": f"{label}：{ent}",
                        "custom_image_path": ast_cfg.get("custom_image_path"),
                        "display_name_en": display_name_en
                    })

            GLOBAL_STATE["assets_to_generate"] = assets_to_generate

            print(f"[Bridge] ✅ 剧本编译成功！Run ID: {run_id}，实体: {entities}")
            GLOBAL_STATE["active_stage"] = ""
            return {
                "status": "success",
                "data": {
                    "compiled_voiceover": compiled_voiceover,
                    "extracted_entities": entities,
                    "cast_prompt": dynamic_cast_prompt,
                    "assets_to_generate": assets_to_generate
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

            # Get assets_to_generate from payload or GLOBAL_STATE or fallback
            assets_to_generate = payload.get("assets_to_generate") or GLOBAL_STATE.get("assets_to_generate")
            if not assets_to_generate:
                # Fallback to old behavior
                mode_path = GLOBAL_STATE.get("mode_path", "RED")
                assets_config = _get_channel_assets_config(mode_path)

                # 双通道智能名字对齐
                matched_entities = {}
                unmatched_entities = list(entities)

                # 第一通道：完全名称对齐
                for idx, ast_cfg in enumerate(assets_config):
                    label = ast_cfg.get("label")
                    if label in unmatched_entities:
                        matched_entities[idx] = label
                        unmatched_entities.remove(label)

                # 第二通道：顺序兜底对齐
                for idx, ast_cfg in enumerate(assets_config):
                    if idx not in matched_entities:
                        if unmatched_entities:
                            matched_entities[idx] = unmatched_entities.pop(0)
                        else:
                            matched_entities[idx] = ast_cfg.get("label", f"Card_{idx+1}")

                assets_to_generate = []
                char_idx = 0
                for idx, ast_cfg in enumerate(assets_config):
                    label = ast_cfg.get("label", f"Card_{idx+1}")
                    t = ast_cfg.get("type", "character")
                    ent = matched_entities.get(idx, label)
                    custom_image_path = ast_cfg.get("custom_image_path")

                    role_id = t
                    display_name_en = ent
                    if t == "character":
                        char_idx += 1
                        if char_idx == 1:
                            role_id = "protagonist"
                        else:
                            role_id = f"cast_{char_idx:02d}"

                    cast_template = GLOBAL_STATE.get("cast_prompt", "")
                    ref_anchor_lower = str(global_style_prompt or "").lower()
                    is_cyanide_style = "cyanide" in ref_anchor_lower or "stickman" in ref_anchor_lower
                    if is_cyanide_style:
                        char_prompt = "A cute cartoon stickman style representation of {entity}. Flat colors, strong outline, white background."
                    else:
                        char_prompt = "Clean 2D flat illustration representation of {entity}: orthographic sheet, primitive shapes, clear outlines, flat color fills."
                    scene_prompt = "A flat 2D vector style minimalist cartoon background scenery depicting {entity}. Flat shades, no character."
                    prop_prompt = "A flat 2D vector icon cartoon object depicting {entity}. Primitive shape, flat color fill, white background."

                    if cast_template.strip():
                        if "[" not in cast_template:
                            if t == "character": char_prompt = cast_template
                            elif t == "scene": scene_prompt = cast_template
                            elif t == "prop": prop_prompt = cast_template
                        else:
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

                    assets_to_generate.append({
                        "label": f"{label}：{ent}",
                        "type": t,
                        "role_id": role_id,
                        "stage": "middle" if t == "character" else None,
                        "english_prompt": prompt,
                        "anchor_description": f"{label}：{ent}",
                        "custom_image_path": custom_image_path,
                        "display_name_en": display_name_en
                    })

            # Save to GLOBAL_STATE to ensure consistency
            GLOBAL_STATE["assets_to_generate"] = assets_to_generate

            print(f"[Bridge] 待生成的资产卡片共 {len(assets_to_generate)} 张。")
            assets_res = []
            generated_char_refs = {}  # Map role_id -> Path of first generated image for consistency

            for idx, ast in enumerate(assets_to_generate):
                card_id = f"cast_0{idx + 1}"
                out_dir = refs_dir / card_id
                out_dir.mkdir(parents=True, exist_ok=True)

                t = ast.get("type", "character")
                role_id = ast.get("role_id")
                stage = ast.get("stage")
                prompt = ast.get("english_prompt", "")
                label = ast.get("label", card_id)
                custom_image_path = ast.get("custom_image_path")

                print(f"[Bridge] 正在渲染定妆卡片 {card_id} [{label}]...")

                img_file = out_dir / "triple_view.png"

                # 若已上传自定义定妆照，直接抓取物理文件进行拷贝，跳过 AI 生图
                if custom_image_path and (BASE_DIR_PATH / custom_image_path).exists():
                    import shutil
                    shutil.copy(str(BASE_DIR_PATH / custom_image_path), str(img_file))
                    try:
                        from src.project_vault import backup as vault_backup
                        rel = str(img_file.relative_to(BASE_DIR)).replace("\\", "/")
                        vault_backup(img_file, rel)
                    except Exception:
                        pass
                    print(f"  ✅ [Done] 已直接从本地复制用户定妆图并拷贝到: {img_file}")
                else:
                    if t in ("scene", "prop"):
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
                        # character character character
                        ref_image_path = generated_char_refs.get(role_id)

                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            loop.run_until_complete(generate_ref_sheet_at(
                                out_dir=out_dir,
                                english_prompt=prompt,
                                ref_image_path=ref_image_path
                            ))
                        finally:
                            loop.close()
                            asyncio.set_event_loop(None)

                        if img_file.exists() and role_id not in generated_char_refs:
                            generated_char_refs[role_id] = img_file

                img_url = _to_relative_url(img_file) + f"?t={int(time.time())}" \
                    if img_file.exists() else ""

                assets_res.append({
                    "id": card_id,
                    "name": label,
                    "prompt": prompt,
                    "svgType": t,
                    "image_url": img_url,
                    "custom_image_path": custom_image_path
                })

            # 回写 full_story_v6.json 锚点
            full_story_path = paths["scripts_dir"] / "full_story_v6.json"
            physical_anchors = {}

            protagonist_stages = []
            protagonist_prompts = {}
            supporting_map = {}

            scene_idx = 0
            prop_idx = 0

            for idx, ast in enumerate(assets_to_generate):
                card_id = f"cast_0{idx + 1}"
                path_str = str(refs_dir / card_id / "triple_view.png")

                card_t = ast.get("type", "character")
                role_id = ast.get("role_id")
                stage = ast.get("stage")
                prompt_str = ast.get("english_prompt", "")
                anchor_desc = ast.get("anchor_description") or prompt_str
                display_name_en = ast.get("display_name_en", role_id)

                if card_t == "character":
                    if role_id == "protagonist":
                        if stage not in protagonist_stages:
                            protagonist_stages.append(stage)
                        protagonist_prompts[stage] = {
                            "english_prompt": prompt_str,
                            "anchor_description": anchor_desc
                        }
                        physical_anchors[stage] = path_str
                    else:
                        sup_info = supporting_map.setdefault(role_id, {
                            "role_id": role_id,
                            "display_name_en": display_name_en,
                            "stages": [],
                            "stage_prompts": {}
                        })
                        if stage not in sup_info["stages"]:
                            sup_info["stages"].append(stage)
                        sup_info["stage_prompts"][stage] = {
                            "english_prompt": prompt_str,
                            "anchor_description": anchor_desc
                        }
                        physical_anchors[f"supporting_{role_id}_{stage}"] = path_str
                        if stage == "middle":
                            physical_anchors[f"supporting_{role_id}"] = path_str
                        elif f"supporting_{role_id}" not in physical_anchors:
                            physical_anchors[f"supporting_{role_id}"] = path_str
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

            supporting_list = list(supporting_map.values())
            supporting_registry = [{"role_id": k, "display_name_en": v["display_name_en"], "stages": v["stages"]} for k, v in supporting_map.items()]

            pro_dn = "Protagonist"
            for ast in assets_to_generate:
                if ast.get("type") == "character" and ast.get("role_id") == "protagonist":
                    pro_dn = ast.get("display_name_en", "Protagonist")
                    break

            cast_registry = {
                "protagonist": {
                    "display_name_en": pro_dn,
                    "stages": protagonist_stages or ["middle"],
                    "stage_prompts": protagonist_prompts
                },
                "supporting": supporting_registry
            }

            ref_display_slots = _build_ref_display_slots(cast_registry, physical_anchors)

            story_data = {
                "metadata": {
                    "topic": topic,
                    "project_name": topic,
                    "era": "",
                    "duration": 1.0,
                    "run_id": run_id,
                    "story_source": "user_script",
                    "tts_engine": GLOBAL_STATE.get("tts_engine", "edge"),
                    "tts_voice": GLOBAL_STATE.get("tts_voice", ""),
                    "tts_rate": GLOBAL_STATE.get("tts_rate", ""),
                    "tts_emotion": GLOBAL_STATE.get("tts_emotion", ""),
                    "assets_to_generate": assets_to_generate
                },
                "master_design": {
                    "full_narration": GLOBAL_STATE["compiled_voiceover"],
                    "cast_registry": cast_registry,
                    "physical_char_anchors": physical_anchors,
                    "ref_display_slots": ref_display_slots,
                    "detected_life_stages": protagonist_stages or ["middle"]
                }
            }

            stages = protagonist_stages or ["middle"]
            ordered = [s for s in stages if s in physical_anchors] or ["middle"]
            if len(ordered) == 1:
                story_data["master_design"]["stage_map"] = [{"stage": ordered[0], "start_shot": 1, "end_shot": 999999}]
            else:
                rough = []
                span = max(1, 999 // len(ordered))
                start = 1
                for idx, st in enumerate(ordered):
                    end = 999999 if idx == len(ordered) - 1 else (start + span - 1)
                    rough.append({"stage": st, "start_shot": start, "end_shot": end})
                    start = end + 1
                story_data["master_design"]["stage_map"] = rough

            with open(full_story_path, "w", encoding="utf-8") as f:
                json.dump(story_data, f, ensure_ascii=False, indent=2)

            refs_prompt_path = paths["scripts_dir"] / "refs-prompt.json"
            refs_prompt_data = {
                "schema_version": 1,
                "source": "api_server_custom",
                "topic": topic,
                "synopsis": None,
                "protagonist": {
                    "role_id": "protagonist",
                    "display_name_en": pro_dn,
                    "stages": protagonist_stages or ["middle"],
                    "stage_prompts": protagonist_prompts
                },
                "supporting": supporting_list
            }
            with open(refs_prompt_path, "w", encoding="utf-8") as f:
                json.dump(refs_prompt_data, f, ensure_ascii=False, indent=2)

            try:
                from src.project_vault import backup as vault_backup
                vault_backup(refs_prompt_path, "scripts/refs-prompt.json")
            except Exception:
                pass

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
    def generate_storyboard(self, payload=None):
        density = "medium"
        grid_mode = "4x4"
        if payload and isinstance(payload, dict):
            density = payload.get("density", "medium")
            grid_mode = payload.get("grid_mode", "4x4")

        run_id = GLOBAL_STATE.get("current_run_id", "")
        if not run_id:
            return {"status": "error", "detail": "未检测到活跃 of Run-ID。"}

        print(f"\n[Bridge] 为批次 {run_id} 启动分镜插值与 {grid_mode} 宫格大图生成...")

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
            env["STORYBOARD_DENSITY"] = density
            env["STORYBOARD_PROMPT_TEMPLATE"] = GLOBAL_STATE.get("storyboard_prompt", "")
            env["TTS_ENGINE"] = GLOBAL_STATE.get("tts_engine", "edge")
            env["TTS_VOICE"] = GLOBAL_STATE.get("tts_voice", "")
            env["TTS_RATE"] = GLOBAL_STATE.get("tts_rate", "")
            env["TTS_EMOTION"] = GLOBAL_STATE.get("tts_emotion", "")
            env["TTS_PITCH"] = str(GLOBAL_STATE.get("tts_pitch", 0))
            env["TTS_VOLUME"] = str(GLOBAL_STATE.get("tts_volume", 0))
            env["TTS_PROMPT"] = GLOBAL_STATE.get("tts_prompt", "")
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

            # 保存宫格设置到蓝图中
            paths = get_paths()
            final_json_path = paths["scripts_dir"] / "narrative_v6_final.json"
            if final_json_path.exists():
                with open(final_json_path, "r", encoding="utf-8") as f:
                    narr_data = json.load(f)
                if "metadata" not in narr_data:
                    narr_data["metadata"] = {}
                narr_data["metadata"]["grid_mode"] = grid_mode
                with open(final_json_path, "w", encoding="utf-8") as f:
                    json.dump(narr_data, f, ensure_ascii=False, indent=2)

            GLOBAL_STATE["active_stage"] = "006-宫格生图"
            _push("step2", 70, f"[第3步] Step 2 正在绘制全部 {grid_mode} 宫格分镜大图...")

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
            grids_res = []
            frames_res = []

            if final_json_path.exists():
                with open(final_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                timeline = data.get("timeline") or data.get("shots") or []
                total_shots = len(timeline)

                # Reconstruct sliced frames
                for idx, shot in enumerate(timeline):
                    frame_num = idx + 1
                    frame_id = f"frame_0{frame_num}"
                    img_filename = f"S_{frame_num:03d}.png"
                    img_file = paths["storyboards_dir"] / img_filename
                    img_url = _to_relative_url(img_file) if img_file.exists() else ""
                    frames_res.append({
                        "id": frame_id,
                        "text": shot.get("voiceover_text", "电影叙事中..."),
                        "prompt": shot.get("visual_prompt", "cinematic shot"),
                        "image_url": img_url,
                        "time_range": f"{shot.get('trigger_time', 0):.1f}s - {shot.get('trigger_time', 0) + 3.5:.1f}s"
                    })

                # Dynamic grid mode chunking:
                if grid_mode == "2x2":
                    panels_count = 4
                elif grid_mode == "3x3":
                    panels_count = 9
                else:
                    panels_count = 16

                batches = [timeline[i:i + panels_count] for i in range(0, len(timeline), panels_count)]

                for idx, batch_shots in enumerate(batches):
                    batch_index = idx + 1
                    batch_start = (batch_index - 1) * panels_count + 1
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

            print(f"[Bridge] ✅ {grid_mode} 宫格大图生成完毕！")
            GLOBAL_STATE["active_stage"] = ""
            return {"status": "success", "grids": grids_res, "frames": frames_res, "grid_mode": grid_mode}

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

                # Clear manually_redrawn and delete S_XXX.png files of this batch
                grid_mode = (narrative_data.get("metadata") or {}).get("grid_mode", "4x4")
                panels_count = 4 if grid_mode == "2x2" else (9 if grid_mode == "3x3" else 16)
                batch_start = (batch_index - 1) * panels_count
                batch_end = min(batch_start + panels_count, len(timeline))
                storyboards_dir = paths["storyboards_dir"]
                for idx_0 in range(batch_start, batch_end):
                    if "manually_redrawn" in timeline[idx_0]:
                        del timeline[idx_0]["manually_redrawn"]
                    # Delete S_XXX.png file if it exists
                    frame_num = idx_0 + 1
                    s_file = storyboards_dir / f"S_{frame_num:03d}.png"
                    if s_file.exists():
                        try:
                            s_file.unlink()
                        except Exception:
                            pass

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

            grid_mode = (data.get("metadata") or {}).get("grid_mode", "4x4")
            if grid_mode == "2x2":
                panels_count = 4
            elif grid_mode == "3x3":
                panels_count = 9
            else:
                panels_count = 16

            batch_start = (batch_index - 1) * panels_count + 1
            batch_shots = timeline[batch_start - 1 : batch_start - 1 + panels_count]
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
    def synthesize_video(self, payload=None):
        enable_speedup = True
        compile_type = "video"
        if payload and isinstance(payload, dict):
            enable_speedup = payload.get("enable_speedup", True)
            compile_type = payload.get("compile_type", "video")

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
            env["STEP3_POST_PLAYBACK_SPEED"] = "1.1" if enable_speedup else "1.0"
            env["COMPILE_TYPE"] = compile_type
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
                img_file = out_dir / "triple_view.png"

                # Parse the card index
                idx = int(target_id.split("_")[-1]) - 1

                # Load assets_to_generate
                assets_to_generate = []
                if GLOBAL_STATE.get("assets_to_generate"):
                    assets_to_generate = GLOBAL_STATE["assets_to_generate"]
                else:
                    # try loading from full_story_v6.json
                    full_story_path = paths["scripts_dir"] / "full_story_v6.json"
                    if full_story_path.exists():
                        try:
                            with open(full_story_path, "r", encoding="utf-8") as f:
                                fs_data = json.load(f)
                            assets_to_generate = fs_data.get("metadata", {}).get("assets_to_generate", [])
                            if assets_to_generate:
                                GLOBAL_STATE["assets_to_generate"] = assets_to_generate
                        except Exception:
                            pass

                t = "character"
                role_id = "protagonist"
                stage = "middle"
                display_name_en = "Protagonist"

                if assets_to_generate and idx < len(assets_to_generate):
                    ast = assets_to_generate[idx]
                    t = ast.get("type", "character")
                    role_id = ast.get("role_id")
                    stage = ast.get("stage")
                    display_name_en = ast.get("display_name_en", role_id)
                else:
                    # Legacy fallback
                    mode_path = GLOBAL_STATE.get("mode_path", "RED")
                    assets_config = _get_channel_assets_config(mode_path)
                    if idx < len(assets_config):
                        ast_cfg = assets_config[idx]
                        t = ast_cfg["type"]
                        label = ast_cfg.get("label", f"Card_{idx+1}")
                        if t == "character":
                            # Count how many characters precede or equal idx
                            char_idx = sum(1 for i in range(idx + 1) if assets_config[i]["type"] == "character")
                            if char_idx == 1:
                                role_id = "protagonist"
                            else:
                                role_id = f"cast_{char_idx:02d}"
                            stage = "middle"
                            entities = GLOBAL_STATE.get("extracted_entities", [])
                            display_name_en = entities[char_idx - 1] if char_idx - 1 < len(entities) else label
                        else:
                            role_id = t
                            stage = None
                            display_name_en = label
                    else:
                        t = "character"
                        role_id = "protagonist"
                        stage = "middle"
                        display_name_en = "Protagonist"

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
                    ref_image_path = None
                    if stage != "middle" and stage is not None and assets_to_generate:
                        mid_idx = None
                        for i, item in enumerate(assets_to_generate):
                            if item.get("role_id") == role_id and item.get("stage") == "middle":
                                mid_idx = i
                                break
                        if mid_idx is not None:
                            mid_card_id = f"cast_0{mid_idx + 1}"
                            mid_img = paths["refs_dir"] / mid_card_id / "triple_view.png"
                            if mid_img.exists():
                                ref_image_path = mid_img

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(generate_ref_sheet_at(
                            out_dir=out_dir,
                            english_prompt=prompt,
                            ref_image_path=ref_image_path
                        ))
                    finally:
                        loop.close()
                        asyncio.set_event_loop(None)

                # Update memory
                if assets_to_generate and idx < len(assets_to_generate):
                    GLOBAL_STATE["assets_to_generate"][idx]["english_prompt"] = prompt
                    GLOBAL_STATE["assets_to_generate"][idx]["anchor_description"] = prompt

                # 增量更新 full_story_v6.json 和 refs-prompt.json 的角色提示词
                try:
                    full_story_path = paths["scripts_dir"] / "full_story_v6.json"
                    refs_prompt_path = paths["scripts_dir"] / "refs-prompt.json"
                    topic = GLOBAL_STATE.get("topic", "my_epic_story")

                    # 1. 增量更新 full_story_v6.json
                    if full_story_path.exists():
                        with open(full_story_path, "r", encoding="utf-8") as f:
                            fs_data = json.load(f)

                        fs_data.setdefault("metadata", {})["assets_to_generate"] = GLOBAL_STATE.get("assets_to_generate", [])

                        md = fs_data.setdefault("master_design", {})
                        cr = md.setdefault("cast_registry", {})
                        physical_anchors = md.setdefault("physical_char_anchors", {})

                        if t == "character":
                            if role_id == "protagonist":
                                pro = cr.setdefault("protagonist", {})
                                pro["display_name_en"] = display_name_en
                                if stage not in pro.setdefault("stages", []):
                                    pro["stages"].append(stage)
                                sp = pro.setdefault("stage_prompts", {})
                                sp[stage] = {
                                    "english_prompt": prompt,
                                    "anchor_description": prompt
                                }
                            else:
                                sup_list = cr.setdefault("supporting", [])
                                found = False
                                for item in sup_list:
                                    if item.get("role_id") == role_id:
                                        item["display_name_en"] = display_name_en
                                        if stage not in item.setdefault("stages", []):
                                            item["stages"].append(stage)
                                        sp = item.setdefault("stage_prompts", {})
                                        sp[stage] = {
                                            "english_prompt": prompt,
                                            "anchor_description": prompt
                                        }
                                        found = True
                                        break
                                if not found:
                                    sup_list.append({
                                        "role_id": role_id,
                                        "display_name_en": display_name_en,
                                        "stages": [stage] if stage else [],
                                        "stage_prompts": {
                                            stage: {
                                                "english_prompt": prompt,
                                                "anchor_description": prompt
                                            }
                                        } if stage else {}
                                    })

                            md["ref_display_slots"] = _build_ref_display_slots(cr, physical_anchors)

                        with open(full_story_path, "w", encoding="utf-8") as f:
                            json.dump(fs_data, f, ensure_ascii=False, indent=2)

                    # 2. 增量更新 refs-prompt.json
                    if refs_prompt_path.exists():
                        with open(refs_prompt_path, "r", encoding="utf-8") as f:
                            rp_data = json.load(f)
                    else:
                        rp_data = {
                            "schema_version": 1,
                            "source": "api_server_custom",
                            "topic": topic,
                            "synopsis": None,
                            "protagonist": {
                                "role_id": "protagonist",
                                "display_name_en": "Protagonist",
                                "stages": ["middle"],
                                "stage_prompts": {}
                            },
                            "supporting": []
                        }

                    if t == "character":
                        if role_id == "protagonist":
                            rp_pro = rp_data.setdefault("protagonist", {})
                            rp_pro["display_name_en"] = display_name_en
                            if stage not in rp_pro.setdefault("stages", []):
                                rp_pro["stages"].append(stage)
                            rp_sp = rp_pro.setdefault("stage_prompts", {})
                            rp_sp[stage] = {
                                "english_prompt": prompt,
                                "anchor_description": prompt
                            }
                        else:
                            sup_list = rp_data.setdefault("supporting", [])
                            found = False
                            for item in sup_list:
                                if item.get("role_id") == role_id:
                                    item["display_name_en"] = display_name_en
                                    if stage not in item.setdefault("stages", []):
                                        item["stages"].append(stage)
                                    sp = item.setdefault("stage_prompts", {})
                                    sp[stage] = {
                                        "english_prompt": prompt,
                                        "anchor_description": prompt
                                    }
                                    found = True
                                    break
                            if not found:
                                sup_list.append({
                                    "role_id": role_id,
                                    "display_name_en": display_name_en,
                                    "stages": [stage] if stage else [],
                                    "stage_prompts": {
                                        stage: {
                                            "english_prompt": prompt,
                                            "anchor_description": prompt
                                        }
                                    } if stage else {}
                                })

                    with open(refs_prompt_path, "w", encoding="utf-8") as f:
                        json.dump(rp_data, f, ensure_ascii=False, indent=2)
                    try:
                        from src.project_vault import backup as vault_backup
                        vault_backup(refs_prompt_path, "scripts/refs-prompt.json")
                    except Exception:
                        pass
                except Exception as update_err:
                    print(f"⚠️ [Bridge] 更新剧本或定妆提示词文件失败: {update_err}")

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
                image_refs = []
                if final_json_path.exists():
                    with open(final_json_path, "r", encoding="utf-8") as f:
                        narrative_data = json.load(f)

                    timeline = narrative_data.get("timeline")
                    shots = narrative_data.get("shots")

                    target_shot = None
                    if timeline and frame_idx < len(timeline):
                        timeline[frame_idx]["visual_prompt"] = prompt
                        timeline[frame_idx]["manually_redrawn"] = True
                        target_shot = timeline[frame_idx]
                    if shots and frame_idx < len(shots):
                        shots[frame_idx]["visual_prompt"] = prompt
                        shots[frame_idx]["manually_redrawn"] = True
                        if not target_shot:
                            target_shot = shots[frame_idx]

                    with open(final_json_path, "w", encoding="utf-8") as f:
                        json.dump(narrative_data, f, ensure_ascii=False, indent=2)

                    if target_shot:
                        ref_image_paths = target_shot.get("ref_image_paths") or []
                        anchor_look = target_shot.get("anchor_look")
                        if isinstance(ref_image_paths, list):
                            for p in ref_image_paths:
                                if p and str(p).strip():
                                    image_refs.append(str(p).strip())
                        if anchor_look and str(anchor_look).strip() and str(anchor_look).strip() not in image_refs:
                            image_refs.append(str(anchor_look).strip())

                # Prep global style prefix
                global_style = GLOBAL_STATE.get("storyboard_prompt", "")
                full_prompt = f"Style: {global_style}\nDetail: {prompt}" if global_style else prompt

                # 调用生图引擎
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    img_bytes = loop.run_until_complete(_gen_img(
                        prompt=full_prompt,
                        image_refs=image_refs,
                        size="1280x720", # 16:9 ratio 1K resolution
                        standalone_prompt=True
                    ))
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)

                frame_filename = f"S_{frame_idx + 1:03d}.png"
                storyboard_path = paths["storyboards_dir"] / frame_filename
                if img_bytes:
                    storyboard_path.write_bytes(img_bytes)
                    # Run super-resolution Real-ESRGAN
                    try:
                        from src.image_processor import upscale_image
                        upscale_image(storyboard_path)
                    except Exception as upscale_err:
                        print(f"⚠️ [Bridge] 单分镜超分高清失败: {upscale_err}")

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
    # 📤 上传自定义资产图片 (支持多进程安全弹出 Tkinter 对话框)
    # ──────────────────────────────────────────────
    def select_custom_asset_image(self, payload):
        """拉起本地文件选择框选择定妆照，并复制到 data/custom_assets/ 目录下"""
        channel_id = payload.get("channel_id", "temp_channel")
        label = payload.get("label", "custom_asset")
        print(f"[Bridge] 正在唤起本地定妆照选择对话框 (channel={channel_id}, label={label})...")
        try:
            import subprocess
            import sys
            import shutil

            code = """
import tkinter as tk
from tkinter import filedialog
import sys

try:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    file_path = filedialog.askopenfilename(
        filetypes=[("图片文件", "*.png;*.jpg;*.jpeg;*.webp"), ("所有文件", "*.*")]
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
                src_path = res.stdout.strip()
                if not src_path:
                    print("[Bridge] 用户取消了文件选择。")
                    return {"status": "cancel"}

                # 创建目标路径
                import re
                safe_label = re.sub(r'[\\/*?:"<>|]', "_", label).strip()
                dest_dir = BASE_DIR_PATH / "data" / "custom_assets" / channel_id
                dest_dir.mkdir(parents=True, exist_ok=True)

                # 获取原文件后缀名
                suffix = Path(src_path).suffix or ".png"
                dest_file = dest_dir / f"{safe_label}{suffix}"

                # 复制图片
                shutil.copy(src_path, dest_file)
                rel_path = str(dest_file.relative_to(BASE_DIR_PATH)).replace("\\", "/")
                print(f"[Bridge] 成功复制自定义资产图片到: {rel_path}")

                return {"status": "success", "image_path": rel_path}
            else:
                print(f"❌ [Bridge] 安全子进程文件选择运行失败: {res.stderr}")
                return {"status": "error", "detail": "文件选择服务异常"}
        except Exception as err:
            print(f"❌ [Bridge] 唤起文件选择对话框失败: {err}")
            return {"status": "error", "detail": str(err)}

    # ──────────────────────────────────────────────
    # 🤖 智能识图描述 (使用 VLM Gemini Pro 生成英文 Prompt)
    # ──────────────────────────────────────────────
    def describe_custom_asset_image(self, payload):
        """调用 VLM 模型，根据上传的定妆照自动识图输出英文提示词描述"""
        import base64
        import json
        from openai import OpenAI
        from src.run_context import get_paths

        image_path = payload.get("image_path", "")
        asset_type = payload.get("type", "character")

        print(f"[Bridge] 正在调用 VLM 模型识别资产描述: image_path={image_path}, type={asset_type}")
        if not image_path:
            return {"status": "error", "detail": "图片路径为空"}

        full_img_path = BASE_DIR_PATH / image_path
        if not full_img_path.exists():
            return {"status": "error", "detail": "物理图片不存在"}

        try:
            # 读取图片并做 Base64 编码
            with open(full_img_path, "rb") as img_f:
                img_data = base64.b64encode(img_f.read()).decode("utf-8")

            # 根据类型，使用对应的 VLM 引导 Prompt
            if asset_type == "scene":
                vlm_prompt = (
                    "You are a master concept artist. Describe the background scene in this image extremely concisely. "
                    "Focus only on the most essential environment elements, colors, and layout. "
                    "Write a single extremely brief English description of 15-25 words (no bullet points, no markdown). "
                    "Describe it as a 2D flat minimalist background illustration. DO NOT mention any characters."
                )
            elif asset_type == "prop":
                vlm_prompt = (
                    "You are a flat vector icon designer. Describe the object/prop shown in this image extremely concisely. "
                    "Focus only on the core shape and primary colors. "
                    "Write a single extremely brief English description of 10-15 words (no bullet points, no markdown) describing "
                    "it as a 2D vector icon on a pure white background."
                )
            else:
                vlm_prompt = (
                    "You are a character concept designer. Describe the appearance of the character in this image extremely concisely. "
                    "Focus only on the most essential features: gender, hair color/style, and clothing type/color. "
                    "Write a single extremely brief English description of 15-20 words (no bullet points, no markdown). "
                    "Describe it as a 2D flat comic character. Keep it simple, iconic, and very short. "
                    "Do NOT include photorealism, CGI, or complex anatomy terms."
                )

            # 引入 VLM 配置（强制使用配置中的 VLM，如 Gemini Pro）
            from src.model_presets import MODEL_VLM, VLM_API_KEY, VLM_BASE_URL

            client = OpenAI(api_key=VLM_API_KEY, base_url=VLM_BASE_URL.rstrip("/"), timeout=60.0)

            # 使用 OpenAI 格式的 Vision 格式调用
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": vlm_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_data}"
                            }
                        }
                    ]
                }
            ]

            # 兼容性日志记录
            from src.api_audit import PHASE_CASTING, log_llm_chat

            response = log_llm_chat(
                PHASE_CASTING,
                "custom_asset_vlm_describe",
                MODEL_VLM,
                lambda: client.chat.completions.create(
                    model=MODEL_VLM,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=4096
                )
            )

            description = (response.choices[0].message.content or "").strip()
            print(f"[Bridge] VLM 识别描述成功: {description[:100]}...")
            return {"status": "success", "description": description}

        except Exception as e:
            import traceback
            print(f"❌ [Bridge] VLM 识别失败: {str(e)}")
            traceback.print_exc()
            return {"status": "error", "detail": f"VLM 识别失败: {str(e)}"}

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

    # ──────────────────────────────────────────────
    # 🎙️ 旁白音色试听合成（实时预览）
    # ──────────────────────────────────────────────
    def tts_preview(self, payload):
        """
        🎙️ 旁白音色试听生成接口
        """
        engine = payload.get("engine", "edge")
        voice = payload.get("voice", "")
        rate = payload.get("rate", "")
        emotion = payload.get("emotion", "none")
        pitch = int(payload.get("pitch", 0))
        volume = int(payload.get("volume", 0))
        prompt = payload.get("prompt", "")

        print(f"\n[Bridge] 正在生成试听音频: engine={engine}, voice={voice}, rate={rate}, emotion={emotion}, pitch={pitch}, volume={volume}, prompt={prompt}")

        try:
            preview_text = "您好！这是我当前的声音效果，如果您觉得满意，就选择我为您配音吧。"
            if engine == "volc" and emotion == "expressive":
                preview_text = "<cot text=温柔>您好！这是我当前的声音效果，如果您觉得满意，就选择我为您配音吧。</cot>"

            preview_dir = BASE_DIR_PATH / "previews"
            preview_dir.mkdir(parents=True, exist_ok=True)

            import hashlib
            config_hash = hashlib.md5(f"{engine}_{voice}_{rate}_{emotion}_{pitch}_{volume}_{prompt}".encode("utf-8")).hexdigest()
            filename = f"preview_{config_hash}.mp3"
            local_audio_path = preview_dir / filename

            if not local_audio_path.exists():
                if engine == "volc":
                    from src.step1_writer_v6 import _run_volc_tts_to_files
                    _run_volc_tts_to_files(
                        text=preview_text,
                        audio_path=local_audio_path,
                        voice=voice,
                        rate=rate,
                        emotion=emotion,
                        pitch=pitch,
                        volume=volume,
                        prompt=prompt
                    )
                else:
                    from src.step1_writer_v6 import _run_edge_tts_to_files
                    vtt_path = local_audio_path.with_suffix(".vtt")
                    _run_edge_tts_to_files(
                        text=preview_text,
                        audio_path=local_audio_path,
                        vtt_path=vtt_path,
                        voice=voice,
                        rate=rate
                    )
                    vtt_path.unlink(missing_ok=True)

            relative_url = _to_relative_url(local_audio_path)
            return {"status": "success", "audio_url": relative_url}
        except Exception as e:
            print(f"❌ [Bridge] 试听音频生成失败: {e}")
            return {"status": "error", "detail": f"试听音频生成失败: {str(e)}"}



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
