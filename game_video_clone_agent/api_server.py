# -*- coding: utf-8 -*-
"""
🔌 “调色板” AI 电影级中控服务 (api_server.py)
=========================================
- 基于 FastAPI 框架，专为 palette_studio.html 前台提供 API 绑定支持。
- 不改动您原有任何生成脚本，采用子进程与核心导入方式进行操作。
- 实现剧本润色 / 原稿绝对物理锁死直出。
- 无缝驱动 ref_generator, step1_writer_v6, step2_comic_generator_v6 和 step3_assembler_v6。
- 提供 Windows 系统 Save File Dialog 原生另存为物理拷贝下载。
"""

import os
import sys

# ── 🌐 强制指定全局终端流为 UTF-8 编码，彻底扫清 Windows 平台下任何子进程的 Emoji/中文字符 GBK 编码报错 ──
os.environ["PYTHONIOENCODING"] = "utf-8"

# ── 🔑 极速加载本地 .env 环境配置（确保第一秒读取中转站大模型 API KEY 与 Base URL） ──
try:
    from dotenv import load_dotenv
    # 从当前目录或上级目录自动识别加载 .env 变量
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(_env_path):
        load_dotenv(dotenv_path=_env_path)
        print(f"[API 中控] 成功由根目录加载本地 .env 配置: {_env_path}")
    else:
        load_dotenv()
        print("[API 中控] 未在根目录发现 .env，执行默认全局加载模式。")
except Exception as e:
    print(f"⚠️ [API 中控] 加载 .env 环境变量发生异常: {e}")

import json
import time
import shutil
import asyncio
import subprocess
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Any

# ── 保证能找到同级和上级目录 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# ── 导入本地核心运行模块 ──
import src.style_config as config
from src.run_context import start_new_run, get_paths, get_current_run_id
from src.ref_generator import run_ref_process, generate_ref_sheet_at, _build_ref_display_slots
import story_planner_v6 as planner

app = FastAPI(title="Palette Cinema API Server")

# ── 开启跨域，确保本地联调一路通畅 ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 全局状态缓存（记录当前批次的元数据） ──
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

# ── 如果 data 目录存在，托管 data/runs 目录供前端直连读取生成的图片/音频/视频 ──
RUNS_DIR = os.path.join(BASE_DIR, "data", "runs")
if os.path.exists(RUNS_DIR):
    app.mount("/static/runs", StaticFiles(directory=RUNS_DIR), name="runs")

# ── 统一托管前端素材 ──
app.mount("/static", StaticFiles(directory=BASE_DIR), name="static")


# ── Pydantic 请求模型定义 ──
class PolishFlow(BaseModel):
    enabled: bool
    system_prompt: str = ""
    immutable_lock: bool = True

class VoiceoverFlow(BaseModel):
    system_prompt: str = ""
    engine: str = "edge"
    voice_role: str = ""
    voice_rate: str = ""
    voice_emotion: str = ""
    voice_pitch: int = 0
    voice_volume: int = 0
    voice_prompt: str = ""

class RenderFlow(BaseModel):
    style_presets: str = ""
    seed: int = 40984180
    cast_prompt: str = ""
    storyboard_prompt: str = ""

class PipelineConfig(BaseModel):
    polish_flow: PolishFlow
    voiceover_flow: VoiceoverFlow
    render_flow: RenderFlow

class StoryCompileRequest(BaseModel):
    app_id: str = "palette-cinema-id"
    mode_path: str = "RED"  # RED=剧本, YELLOW=科普, BLUE=随机
    original_text: str
    pipeline_config: PipelineConfig

class AssetGenerateRequest(BaseModel):
    entities: List[str]
    global_style_prompt: str
    seed: int
    assets_to_generate: List[Dict[str, Any]] = None

class SingleFrameRenderRequest(BaseModel):
    target_id: str
    prompt: str
    seed: int
    style_lock: bool = True

class SaveFileRequest(BaseModel):
    source_file_relative_path: str  # 相对 Runs 的路径，如 "Run_xxx/output/narrative_v6_final_epic.mp4"
    target_absolute_path: str

class TtsPreviewRequest(BaseModel):
    engine: str
    voice: str
    rate: str
    emotion: str
    pitch: int = 0
    volume: int = 0
    prompt: str = ""


# ── 🛠️ 辅助函数 ──

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


def _stage_ch(st):
    mapping = {
        "child": "童年",
        "youth": "青年",
        "middle": "中年",
        "elderly": "老年"
    }
    return mapping.get(st, st)


