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
from src.ref_generator import run_ref_process, generate_ref_sheet_at
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
    "last_compiled_synopsis": {}
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

class RenderFlow(BaseModel):
    style_presets: str = ""
    seed: int = 40984180

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

class SingleFrameRenderRequest(BaseModel):
    target_id: str
    prompt: str
    seed: int
    style_lock: bool = True

class SaveFileRequest(BaseModel):
    source_file_relative_path: str  # 相对 Runs 的路径，如 "Run_xxx/output/narrative_v6_final_epic.mp4"
    target_absolute_path: str


# ── 🛠️ 辅助函数 ──

def is_science_or_infographic_mode(mode_path: str) -> bool:
    """
    智能判定是否为“非虚构剧情”的极简单背景模式。
    - 剧情故事/角色扮演 (含 DRAMA, ROLEPLAY, RED, BLUE) -> 走 3 张人物场景道具卡。
    - 其它所有解说或科普类频道 (如 SCIENCE 科普, FOOD 美食, FINANCE 财经, HISTORY 历史) -> 自适应极简为 1 张画布模板背景卡！
    """
    m = str(mode_path).upper()
    if "DRAMA" in m or m in ("RED", "BLUE", "ROLEPLAY"):
        return False
    return True


def extract_entities_manually(text: str, mode_path: str = "RED") -> List[str]:
    """
    智能提炼定妆照核心实体词。
    - 剧情故事: 提炼 3 个词 [最核心人物角色, 核心大场景, 最关键线索道具]
    - 非虚构解说/科普 (美食/财经/科学): 仅提炼 1 个词 [最适合的演示大背景模板]
    """
    client = planner.get_client()
    
    if is_science_or_infographic_mode(mode_path):
        print(f"[API 中控] 解说/非剧情频道 ({mode_path})：正在为定妆照智能提炼唯一的【画布背景模板】实体词...")
        sys_prompt = "你是一个视频美术指导。请读下方解说文本，提炼出最适合作为全片科学或解说演示背景大底板的【1个视觉基底风格词】（如：\"温馨美食烹饪餐桌背景\" 或 \"深色物理网格草稿纸\" 或 \"科技蓝图底纹\" 或 \"石板手绘黑板背景\"）。只返回一个中文 JSON 数组，只包含这1个词（如：[\"温馨美食烹饪餐桌背景\"]），不要任何解释和 markdown 围栏。"
    else:
        print("[API 中控] 剧情/故事频道：正在为定妆照智能提炼核心三要素...")
        sys_prompt = "你是一个剧本分析师。请读下方文本，提炼出【1个最核心人物角色】、【1个核心大场景】和【1个最关键线索道具】。只返回一个中文 JSON 数组，包含这三个词（如：[\"老钟表匠\", \"机械工坊\", \"逆动怀表\"]），不要任何解释和 markdown 围栏。"

    try:
        response = client.chat.completions.create(
            model=config.MODEL_LLM,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": text[:2000]}
            ],
            temperature=0.2,
            max_tokens=200
        )
        content = response.choices[0].message.content.strip()
        if "```" in content:
            content = content.split("```")[1].replace("json", "").strip()
        entities = json.loads(content)
        if isinstance(entities, list) and len(entities) > 0:
            print(f"[API 中控] 提炼实体成功: {entities}")
            if is_science_or_infographic_mode(mode_path):
                return [str(e)[:16] for e in entities[:1]]
            else:
                return [str(e)[:16] for e in entities[:3]]
    except Exception as e:
        print(f"⚠️ [API 中控] 实体提炼失败: {e}，将采用备用兜底词组。")
    
    # 兜底词组
    if is_science_or_infographic_mode(mode_path):
        return ["极简视觉网格底模板"]
    return ["核心角色", "神秘工坊", "核心道具"]


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
                "era": "霓虹雨夜",
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

        # E. 返回给桌年前端
        return {
            "status": "success",
            "data": {
                "compiled_voiceover": compiled_voiceover,
                "extracted_entities": entities
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
    - 动态解耦支持 1 张背景底图或 3 张剧情人景物大卡！
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
        
        # 根据提炼实体的个数与当前频道类型动态自适应卡片配置
        assets_res = []
        mode_path = GLOBAL_STATE.get("mode_path", "RED")
        if is_science_or_infographic_mode(mode_path) or len(req.entities) == 1:
            labels = ["视觉基调背景"]
            types = ["scene"]
        else:
            labels = ["主角", "核心场景", "线索道具"]
            types = ["character", "scene", "prop"]
        
        # 覆盖风格预设配置
        config.REF_STYLE_ANCHOR = req.global_style_prompt
        config.STYLE_ANCHOR = req.global_style_prompt
        os.environ["REF_STYLE_ANCHOR"] = req.global_style_prompt
        os.environ["STYLE_ANCHOR"] = req.global_style_prompt
        
        # 依次渲染资产大卡（支持单卡极简或三卡铁三角）
        for idx, (ent, label, t) in enumerate(zip(req.entities, labels, types)):
            # 建立独立的文件夹
            card_id = f"cast_0{idx + 1}"
            out_dir = refs_dir / card_id
            out_dir.mkdir(parents=True, exist_ok=True)
            
            if t == "scene":
                prompt = f"A flat 2D vector style minimalist cartoon background scenery depicting {ent}. Flat shades, no character."
            elif t == "prop":
                prompt = f"A flat 2D vector icon cartoon object depicting {ent}. Primitive shape, flat color fill, white background."
            else: # character
                prompt = f"A cute cartoon stickman style representation of {ent}. Flat colors, strong outline, white background."

            # 调用已有的生图流程核心 generate_ref_sheet_at
            print(f"[API 中控] 正在渲染定妆卡片 [{label} - {ent}]...")
            img_path = await generate_ref_sheet_at(
                out_dir=out_dir,
                english_prompt=prompt,
                ref_image_path=None
            )
            
            # 将相对路径转换为可供前端直连读取的 URL 路径
            img_url = f"http://127.0.0.1:8000/static/runs/{run_id}/refs/{card_id}/triple_view.png"
            
            assets_res.append({
                "id": card_id,
                "name": f"{label}：{ent}",
                "prompt": prompt,
                "svgType": t,
                "image_url": img_url
            })

        # 回写 full_story_v6.json 锚点
        full_story_v6_path = paths["scripts_dir"] / "full_story_v6.json"
        
        # 构建物理锚点回写字典
        if is_science_or_infographic_mode(mode_path) or len(req.entities) == 1:
            anchors_data = {
                "supporting_scene": f"data/runs/{run_id}/refs/cast_01/triple_view.png"
            }
        else:
            anchors_data = {
                "middle": f"data/runs/{run_id}/refs/cast_01/triple_view.png",
                "supporting_scene": f"data/runs/{run_id}/refs/cast_02/triple_view.png",
                "supporting_prop": f"data/runs/{run_id}/refs/cast_03/triple_view.png"
            }
            
        story_data = {
            "metadata": {
                "topic": topic,
                "project_name": topic,
                "era": "霓虹雨夜",
                "duration": 1.0,
                "run_id": run_id,
                "story_source": "user_script"
            },
            "master_design": {
                "full_narration": GLOBAL_STATE["compiled_voiceover"],
                "cast_registry": {
                    "protagonist": {"display_name_en": "Protagonist", "stages": ["middle"], "stage_prompts": {}},
                    "supporting": []
                },
                "physical_char_anchors": anchors_data
            }
        }
        with open(full_story_v6_path, "w", encoding="utf-8") as f:
            json.dump(story_data, f, ensure_ascii=False, indent=2)

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
            
            # 确定当前卡片类型
            mode_path = GLOBAL_STATE.get("mode_path", "RED")
            is_science = is_science_or_infographic_mode(mode_path)
            
            if is_science:
                t = "scene"
            else:
                t = "character" if req.target_id == "cast_01" else ("scene" if req.target_id == "cast_02" else "prop")
            
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
                    img_file = out_dir / "triple_view.png"
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
        # A. 运行 step1_writer_v6 --phase phase2 生成 master_voice.mp3 与 micro srt 歌词微轴
        print("[API 中控] 正在执行 Phase 2 (旁白配音与时间轴微切)...")
        # 直接使用 python -m 命令以百分之百保护原有的路径隔离和包环境
        proc2 = subprocess.run(
            [sys.executable, "-m", "src.step1_writer_v6", "--phase", "phase2"],
            cwd=BASE_DIR,
            capture_output=True,
            encoding="utf-8"
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
            encoding="utf-8"
        )
        if proc3.returncode != 0:
            print(f"❌ [Phase3 错误日志]: {proc3.stderr}")
            raise HTTPException(status_code=500, detail=f"分镜插值失败: {proc3.stderr}")

        # C. 运行 step2_comic_generator_v6.py 自动渲染 16 宫格大图并物理自动切割为 S_001.png 等单镜
        print("[API 中控] 正在执行 Step 2 (生图大宫格与切片)...")
        env = dict(os.environ)
        env["GRID_SKIP_LAYOUT_VALIDATE"] = "1"
        proc_step2 = subprocess.run(
            [sys.executable, "-m", "src.step2_comic_generator_v6"],
            cwd=BASE_DIR,
            capture_output=True,
            env=env,
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


# ── 启动主入口 ──
if __name__ == "__main__":
    import uvicorn
    # 绑定 8000 端口，开启运行
    uvicorn.run(app, host="127.0.0.1", port=8000)
