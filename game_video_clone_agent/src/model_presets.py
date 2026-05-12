"""
🧠 模型与厂商预设库 (Model Presets Registry) — v3.0 三分离版
=============================================================
三个独立控制变量，分别管理 LLM / VLM / IMG 三类任务。
更换厂商时只需修改对应的 ACTIVE_xxx_VENDOR 变量。
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

if load_dotenv:
    # 统一从项目根目录加载 .env，避免在不同入口脚本下读取失败
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=_env_path)

# ================================================================
#  🚩 三分离：LLM / VLM / IMG 各自独立选厂商
# ================================================================
ACTIVE_LLM_VENDOR = "deepseek_v4_pro"    # DeepSeek V4 Pro（OpenAI 兼容）
ACTIVE_VLM_VENDOR = "gribo_text"    # 与 LLM 同源；分镜多模态
ACTIVE_IMG_VENDOR = "gribo_img"          # ✅ 生图仍走 Gribo
# 备选厂商（降级时才改）："doubao_v4" | "aliyun_dashscope" | "deepseek_v4_pro"


# ================================================================
#  📚 厂商预设库
# ================================================================
VENDORS_PRESETS = {

    # ----------------------------------------------------------
    # 阿里云 DashScope（LLM + VLM 主力）
    # ----------------------------------------------------------
    "aliyun_dashscope": {
        "vendor_name": "阿里云 DashScope",
        "api_key": os.getenv("ALIYUN_DASHSCOPE_API_KEY", ""),
        "app_secret": os.getenv("ALIYUN_DASHSCOPE_APP_SECRET", ""),
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "dashscope_base_http": "https://dashscope.aliyuncs.com/api/v1",
        "models": {
            "llm": "qwen-max-latest",
            "vlm": "qwen-vl-max-latest",
            "img": "qwen-image-2.0",
        },
        "extra_params": {}
    },

    # ----------------------------------------------------------
    # DeepSeek V4 Pro（OpenAI Chat Completions 兼容）
    # 官方：base_url 不变，模型名 deepseek-v4-pro / deepseek-v4-flash
    # ----------------------------------------------------------
    "deepseek_v4_pro": {
        "vendor_name": "DeepSeek V4 Pro",
        "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        "app_secret": os.getenv("DEEPSEEK_APP_SECRET", ""),
        "base_url": "https://api.deepseek.com",
        "dashscope_base_http": "",
        "models": {
            "llm": "deepseek-v4-pro",
            "vlm": "deepseek-v4-pro",
        },
        "extra_params": {
            "protocol": "openai_compatible",
        }
    },

    # ----------------------------------------------------------
    # 豆包 / 火山方舟（Doubao-Seedream-4.0 1K/2K/4K）
    # ----------------------------------------------------------
    "doubao_v4": {
        "vendor_name": "豆包 (Seedream-4.0)",
        "api_key": os.getenv("DOUBAO_V4_API_KEY", ""),
        "app_secret": os.getenv("DOUBAO_V4_APP_SECRET", ""),
        "base_url": "https://ark.cn-beijing.volces.com",
        "dashscope_base_http": "",
        "models": {
            "llm": "doubao-pro-32k",
            "vlm": "",
            "img": "doubao-seedream-4-0-250828",
        },
        "extra_params": {
            "gen_endpoint": "/api/v3/images/generations",
            "size": "1312x736", # 官方推荐的 1K 16:9 画幅
            "watermark": False,
            "stream": True, # 从文档看，工业级产线优先使用 stream=True 和 disabled 模式
        }
    },

    # ----------------------------------------------------------
    # 豆包 / 火山方舟（Doubao-Seedream-5.0 Endpoint版保留）
    # ----------------------------------------------------------
    "doubao": {
        "vendor_name": "豆包 (火山方舟)",
        "api_key": os.getenv("DOUBAO_API_KEY", ""),
        "app_secret": os.getenv("DOUBAO_APP_SECRET", ""),
        "base_url": "https://ark.cn-beijing.volces.com",
        "dashscope_base_http": "",
        "models": {
            "llm": "doubao-pro-32k",
            "vlm": "",                          # 豆包暂无 VLM，留空
            "img": "ep-m-20260401101830-6h6qd",
        },
        "extra_params": {
            "gen_endpoint": "/api/v3/images/generations",
            "size": "2k",
            "watermark": True,
            "stream": False,
        }
    },

    # ----------------------------------------------------------
    # 谷歌 Gemini (Nano Banana)
    # ----------------------------------------------------------
    "nano_banana": {
        "vendor_name": "Google Gemini (Banana)",
        "api_key": os.getenv("NANO_BANANA_API_KEY", ""),
        "app_secret": os.getenv("NANO_BANANA_APP_SECRET", ""),
        "base_url": "https://generativelanguage.googleapis.com",
        "dashscope_base_http": "",
        "models": {
            "llm": "gemini-1.5-pro",
            "vlm": "gemini-1.5-pro",
            "img": "nano-banana-pro-preview",
        },
        "extra_params": {
            "gen_endpoint": "/v1beta/models/{model}:generateContent"
        }
    },

    # ----------------------------------------------------------
    # 星流 (LibLib / StarFlow)
    # ----------------------------------------------------------
    "starflow_liblib": {
        "vendor_name": "星流 (LibLib API)",
        "api_key": os.getenv("STARFLOW_LIBLIB_API_KEY", ""),
        "app_secret": os.getenv("STARFLOW_LIBLIB_APP_SECRET", ""),
        "base_url": "https://openapi.liblibai.cloud",
        "dashscope_base_http": "",
        "models": {
            "llm": "qwen-plus",
            "vlm": "qwen-vl-max-latest",
            "img": "starflow-ultra",
        },
        "extra_params": {
            "template_uuid": "07e00af4fc464c7ab55ff906f8acf1b7",
            "prompt_magic": 1,
            "status_endpoint": "/api/generate/webui/status",
            "gen_endpoint": "/api/generate/webui/img2img/ultra",
        }
    },

    # ----------------------------------------------------------
    # 📝 Gribo Text (VLM / LLM 专用)
    # ----------------------------------------------------------
    "gribo_text": {
        "vendor_name": "Gribo Text (Qwen-Plus 转发版)",
        "api_key": os.getenv("GRIBO_TEXT_API_KEY", ""),
        "base_url": "https://www.gribo.top/v1",
        "models": {
            "llm": "gemini-3.1-pro-preview",
            "vlm": "gemini-3.1-pro-preview",
        },
        "extra_params": {
            "protocol": "openai_compatible",
        }
    },

    # ----------------------------------------------------------
    # 🎨 Gribo Image (IMG 专用)
    # ----------------------------------------------------------
    "gribo_img": {
        "vendor_name": "Gribo Image (Nano Banana 2)",
        "api_key": os.getenv("GRIBO_IMG_API_KEY", ""),
        "base_url": "https://www.gribo.top/v1",
        "models": {
            "img": "gemini-3.1-flash-image-preview",
        },
        "extra_params": {
            "cooldown": 35,
            "gen_endpoint": "/v1beta/models/{model}:generateContent",
        }
    },
}



# ================================================================
# ⚡ 自动加载三分离配置（供其他模块引用）
# ================================================================
def _get_config(vendor_key: str, role: str) -> dict:
    cfg = VENDORS_PRESETS.get(vendor_key)
    if not cfg:
        raise ValueError(f"未找到厂商预设: {vendor_key}（{role}）请检查 model_presets.py")
    return cfg

_llm_cfg  = _get_config(ACTIVE_LLM_VENDOR, "LLM")
_vlm_cfg  = _get_config(ACTIVE_VLM_VENDOR, "VLM")
_img_cfg  = _get_config(ACTIVE_IMG_VENDOR, "IMG")

# ── LLM 相关 ──────────────────────────────────────────
LLM_API_KEY          = _llm_cfg["api_key"]
LLM_BASE_URL         = _llm_cfg["base_url"]
LLM_DASHSCOPE_HTTP   = _llm_cfg.get("dashscope_base_http", "")
MODEL_LLM            = _llm_cfg["models"]["llm"]

# ── VLM 相关 ──────────────────────────────────────────
VLM_API_KEY          = _vlm_cfg["api_key"]
VLM_BASE_URL         = _vlm_cfg["base_url"]
VLM_DASHSCOPE_HTTP   = _vlm_cfg.get("dashscope_base_http", "")
VLM_COMPAT_URL       = _vlm_cfg["base_url"]   # OpenAI 兼容 URL
MODEL_VLM            = _vlm_cfg["models"]["vlm"]

# ── IMG 相关 ──────────────────────────────────────────
IMG_API_KEY          = _img_cfg["api_key"]
IMG_BASE_URL         = _img_cfg["base_url"]
IMG_DASHSCOPE_HTTP   = _img_cfg.get("dashscope_base_http", "")
MODEL_IMG            = _img_cfg["models"]["img"]
IMG_EXTRA_PARAMS     = _img_cfg.get("extra_params", {})

# ── 向后兼容别名（让旧代码不报错）──────────────────────
API_KEY              = IMG_API_KEY       # 旧代码里 API_KEY 默认指生图厂商
APP_SECRET           = _img_cfg.get("app_secret", "")
BASE_URL             = IMG_BASE_URL
DASHSCOPE_BASE_HTTP  = IMG_DASHSCOPE_HTTP
EXTRA_PARAMS         = IMG_EXTRA_PARAMS
MODELS               = _img_cfg["models"]