def extract_entities_manually(text: str, mode_path: str = "RED") -> List[str]:
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
    
    print(f"[API 中控] 正在为 {mode_path} 提炼 {N} 个核心视觉要素: {labels}...")
    
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
                {"role": "user", "content": text[:2000]}
            ],
            temperature=0.3,
            max_tokens=250
        )
        content = response.choices[0].message.content.strip()
        if "```" in content:
            content = content.split("```")[1].replace("json", "").strip()
        
        res = json.loads(content)
        if isinstance(res, list) and len(res) >= N:
            return [str(e)[:16] for e in res[:N]]
        elif isinstance(res, list) and len(res) > 0:
            while len(res) < N:
                res.append(fallback[len(res)])
            return [str(e)[:16] for e in res]
        else:
            return fallback
    except Exception as e:
        print(f"⚠️ [API 中控] 提炼实体词失败: {e}，将采用兜底词。")
        return fallback


def _generate_cast_prompts_via_llm(topic: str, synopsis_text: str, entities: list, custom_template: str = ""):
    """根据故事简介与提取出的资产词，并参考定制风格模板，调用大模型动态构思符合该故事背景的定妆照提示词"""
    mode_path = GLOBAL_STATE.get("mode_path", "RED")
    print(f"[API 中控] 正在调用大模型为频道 {mode_path} 动态设计符合故事背景的视觉描述...")
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
            cast_prompt_parts.append(f"[{lbl}]\n{desc}")
            
        cast_prompt = "\n\n".join(cast_prompt_parts)
        print("[API 中控] 动态定妆提示词大模型构思成功！")
        return cast_prompt
    except Exception as e:
        print(f"⚠️ [API 中控] 动态构思定妆提示词失败: {e}，将采用备用默认模板。")
        cast_prompt_parts = []
        for lbl, tpl, ent in zip(labels, baseline_prompts, ents):
            desc = tpl.replace("{entity}", ent).replace("{ent}", ent)
            cast_prompt_parts.append(f"[{lbl}]\n{desc}")
        return "\n\n".join(cast_prompt_parts)


