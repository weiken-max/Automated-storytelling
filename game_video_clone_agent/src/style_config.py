"""
🎨 全局风格 & 配置中心 (style_config.py) — v3.1 资产精简版
==========================================
所有脚本共用的风格锚点、API Key、路径配置集中在此。
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# 旁白扩写：segmented=多段请求+拼接；one_shot_acts=按 synopsis_acts 顺序一次性扩写全文
_nem = os.environ.get("NARRATION_EXPAND_MODE", "segmented").strip().lower()
NARRATION_EXPAND_MODE = _nem if _nem in ("segmented", "one_shot_acts") else "segmented"

# ================================================================
#  🔑 三分离 API 配置
# ================================================================
from src.model_presets import (
    # LLM
    LLM_API_KEY, LLM_BASE_URL, LLM_DASHSCOPE_HTTP,
    MODEL_LLM,
    # VLM
    VLM_API_KEY, VLM_BASE_URL, VLM_DASHSCOPE_HTTP, VLM_COMPAT_URL,
    MODEL_VLM,
    # IMG
    IMG_API_KEY, IMG_BASE_URL, IMG_DASHSCOPE_HTTP,
    MODEL_IMG, IMG_EXTRA_PARAMS,
    # 向后兼容别名
    API_KEY, APP_SECRET, BASE_URL, DASHSCOPE_BASE_HTTP, EXTRA_PARAMS, MODELS,
)

# ================================================================
#  🎨 核心风格锚点（V4.0 精致动漫版，全局唯一）
# ================================================================
STYLE_ANCHOR = os.environ.get("STYLE_ANCHOR", (
    "High-quality 2D vector cartoon, bold black outlines, vibrant flat colors with soft cel-shading. "
    "Style inspired by Cyanide and Happiness but with professional lighting and detailed illustrated backgrounds. "
    "Character proportions: stick figure limbs, round bean heads."
))

# 仅用于人物三视图定妆（与 ref_generator 内 Layer A 一致摘要；完整壳以 generate_ref_sheet_at 为准）。
REF_STYLE_ANCHOR = os.environ.get("REF_STYLE_ANCHOR", (
    "Cyanide-and-Happiness web-comic character sheet: 2D vector, oversized round bean head, two dot eyes, "
    "arms and legs as pure black stick strokes (matchstick limbs, no realistic anatomy), simple torso block, "
    "bold outlines, flat fills, no shading or fabric micro-detail."
))

NEGATIVE_PROMPT = (
    "multiple characters, crowded, overlapping characters, "
    "hair, fur, skin texture, 3d, realistic, cgi, shading, gradient, "
    "photorealistic, masterpiece, double face, mutated, extra limbs, "
    "volumetric lighting, rim light, ambient occlusion"
)

FORBIDDEN_WORDS = ["3D", "realistic", "CGI", "octane render"]

# ================================================================
#  📂 路径配置（统一管理）
# ================================================================
DATA_DIR          = BASE_DIR / "data"
SCRIPT_DIR        = DATA_DIR / "scripts"
IMG_DIR           = DATA_DIR / "storyboards"  # 分镜图工作台 (临时产区)
AUDIO_DIR         = DATA_DIR / "audio"        # 音频工作台 (临时产区)
OUTPUT_DIR        = DATA_DIR / "output"       # 最终视频工作台 (最终产区)
REFS_DIR          = DATA_DIR / "refs"         # 角色参考图总目录
VAULT_ROOT        = DATA_DIR / "anchors"      # 🏛️ 项目金库根目录 (历史永久存档)

# 🎬 V6 核心产线剧本路径
FULL_STORY_V6_PATH    = SCRIPT_DIR / "full_story_v6.json"
NARRATIVE_V6_PATH     = SCRIPT_DIR / "narrative_v6.json"
CURRENT_PROJECT_PATH  = SCRIPT_DIR / "current_project.json"   # 当前激活的主题标识器
LINE_TIMELINE_PATH    = SCRIPT_DIR / "line_timeline.json"
MASTER_VOICE_PATH     = AUDIO_DIR / "master_voice.mp3"
SRT_LIKE_TIMELINE_PATH = SCRIPT_DIR / "srt_like_timeline.json"
MASTER_SRT_PATH       = SCRIPT_DIR / "master_voice.srt"
TIMELINE_FOR_LLM_PATH = SCRIPT_DIR / "timeline_for_llm.json"
 

# ── 环境与场景参考图 (Environment Anchors) ──
REFS_DIR                 = DATA_DIR / "refs"
REFS_PROTAGONIST_CHILD   = REFS_DIR / "protagonist_child"
REFS_PROTAGONIST_YOUTH   = REFS_DIR / "protagonist_youth"
REFS_PROTAGONIST_MIDDLE  = REFS_DIR / "protagonist_middle"
REFS_PROTAGONIST_ELDERLY = REFS_DIR / "protagonist_elderly"

# 向后兼容：保留旧的主角样张定义作为默认文件夹（即中年期）
REFS_PROTAGONIST  = REFS_PROTAGONIST_MIDDLE 

REFS_SUPPORTING   = REFS_DIR / "supporting"
REFS_OTHER        = REFS_DIR / "other"  # 已转职为环境锚点文件夹
REFS_BACKUP_DIR   = DATA_DIR / "archive" # 自动存档目录

# 角色与环境标签映射 (多人生阶段绑定核心)
CHARACTER_REF_MAP = {
    "child": REFS_PROTAGONIST_CHILD,
    "youth": REFS_PROTAGONIST_YOUTH,
    "middle": REFS_PROTAGONIST_MIDDLE,
    "elderly": REFS_PROTAGONIST_ELDERLY,
    "protagonist": REFS_PROTAGONIST_MIDDLE, # 向后兼容字段
    "supporting": REFS_SUPPORTING,
    "environment": REFS_OTHER
}

COMBINED_REF_PATH = REFS_PROTAGONIST / "triple_view.png"

# 🎙️ V6.0 语速估算 (中文每分钟约 230 字)
WORDS_PER_MINUTE  = 300

# 未指定时长时的默认成片时长（分钟），与飞书大纲卡片主选项「6 分钟」一致
DEFAULT_STORY_DURATION_MINUTES = 6.0

# 大纲：synopsis（synopsis_acts 拼接全文）最大字符数（汉字+标点），规范化时硬压到此上限内
SYNOPSIS_BODY_MAX_CHARS = 1500

# 长文案目标字数：按「目标成片时长(分钟)」粗估（对齐中文旁白 TTS 实测，略留余量避免成片短于目标时长）
NARRATION_CHARS_PER_MINUTE = 300

# 分段扩写（story_planner）：段数、承接上一段尾字数
NARRATION_SEGMENT_COUNT = 6
NARRATION_SEGMENT_TAIL_CHARS = 240
# 单幕 chat.completions 的 max_tokens：粗估「汉字→token」≈ 2.5（中文模型保守估算）；在目标字数上加 BUFFER 再换算，避免 token 不足导致 finish_reason=length 截断
NARRATION_SEGMENT_MAX_TOKENS_CHAR_BUFFER = 300
NARRATION_SEGMENT_CH_TO_TOKEN_RATIO = 2.5

# 一次性按幕扩写：理想字数带与分段写手一致（相对 target_chars）
ONE_SHOT_NARRATION_LO_RATIO = 0.78
ONE_SHOT_NARRATION_HI_RATIO = 1.18
ONE_SHOT_LENGTH_MAX_ATTEMPTS = 4

# 🎬 视频 & 宫格参数（P1 冻结规格）
# 最终成片固定 4:3，统一避免拉伸。
OUTPUT_VIDEO_SIZE = (1024, 768)      # 4:3 @ 1K

# 容器策略（beat 强绑定）
# 1 subshot -> 单图（4:3 @ 1K）
SINGLE_CONTAINER_SIZE = (1024, 768)
# 2 subshot -> 二宫格（2:3 @ 1K，上下切）
DOUBLE_CONTAINER_SIZE = (1024, 1536)
# 3/4 subshot -> 四宫格（4:3 @ 2K）
FOUR_CONTAINER_SIZE = (2048, 1536)

# ================================================================
#  🎙️ 配音配置
# ================================================================
VOICE_ROLE  = "zh-CN-YunjianNeural"
VOICE_RATE  = "+0%"
VOICE_PITCH = "+0Hz"

# 火山引擎 (豆包语音合成) 配置
VOLC_TTS_API_KEY = os.environ.get("VOLC_TTS_API_KEY", "")
VOLC_TTS_APPID = os.environ.get("VOLC_TTS_APPID", "")


# DSP 默认参数（主音轨连续化）
DSP_TRIM_THRESHOLD_DB = -40.0
DSP_MIN_SILENCE_SEC   = 0.12
DSP_CROSSFADE_SEC     = 0.08
DSP_TARGET_LUFS       = -16.0

# ================================================================
#  🏭 生图配置
# ================================================================
IMG_SIZE         = "1024*768"
OUTPUT_FPS       = 30
MAX_RETRIES      = 3  # 指数退避重试次数
BATCH_SIZE       = 2  # VLM 多模态批次 (极端安全模式)
VLM_BATCH_SIZE   = 2  # 兼容旧版参数
timeout          = 180 # 增加 VLM 超时到 180s (应对复杂剧情)

# 动态分段阈值（token），默认 1500，约为 gpt-5-mini 最大 token 的 20%
STORY_SEGMENT_MAX_TOKENS = 1500

# ================================================================
#  🎞️ 视频合成特效配置 (V6.7)
# ================================================================
FONT_PATH           = "C:/Windows/Fonts/msyh.ttc"  # 默认微软雅黑
SUBTITLE_SIZE       = 32
SUBTITLE_Y_FRAC     = 0.85                         # 字幕位于画面下方 85% 处
TRANSITION_DURATION = 0.5                          # 转场时长 0.5s

# 使用 LLM 生成段落摘要的模型（已在前文配置）
# SUMMARY_MODEL 已在文件中定义，保持不变