@app.post("/api/story/v1/compile")
async def compile_story(req: StoryCompileRequest):
    """
    📖 1. 剧本编译与多轨 System Prompt 提交
    - 支持智能润色开启 ➔ 调用 LLM 润色
    - 支持智能润色关闭 ➔ 原汁原味 100% 锁死直出，物理段落切片
    """
    print(f"\n[API 中控] 收到剧本编译请求。当前模式: {req.mode_path}，润色开关: {req.pipeline_config.polish_flow.enabled}")
    
    try:
        # A. 开启全新隔离批次
        topic = "director_cut_" + req.mode_path.lower()
        run_dir = start_new_run(topic=topic)
        run_id = run_dir.name
        paths = get_paths(create_if_missing=True)
        scripts_dir = paths["scripts_dir"]
        
        GLOBAL_STATE["current_run_id"] = run_id
        GLOBAL_STATE["topic"] = topic
        GLOBAL_STATE["mode_path"] = req.mode_path
        GLOBAL_STATE["original_text"] = req.original_text
        GLOBAL_STATE["style_presets"] = req.pipeline_config.render_flow.style_presets
        GLOBAL_STATE["seed"] = req.pipeline_config.render_flow.seed
        GLOBAL_STATE["polish_enabled"] = req.pipeline_config.polish_flow.enabled
        GLOBAL_STATE["tts_engine"] = req.pipeline_config.voiceover_flow.engine
        GLOBAL_STATE["tts_voice"] = req.pipeline_config.voiceover_flow.voice_role
        GLOBAL_STATE["tts_rate"] = req.pipeline_config.voiceover_flow.voice_rate
        GLOBAL_STATE["tts_emotion"] = req.pipeline_config.voiceover_flow.voice_emotion
        GLOBAL_STATE["tts_pitch"] = req.pipeline_config.voiceover_flow.voice_pitch
        GLOBAL_STATE["tts_volume"] = req.pipeline_config.voiceover_flow.voice_volume
        GLOBAL_STATE["tts_prompt"] = req.pipeline_config.voiceover_flow.voice_prompt
        if req.pipeline_config.render_flow.cast_prompt:
            GLOBAL_STATE["cast_prompt"] = req.pipeline_config.render_flow.cast_prompt
        if req.pipeline_config.render_flow.storyboard_prompt:
            GLOBAL_STATE["storyboard_prompt"] = req.pipeline_config.render_flow.storyboard_prompt

        # ── 🔌 动态同步覆盖后台真实提示词 ──
        # 1. 覆盖视觉风格提示词
        custom_style_prompt = req.pipeline_config.render_flow.style_presets
        if custom_style_prompt.strip():
            config.STYLE_ANCHOR = custom_style_prompt
            config.REF_STYLE_ANCHOR = custom_style_prompt
            os.environ["STYLE_ANCHOR"] = custom_style_prompt
            os.environ["REF_STYLE_ANCHOR"] = custom_style_prompt
            print(f"[API 中控] 动态同步：已将全局 STYLE_ANCHOR 覆盖为用户自定风格。")

        # 2. 覆盖剧本润色 System Prompt
        custom_polish_prompt = req.pipeline_config.polish_flow.system_prompt
        if custom_polish_prompt.strip():
            planner._polish_user_script_system_prompt = lambda: custom_polish_prompt
            planner.SYNOPSIS_SYSTEM_PROMPT = custom_polish_prompt
            print(f"[API 中控] 动态同步：已将后台剧本润色 System Prompt 覆盖为用户定制版本。")

        # 3. 覆盖旁白解说 System Prompt
        custom_voiceover_prompt = req.pipeline_config.voiceover_flow.system_prompt
        if custom_voiceover_prompt.strip():
            planner._segment_system_prompt = lambda seg_target, neutral=False: custom_voiceover_prompt.replace("{seg_target}", str(seg_target))
            print(f"[API 中控] 动态同步：已将后台旁白解说 System Prompt 覆盖为用户定制版本。")

        compiled_voiceover = ""
        entities = []
        syn_result = {}

        # B. 开始判定润色与锁死逻辑
        if req.pipeline_config.polish_flow.enabled:
            # 模式 1：开启润色（调用大模型扩写文学剧本）
            print("[API 中控] 开关状态：已开启润色。正在呼唤编剧大模型加工剧本...")
            
            # 触发润色
            syn_result = planner.polish_user_script_synopsis(
                raw_user_input=req.original_text,
                feedback=""
            )
            if not syn_result:
                raise HTTPException(status_code=500, detail="大模型剧本润色失败，请重试。")
            
            syn_result = planner.normalize_synopsis_payload(syn_result)
            compiled_voiceover = syn_result.get("synopsis", "")
            
        else:
            # 模式 2：物理锁死直出（红线拦截：绝对不篡改原著一字一句）
            print("[API 中控] 开关状态：🚫 锁死原著直出！跳过大模型润色，进行物理段落切片。")
            
            # 根据标点符号或换行，直接把用户原文划分为 4 幕物理大纲
            paras = [p.strip() for p in req.original_text.split("\n") if p.strip()]
            if len(paras) < 4:
                # 按句号切分
                paras = [s.strip() + "。" for s in req.original_text.split("。") if s.strip()]
            
            # 重新规划为恰好 4 段
            acts = planner._bucket_strings_for_n_segments(paras, 4)
            
            syn_result = {
                "synopsis_acts": acts,
                "synopsis": req.original_text,
                "era": "",
                "identity": "主角",
                "industry_rules": ["保留用户原著不可篡改规则"],
                "story_source": "user_script",
                "duration": 1.0
            }
            compiled_voiceover = req.original_text

        # C. 物理写入本地大纲缓存以配合后续脚本流转
        temp_synopsis_path = scripts_dir / "temp_synopsis.json"
        with open(temp_synopsis_path, "w", encoding="utf-8") as f:
            json.dump(syn_result, f, ensure_ascii=False, indent=2)
            
        GLOBAL_STATE["last_compiled_synopsis"] = syn_result
        
        # D. 提炼视觉实体（用于生成定妆照）
        entities = extract_entities_manually(compiled_voiceover, req.mode_path)
        GLOBAL_STATE["entities"] = entities
        GLOBAL_STATE["compiled_voiceover"] = compiled_voiceover

        # 动态生成定妆照提示词（依据资产卡片配置判断，支持自定义多卡片和剧情模式）
        assets_config = _get_channel_assets_config(req.mode_path)
        has_character = any(ast.get("type") == "character" for ast in assets_config)
        should_gen_cast = has_character or _is_drama_mode(req.mode_path) or len(assets_config) > 1

        # 检查是否为自定义资产配置频道
        is_custom_channel = False
        try:
            channels_file = os.path.join(BASE_DIR, "data", "channels_presets.json")
            if os.path.exists(channels_file):
                with open(channels_file, "r", encoding="utf-8") as f:
                    channels = json.load(f)
                for ch in channels:
                    if str(ch.get("id", "")).upper() == req.mode_path.upper():
                        if ch.get("channelType") == "custom":
                            is_custom_channel = True
                        break
        except Exception:
            pass

        assets_to_generate = []
        dynamic_cast_prompt = ""

        if should_gen_cast and entities and not is_custom_channel:
            from src.ref_generator import llm_plan_cast_from_synopsis
            print("[API 中控] 🧠 正在使用大模型规划多角色多时期定妆设计...")
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

        # E. 返回给前端
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
        print(f"❌ [API 中控] 编译剧本时发生错误: {e}")
        raise HTTPException(status_code=500, detail=f"剧本编译失败: {str(e)}")


@app.post("/api/assets/v1/generate")
async def generate_assets(req: AssetGenerateRequest):
    """
    🎨 2. 视觉资产（定妆照）生成
    - 当前端拿到了提炼出的实体词后触发。
    - 动态解耦支持任意数量 of 自定义资产大卡！
    """
    run_id = GLOBAL_STATE["current_run_id"]
    topic = GLOBAL_STATE["topic"]
    if not run_id:
        raise HTTPException(status_code=400, detail="未检测到活跃的 Run-ID，请先提交剧本进行编译。")

    print(f"\n[API 中控] 正在为批次 {run_id} 渲染定妆画资产大卡集...")
    print(f"[API 中控] 实体列表: {req.entities}，风格: {req.global_style_prompt}，随机种子: {req.seed}")

    try:
        paths = get_paths()
        refs_dir = paths["refs_dir"]
        
        mode_path = GLOBAL_STATE.get("mode_path", "RED")
        assets_config = _get_channel_assets_config(mode_path)
        print(f"[API 中控] 频道 ({mode_path}) 配置的资产卡片共 {len(assets_config)} 张卡片。")
        
        # 覆盖风格预设配置
        config.REF_STYLE_ANCHOR = req.global_style_prompt
        config.STYLE_ANCHOR = req.global_style_prompt
        os.environ["REF_STYLE_ANCHOR"] = req.global_style_prompt
        os.environ["STYLE_ANCHOR"] = req.global_style_prompt
        
        # 从 payload (req.assets_to_generate) 或 GLOBAL_STATE 读取资产定义
        assets_to_generate = req.assets_to_generate or GLOBAL_STATE.get("assets_to_generate")
        
        if not assets_to_generate:
            # 兼容老逻辑的兜底机制
            # 双通道智能名字对齐
            matched_entities = {}
            unmatched_entities = list(req.entities)
            
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
                ref_anchor_lower = str(req.global_style_prompt or "").lower()
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

        GLOBAL_STATE["assets_to_generate"] = assets_to_generate
        print(f"[API 中控] 待生成的资产卡片共 {len(assets_to_generate)} 张。")
        
        assets_res = []
        generated_char_refs = {}  # Map role_id -> Path of first generated image for consistency
        
        # 依次渲染/读取资产大卡
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
            
            print(f"[API 中控] 正在渲染定妆卡片 {card_id} [{label}]...")
            img_file = out_dir / "triple_view.png"

            # 若已上传自定义定妆照，直接抓取物理文件进行拷贝，跳过 AI 生图
            from pathlib import Path
            base_dir_path = Path(BASE_DIR)
            if custom_image_path and (base_dir_path / custom_image_path).exists():
                import shutil
                shutil.copy(str(base_dir_path / custom_image_path), str(img_file))
                try:
                    from src.project_vault import backup as vault_backup
                    rel = str(img_file.relative_to(BASE_DIR)).replace("\\", "/")
                    vault_backup(img_file, rel)
                except Exception:
                    pass
                print(f"  ✅ [Done] 已直接从本地复制用户定妆图并拷贝到: {img_file}")
            else:
                if t in ("scene", "prop"):
                    from src.image_engine import generate_image as _gen_img
                    if t == "scene":
                        lines = [
                            "A flat 2D vector style minimalist cartoon background scenery, WIDE ANGLE CINEMATIC BACKGROUND, No characters, no people.",
                            "Lighting: flat even cartoon lighting—no dramatic cast shadows, rim light, or studio volumetrics.",
                            f"Style (summary): {req.global_style_prompt}",
                            f"Scenery Details: {prompt}"
                        ]
                    else:
                        lines = [
                            "A flat 2D vector icon cartoon object on a flat pure white #FFFFFF background only—no floor, horizon, or environment.",
                            "Lighting: flat even cartoon lighting—no dramatic cast shadows, rim light, or studio volumetrics.",
                            f"Style (summary): {req.global_style_prompt}",
                            f"Object Details: {prompt}"
                        ]
                    full_prompt = "\n".join(lines)
                    
                    from src.api_audit import PHASE_CASTING
                    img_bytes = await _gen_img(
                        prompt=full_prompt,
                        size="2k",
                        standalone_prompt=True,
                        audit_phase=PHASE_CASTING,
                        audit_step=f"triple_view/{card_id}"
                    )
                    if img_bytes:
                        img_file.write_bytes(img_bytes)
                        try:
                            from src.project_vault import backup as vault_backup
                            rel = str(img_file.relative_to(BASE_DIR)).replace("\\", "/")
                            vault_backup(img_file, rel)
                        except Exception:
                            pass
                else:
                    # 角色：走 generate_ref_sheet_at 保留三视图
                    ref_image_path = generated_char_refs.get(role_id)
                    await generate_ref_sheet_at(
                        out_dir=out_dir,
                        english_prompt=prompt,
                        ref_image_path=ref_image_path
                    )
                    if img_file.exists() and role_id not in generated_char_refs:
                        generated_char_refs[role_id] = img_file
            
            # 将相对路径转换为可供前端直连读取的 URL 路径
            img_url = f"http://127.0.0.1:8000/static/runs/{run_id}/refs/{card_id}/triple_view.png?t={int(time.time())}"
            
            assets_res.append({
                "id": card_id,
                "name": label,
                "prompt": prompt,
                "svgType": t,
                "image_url": img_url,
                "custom_image_path": custom_image_path
            })

        # 回写 full_story_v6.json 锚点（支持任意自定义卡片数量与类型）
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
                "tts_pitch": GLOBAL_STATE.get("tts_pitch", 0),
                "tts_volume": GLOBAL_STATE.get("tts_volume", 0),
                "tts_prompt": GLOBAL_STATE.get("tts_prompt", ""),
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

        # 同时写入 refs-prompt.json 供 Stage 3 大模型构思分镜时读取
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

        print("[API 中控] 定妆照渲染与剧本锚点回写成功！")
        return {
            "status": "success",
            "assets": assets_res
        }

    except Exception as e:
        print(f"❌ [API 中控] 定妆资产渲染失败: {e}")
        raise HTTPException(status_code=500, detail=f"定妆资产渲染失败: {str(e)}")

@app.post("/api/render/v1/single-frame")
async def single_frame_render(req: SingleFrameRenderRequest):
    """
    💡 3. 单帧画面重绘（定妆卡片 D1.1 / 分镜单帧 E1）
    - 接收提示词，锁定 Seed 种子，进行局部重绘，替换原图。
    """
    run_id = GLOBAL_STATE["current_run_id"]
    if not run_id:
        raise HTTPException(status_code=400, detail="未检测到活跃的 Run-ID。")

    print(f"\n[API 中控] 收到单帧重绘请求。目标: {req.target_id}，提示词: {req.prompt}")

    try:
        paths = get_paths()
        
        if req.target_id.startswith("cast_"):
            # A. 定妆卡片局部重绘 (D1.1)
            print(f"[API 中控] 正在重画定妆照角色卡: {req.target_id}...")
            out_dir = paths["refs_dir"] / req.target_id
            out_dir.mkdir(parents=True, exist_ok=True)
            
            # 确定当前卡片类型
            mode_path = GLOBAL_STATE.get("mode_path", "RED")
            assets_config = _get_channel_assets_config(mode_path)
            try:
                idx = int(req.target_id.split("_")[-1]) - 1
                t = assets_config[idx]["type"] if idx < len(assets_config) else "character"
            except Exception:
                t = "character"
            img_file = out_dir / "triple_view.png"
            
            if t in ("scene", "prop"):
                # 场景/背景/道具：直接生图，不走三视图流程
                from src.image_engine import generate_image as _gen_img
                global_style_prompt = GLOBAL_STATE.get("style_presets", "cinematic realism, commercial grading, 35mm photograph")
                if t == "scene":
                    lines = [
                        "A flat 2D vector style minimalist cartoon background scenery, WIDE ANGLE CINEMATIC BACKGROUND, No characters, no people.",
                        "Lighting: flat even cartoon lighting—no dramatic cast shadows, rim light, or studio volumetrics.",
                        f"Style (summary): {global_style_prompt}",
                        f"Scenery Details: {req.prompt}"
                    ]
                else:
                    lines = [
                        "A flat 2D vector icon cartoon object on a flat pure white #FFFFFF background only—no floor, horizon, or environment.",
                        "Lighting: flat even cartoon lighting—no dramatic cast shadows, rim light, or studio volumetrics.",
                        f"Style (summary): {global_style_prompt}",
                        f"Object Details: {req.prompt}"
                    ]
                full_prompt = "\n".join(lines)
                
                from src.api_audit import PHASE_CASTING
                img_bytes = await _gen_img(
                    prompt=full_prompt,
                    size="2k",
                    standalone_prompt=True,
                    audit_phase=PHASE_CASTING,
                    audit_step=f"triple_view/{req.target_id}"
                )
                if img_bytes:
                    img_file.write_bytes(img_bytes)
                    try:
                        from src.project_vault import backup as vault_backup
                        rel = str(img_file.relative_to(BASE_DIR)).replace("\\", "/")
                        vault_backup(img_file, rel)
                    except Exception:
                        pass
            else:
                # 剧情主角：走三视图流程
                await generate_ref_sheet_at(
                    out_dir=out_dir,
                    english_prompt=req.prompt,
                    ref_image_path=None
                )
            
            # 增量更新 full_story_v6.json 和 refs-prompt.json 的角色提示词
            try:
                idx = int(req.target_id.split("_")[-1]) - 1
                full_story_path = paths["scripts_dir"] / "full_story_v6.json"
                refs_prompt_path = paths["scripts_dir"] / "refs-prompt.json"
                
                # Load assets_to_generate
                assets_to_generate = []
                if GLOBAL_STATE.get("assets_to_generate"):
                    assets_to_generate = GLOBAL_STATE["assets_to_generate"]
                else:
                    if full_story_path.exists():
                        try:
                            with open(full_story_path, "r", encoding="utf-8") as f:
                                fs_data = json.load(f)
                            assets_to_generate = fs_data.get("metadata", {}).get("assets_to_generate", [])
                            if assets_to_generate:
                                GLOBAL_STATE["assets_to_generate"] = assets_to_generate
                        except Exception:
                            pass

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
                                "english_prompt": req.prompt,
                                "anchor_description": req.prompt
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
                                        "english_prompt": req.prompt,
                                        "anchor_description": req.prompt
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
                                            "english_prompt": req.prompt,
                                            "anchor_description": req.prompt
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
                        "topic": GLOBAL_STATE.get("topic", "my_epic_story"),
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
                        rp_data["protagonist"]["display_name_en"] = display_name_en
                        stage_prompts = rp_data["protagonist"].setdefault("stage_prompts", {})
                        stage_prompts[stage] = {
                            "english_prompt": req.prompt,
                            "anchor_description": req.prompt
                        }
                    else:
                        sup_list = rp_data.setdefault("supporting", [])
                        found = False
                        for item in sup_list:
                            if item.get("role_id") == role_id:
                                item["display_name_en"] = display_name_en
                                stage_prompts = item.setdefault("stage_prompts", {})
                                stage_prompts[stage] = {
                                    "english_prompt": req.prompt,
                                    "anchor_description": req.prompt
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
                                        "english_prompt": req.prompt,
                                        "anchor_description": req.prompt
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
                print(f"⚠️ [API 中控] 更新剧本或定妆提示词文件失败: {update_err}")
            
            img_url = f"http://127.0.0.1:8000/static/runs/{run_id}/refs/{req.target_id}/triple_view.png?t={int(time.time())}" # 加时间戳防止缓存
            
            return {
                "status": "success",
                "render_url": img_url,
                "svgType": t
            }
            
        else:
            # B. 分镜底片单帧局部重绘 (E1)
            print(f"[API 中控] 正在局部重绘分镜单帧: {req.target_id}...")
            
            # 修改分镜 JSON 里对应的 prompt 锚点
            final_json_path = paths["scripts_dir"] / "narrative_v6_final.json"
            if final_json_path.exists():
                with open(final_json_path, "r", encoding="utf-8") as f:
                    narrative_data = json.load(f)
                
                # 寻找对应的帧进行修改 (例如 "frame_02")
                # 假设帧 ID 以 "frame_" 命名，或者直接按索引映射
                frame_idx = 0
                try:
                    frame_idx = int(req.target_id.split("_")[-1]) - 1
                except:
                    pass
                
                if "shots" in narrative_data and frame_idx < len(narrative_data["shots"]):
                    narrative_data["shots"][frame_idx]["visual_prompt"] = req.prompt
                    with open(final_json_path, "w", encoding="utf-8") as f:
                        json.dump(narrative_data, f, ensure_ascii=False, indent=2)
            
            # 单帧生图，输出到 storyboards/ 目录中
            # 调用已有的核心绘图引擎
            from src.image_engine import generate_image
            img_bytes = await generate_image(
                prompt=req.prompt,
                size="1080p",
                standalone_prompt=True
            )
            
            # 覆盖原分镜图，例如 storyboards/S_002.png
            frame_filename = f"S_00{frame_idx + 1}.png"
            storyboard_img_path = paths["storyboards_dir"] / frame_filename
            if img_bytes:
                storyboard_img_path.write_bytes(img_bytes)
                
            img_url = f"http://127.0.0.1:8000/static/runs/{run_id}/storyboards/{frame_filename}?t={int(time.time())}"
            
            return {
                "status": "success",
                "render_url": img_url,
                "svgType": "storyboard"
            }

    except Exception as e:
        print(f"❌ [API 中控] 局部重画发生错误: {e}")
        raise HTTPException(status_code=500, detail=f"局部重绘失败: {str(e)}")


@app.post("/api/story/v1/generate-storyboard")
async def generate_storyboard():
    """
    🎬 4. 生成分镜大底片（物理微秒切秒）
    - 连接 Step 1 完成后的分镜切片网格（E 界面）。
    - 此接口在后台自动串起已有的 step1_writer_v6 --phase phase2/3 脚本，并自动提取分镜信息。
    """
    run_id = GLOBAL_STATE["current_run_id"]
    topic = GLOBAL_STATE["topic"]
    if not run_id:
        raise HTTPException(status_code=400, detail="未检测到活跃的 Run-ID。")

    print(f"\n[API 中控] 正在为批次 {run_id} 启动分镜插值与秒数切片...")

    try:
        env = dict(os.environ)
        env["STORYBOARD_PROMPT_TEMPLATE"] = GLOBAL_STATE.get("storyboard_prompt", "")
        env["TTS_ENGINE"] = GLOBAL_STATE.get("tts_engine", "edge")
        env["TTS_VOICE"] = GLOBAL_STATE.get("tts_voice", "")
        env["TTS_RATE"] = GLOBAL_STATE.get("tts_rate", "")
        env["TTS_EMOTION"] = GLOBAL_STATE.get("tts_emotion", "")
        env["TTS_PITCH"] = str(GLOBAL_STATE.get("tts_pitch", 0))
        env["TTS_VOLUME"] = str(GLOBAL_STATE.get("tts_volume", 0))
        env["TTS_PROMPT"] = GLOBAL_STATE.get("tts_prompt", "")

        # A. 运行 step1_writer_v6 --phase phase2 生成 master_voice.mp3 与 micro srt 歌词微轴
        print("[API 中控] 正在执行 Phase 2 (旁白配音与时间轴微切)...")
        # 直接使用 python -m 命令以百分之百保护原有的路径隔离和包环境
        proc2 = subprocess.run(
            [sys.executable, "-m", "src.step1_writer_v6", "--phase", "phase2"],
            cwd=BASE_DIR,
            capture_output=True,
            encoding="utf-8",
            env=env
        )
        if proc2.returncode != 0:
            print(f"❌ [Phase2 错误日志]: {proc2.stderr}")
            raise HTTPException(status_code=500, detail=f"微切时间轴失败: {proc2.stderr}")

        # B. 运行 step1_writer_v6 --phase phase3 生成最终分镜脚本 narrative_v6_final.json
        print("[API 中控] 正在执行 Phase 3 (实体提炼与分镜插值)...")
        proc3 = subprocess.run(
            [sys.executable, "-m", "src.step1_writer_v6", "--phase", "phase3"],
            cwd=BASE_DIR,
            capture_output=True,
            encoding="utf-8",
            env=env
        )
        if proc3.returncode != 0:
            print(f"❌ [Phase3 错误日志]: {proc3.stderr}")
            raise HTTPException(status_code=500, detail=f"分镜插值失败: {proc3.stderr}")

        # C. 运行 step2_comic_generator_v6.py 自动渲染 16 宫格大图并物理自动切割为 S_001.png 等单镜
        print("[API 中控] 正在执行 Step 2 (生图大宫格与切片)...")
        env_step2 = dict(env)
        env_step2["GRID_SKIP_LAYOUT_VALIDATE"] = "1"
        proc_step2 = subprocess.run(
            [sys.executable, "-m", "src.step2_comic_generator_v6"],
            cwd=BASE_DIR,
            capture_output=True,
            env=env_step2,
            encoding="utf-8"
        )
        if proc_step2.returncode != 0:
            print(f"❌ [Step2 错误日志]: {proc_step2.stderr}")
            raise HTTPException(status_code=500, detail=f"分镜画图生图失败: {proc_step2.stderr}")

        # D. 读取生成的分镜底片信息
        paths = get_paths()
        final_json_path = paths["scripts_dir"] / "narrative_v6_final.json"
        
        frames_res = []
        if final_json_path.exists():
            with open(final_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 读取分镜中的每个段落 (微帧)
            for idx, shot in enumerate(data.get("shots", [])):
                frame_idx = idx + 1
                frame_id = f"frame_0{frame_idx}"
                img_filename = f"S_00{frame_idx}.png"
                
                # 拼接成可供前端读取的 URL 路径
                img_url = f"http://127.0.0.1:8000/static/runs/{run_id}/storyboards/{img_filename}"
                
                frames_res.append({
                    "id": frame_id,
                    "text": shot.get("voiceover_text", "电影叙事中..."),
                    "prompt": shot.get("visual_prompt", "cinematic shot"),
                    "image_url": img_url,
                    "time_range": f"{shot.get('trigger_time', 0):.1f}s - {shot.get('trigger_time', 0) + 3.5:.1f}s"
                })

        print("[API 中控] 分镜大底片生成完成！")
        return {
            "status": "success",
            "frames": frames_res
        }

    except Exception as e:
        print(f"❌ [API 中控] 生成分镜底片发生致命错误: {e}")
        raise HTTPException(status_code=500, detail=f"生成分镜底片失败: {str(e)}")


@app.post("/api/story/v1/synthesize")
async def synthesize_video():
    """
    🎥 5. 全盘合成（FFmpeg 绝对时间轴卡秒视频物理组装）
    - 驱动 step3_assembler_v6 编译成片，并返回成片的静态视频 URL！
    """
    run_id = GLOBAL_STATE["current_run_id"]
    if not run_id:
        raise HTTPException(status_code=400, detail="未检测到活跃的 Run-ID。")

    print(f"\n[API 中控] 正在呼唤 FFmpeg 拼装大师，开启批次 {run_id} 的全盘合成...")

    try:
        # 直接运行您已开发好的合成脚本 step3_assembler_v6
        proc = subprocess.run(
            [sys.executable, "-m", "src.step3_assembler_v6"],
            cwd=BASE_DIR,
            capture_output=True,
            encoding="utf-8"
        )
        if proc.returncode != 0:
            print(f"❌ [FFmpeg 拼装报错]: {proc.stderr}")
            raise HTTPException(status_code=500, detail=f"视频合成失败: {proc.stderr}")

        # 检查是否成功导出了 narrative_v6_final_epic.mp4
        paths = get_paths()
        epic_mp4_path = paths["output_dir"] / "narrative_v6_final_epic.mp4"
        if not epic_mp4_path.exists():
            raise HTTPException(status_code=500, detail="合成器运行完毕，但未在 output 目录下发现最终的视频文件。")

        # 拼接成可供前台内置播放器流畅播放的静态 URL
        video_url = f"http://127.0.0.1:8000/static/runs/{run_id}/output/narrative_v6_final_epic.mp4"
        print(f"[API 中控] 🎬 全盘合成大获成功！视频文件: {epic_mp4_path}")

        # 返回相对路径以供下载使用
        relative_mp4_path = f"{run_id}/output/narrative_v6_final_epic.mp4"

        return {
            "status": "success",
            "video_url": video_url,
            "relative_path": relative_mp4_path
        }

    except Exception as e:
        print(f"❌ [API 中控] 视频合成发生致命错误: {e}")
        raise HTTPException(status_code=500, detail=f"视频物理合成失败: {str(e)}")


@app.post("/api/story/v1/download")
async def download_video(req: SaveFileRequest):
    """
    💾 6. 系统原生“另存为”另拷文件下载
    - 从隔离运行文件夹中把生成的 MP4 拷到用户指定的任何盘符和目录中。
    """
    print(f"\n[API 中控] 正在为用户物理保存视频...")
    print(f"[API 中控] 源相对文件: {req.source_file_relative_path}")
    print(f"[API 中控] 目标绝对物理路径: {req.target_absolute_path}")

    try:
        source_abs_path = os.path.join(RUNS_DIR, req.source_file_relative_path)
        if not os.path.exists(source_abs_path):
            raise HTTPException(status_code=404, detail="未找到合成好的视频源文件。")

        # 执行物理安全拷贝
        shutil.copy(source_abs_path, req.target_absolute_path)
        print(f"🎉 [API 中控] 成功！您的科幻大片已安全下载至: {req.target_absolute_path}")
        return {"status": "success", "msg": f"保存成功！视频已导出至 {req.target_absolute_path}"}

    except Exception as e:
        print(f"❌ [API 中控] 导出拷贝失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件保存拷贝失败: {str(e)}")


@app.post("/api/story/v1/tts-preview")
async def tts_preview(req: TtsPreviewRequest):
    """
    🎙️ 旁白音色试听生成接口
    """
    print(f"\n[API 中控] 正在为用户生成试听音频: engine={req.engine}, voice={req.voice}, rate={req.rate}, emotion={req.emotion}")
    try:
        preview_text = "您好！这是我当前的声音效果，如果您觉得满意，就选择我为您配音吧。"
        if req.engine == "volc" and req.emotion == "expressive":
            preview_text = "<cot text=温柔>您好！这是我当前的声音效果，如果您觉得满意，就选择我为您配音吧。</cot>"

        preview_dir = BASE_DIR / "previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        
        import hashlib
        config_hash = hashlib.md5(f"{req.engine}_{req.voice}_{req.rate}_{req.emotion}_{req.pitch}_{req.volume}_{req.prompt}".encode("utf-8")).hexdigest()
        filename = f"preview_{config_hash}.mp3"
        local_audio_path = preview_dir / filename
        
        if not local_audio_path.exists():
            if req.engine == "volc":
                from src.step1_writer_v6 import _run_volc_tts_to_files
                _run_volc_tts_to_files(
                    text=preview_text,
                    audio_path=local_audio_path,
                    voice=req.voice,
                    rate=req.rate,
                    emotion=req.emotion,
                    pitch=req.pitch,
                    volume=req.volume,
                    prompt=req.prompt
                )
            else:
                from src.step1_writer_v6 import _run_edge_tts_to_files
                vtt_path = local_audio_path.with_suffix(".vtt")
                _run_edge_tts_to_files(
                    text=preview_text,
                    audio_path=local_audio_path,
                    vtt_path=vtt_path,
                    voice=req.voice,
                    rate=req.rate
                )
                vtt_path.unlink(missing_ok=True)

        audio_url = f"http://127.0.0.1:8000/static/previews/{filename}"
        print(f"[API 中控] 🎙️ 试听音频生成成功: {audio_url}")
        return {"status": "success", "audio_url": audio_url}

    except Exception as e:
        print(f"❌ [API 中控] 生成试听音频发生错误: {e}")
        raise HTTPException(status_code=500, detail=f"试听音频生成失败: {str(e)}")
        


# ── 启动主入口 ──
if __name__ == "__main__":
    import uvicorn
    # 绑定 8000 端口，开启运行
    uvicorn.run(app, host="127.0.0.1", port=8000)
