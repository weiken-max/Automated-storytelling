"""
🧠 模型与厂商预设库 (Model Presets Registry) — v3.0 三分离版
=============================================================
三个独立控制变量，分别管理 LLM / VLM / IMG 三类任务。
更换厂商时只需修改对应的 ACTIVE_xxx_VENDOR 变量。
"""

import os
import json
import copy
import re
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
ACTIVE_VLM_VENDOR = "gribo_text"   # VLM 多模态（Google 模型经 Gribo 中转）
ACTIVE_IMG_VENDOR = "gribo_img"          # ✅ 生图仍走 Gribo
ACTIVE_VLM_ANALYZE_VENDOR = "gribo_text"  # 🔍 VLM 识图分析（默认同 VLM）
TRANSLATE_LLM_VENDOR = "deepseek_v4_flash"  # 翻译专用
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
    # DeepSeek V4 Flash（翻译专用，轻量快速）
    # ----------------------------------------------------------
    "deepseek_v4_flash": {
        "vendor_name": "DeepSeek V4 Flash",
        "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        "app_secret": os.getenv("DEEPSEEK_APP_SECRET", ""),
        "base_url": "https://api.deepseek.com",
        "dashscope_base_http": "",
        "models": {
            "llm": "deepseek-v4-flash",
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
    # 🌋 火山方舟 ARK (VLM 多模态专用 — OpenAI 兼容 Bearer Token)
    # 鉴权：标准 OpenAI 客户端 + Bearer Token；model 填推理接入点 ID (ep-/endpoint id)
    # ----------------------------------------------------------
    "volc_ark_vlm": {
        "vendor_name": "火山方舟 ARK (VLM 多模态)",
        "api_key": os.getenv("VOLC_ARK_API_KEY", ""),
        "app_secret": "",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "dashscope_base_http": "",
        "models": {
            "vlm": "doubao-seed-2-1-turbo-260628",
        },
        "extra_params": {
            "protocol": "openai_compatible",
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
            "request_timeout": 300,
            "gen_endpoint": "/v1beta/models/{model}:generateContent",
        }
    },
}

# 内置预设快照：后续会叠加本地供应商配置，但保留一份干净默认值便于重载/恢复
BUILTIN_VENDOR_KEYS = set(VENDORS_PRESETS.keys())
_BUILTIN_VENDOR_PRESETS = copy.deepcopy(VENDORS_PRESETS)


# ================================================================
# 🧩 商业版供应商目录：内置预设 + 本地自定义供应商
# ================================================================

def _settings_file() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "model_settings.json"


def _load_settings_json() -> dict:
    path = _settings_file()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _safe_vendor_key(name: str) -> str:
    raw = (name or "custom_provider").strip().lower()
    raw = re.sub(r"[^a-z0-9_\-]+", "_", raw)
    raw = re.sub(r"_+", "_", raw).strip("_")
    return raw or "custom_provider"


def normalize_provider_config(vendor_key: str, cfg: dict, builtin: bool = False) -> dict:
    """把 UI/JSON 中的供应商配置统一成 VENDORS_PRESETS 可用结构。"""
    cfg = cfg or {}
    models = cfg.get("models") if isinstance(cfg.get("models"), dict) else {}
    variants = cfg.get("model_variants") or cfg.get("models_list") or []
    if isinstance(variants, str):
        variants = [m.strip() for m in variants.split("\n") if m.strip()]
    variants = [str(m).strip() for m in variants if str(m).strip()]

    api_format = cfg.get("api_format") or cfg.get("extra_params", {}).get("protocol") or "openai_compatible"
    extra = cfg.get("extra_params") if isinstance(cfg.get("extra_params"), dict) else {}
    extra = dict(extra)
    if api_format:
        extra["protocol"] = api_format

    return {
        "vendor_name": cfg.get("vendor_name") or cfg.get("name") or vendor_key,
        "api_key": cfg.get("api_key", ""),
        "app_secret": cfg.get("app_secret", ""),
        "base_url": cfg.get("base_url", ""),
        "dashscope_base_http": cfg.get("dashscope_base_http", ""),
        "models": {
            "llm": models.get("llm", ""),
            "vlm": models.get("vlm", models.get("llm", "")),
            "img": models.get("img", ""),
        },
        "model_variants": list(dict.fromkeys(variants + [m for m in models.values() if m])),
        "api_format": api_format,
        "enabled": bool(cfg.get("enabled", True)),
        "builtin": bool(cfg.get("builtin", builtin)),
        "extra_params": extra,
    }


def apply_provider_catalog(data: dict = None):
    """把 model_settings.json 中的供应商目录合并到运行时 VENDORS_PRESETS。"""
    data = data if isinstance(data, dict) else _load_settings_json()
    VENDORS_PRESETS.clear()
    VENDORS_PRESETS.update(copy.deepcopy(_BUILTIN_VENDOR_PRESETS))

    # 内置供应商默认标记
    for cfg in VENDORS_PRESETS.values():
        cfg.setdefault("builtin", True)
        cfg.setdefault("enabled", True)
        api_format = cfg.get("api_format") or cfg.get("extra_params", {}).get("protocol") or "openai_compatible"
        cfg["api_format"] = api_format
        cfg.setdefault("model_variants", list(dict.fromkeys(m for m in cfg.get("models", {}).values() if m)))

    # 对内置项做本地覆盖（禁用、URL、模型列表等）
    overrides = data.get("provider_overrides", {})
    if isinstance(overrides, dict):
        for vk, ov in overrides.items():
            if vk not in VENDORS_PRESETS or not isinstance(ov, dict):
                continue
            merged = copy.deepcopy(VENDORS_PRESETS[vk])
            for key in ("vendor_name", "base_url", "api_key", "enabled", "api_format", "model_variants"):
                if key in ov:
                    merged[key] = ov[key]
            if isinstance(ov.get("models"), dict):
                merged.setdefault("models", {}).update(ov["models"])
            if isinstance(ov.get("extra_params"), dict):
                merged.setdefault("extra_params", {}).update(ov["extra_params"])
            VENDORS_PRESETS[vk] = normalize_provider_config(vk, merged, builtin=True)

    # 加载客户自定义供应商
    custom = data.get("custom_providers", {})
    if isinstance(custom, dict):
        for vk, cfg in custom.items():
            if not isinstance(cfg, dict):
                continue
            safe_key = _safe_vendor_key(vk)
            if safe_key in BUILTIN_VENDOR_KEYS:
                safe_key = f"custom_{safe_key}"
            VENDORS_PRESETS[safe_key] = normalize_provider_config(safe_key, cfg, builtin=False)


def _save_settings_json(data: dict):
    """把完整 settings 字典写回 model_settings.json（调用方负责合并）。"""
    path = _settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def _merge_save_settings(patch: dict):
    """读取现有 settings，合并 patch（浅合并顶层 key）后写回，避免整文件覆盖。"""
    data = _load_settings_json()
    for k, v in (patch or {}).items():
        data[k] = v
    _save_settings_json(data)
    return data


def list_all_providers() -> list:
    """
    返回完整供应商目录（不按 base_url 合并），供商业版供应商管理面板使用。
    每项: vendor_key, vendor_name, base_url, api_format, enabled, builtin,
          has_key, masked_key, supported_roles, default_models, model_variants
    """
    result = []
    for vk, cfg in VENDORS_PRESETS.items():
        api_key_raw = cfg.get("api_key", "") or ""
        has_key = bool(api_key_raw.strip())
        masked_key = (
            api_key_raw[:8] + "***" if len(api_key_raw) > 12
            else (api_key_raw[:4] + "***" if api_key_raw else "")
        )
        models = cfg.get("models", {}) or {}
        supported_roles = [r for r in ("llm", "vlm", "img") if models.get(r)]
        result.append({
            "vendor_key": vk,
            "vendor_name": cfg.get("vendor_name", vk),
            "base_url": cfg.get("base_url", ""),
            "api_format": cfg.get("api_format")
                or cfg.get("extra_params", {}).get("protocol")
                or "openai_compatible",
            "enabled": bool(cfg.get("enabled", True)),
            "builtin": bool(cfg.get("builtin", vk in BUILTIN_VENDOR_KEYS)),
            "has_key": has_key,
            "api_key": api_key_raw,
            "masked_key": masked_key,
            "supported_roles": supported_roles,
            "default_models": {
                "llm": models.get("llm", ""),
                "vlm": models.get("vlm", ""),
                "img": models.get("img", ""),
            },
            "model_variants": list(cfg.get("model_variants")
                or dict.fromkeys(m for m in models.values() if m)),
        })
    return result


def save_provider(cfg: dict) -> dict:
    """
    新增或更新一个供应商。
    - 内置供应商：写入 provider_overrides（只覆盖允许的字段）
    - 自定义供应商：写入 custom_providers
    返回 {"vendor_key": ..., "builtin": bool}
    """
    cfg = cfg or {}
    vendor_key = (cfg.get("vendor_key") or "").strip()
    data = _load_settings_json()

    # —— 内置供应商：走 overrides —— #
    if vendor_key and vendor_key in BUILTIN_VENDOR_KEYS:
        overrides = data.get("provider_overrides", {})
        if not isinstance(overrides, dict):
            overrides = {}
        ov = overrides.get(vendor_key, {})
        if not isinstance(ov, dict):
            ov = {}
        for key in ("vendor_name", "base_url", "api_key", "enabled", "api_format"):
            if key in cfg:
                ov[key] = cfg[key]
        if isinstance(cfg.get("models"), dict):
            ov["models"] = {**(ov.get("models") or {}), **cfg["models"]}
        variants = cfg.get("model_variants")
        if isinstance(variants, str):
            variants = [m.strip() for m in variants.split("\n") if m.strip()]
        if variants is not None:
            ov["model_variants"] = [str(m).strip() for m in variants if str(m).strip()]
        overrides[vendor_key] = ov
        data["provider_overrides"] = overrides
        _save_settings_json(data)
        apply_provider_catalog(data)
        return {"vendor_key": vendor_key, "builtin": True}

    # —— 自定义供应商：走 custom_providers —— #
    custom = data.get("custom_providers", {})
    if not isinstance(custom, dict):
        custom = {}

    # 编辑已存在的自定义供应商
    if vendor_key and vendor_key in custom:
        existing = custom[vendor_key] if isinstance(custom[vendor_key], dict) else {}
        normalized = normalize_provider_config(vendor_key, {**existing, **cfg}, builtin=False)
        custom[vendor_key] = normalized
        save_key = vendor_key
    else:
        # 新建：根据名称生成安全 key，避免与内置/已有冲突
        base_key = _safe_vendor_key(cfg.get("vendor_name") or cfg.get("name") or vendor_key)
        if base_key in BUILTIN_VENDOR_KEYS:
            base_key = f"custom_{base_key}"
        save_key = base_key
        n = 2
        while save_key in custom:
            save_key = f"{base_key}_{n}"
            n += 1
        custom[save_key] = normalize_provider_config(save_key, cfg, builtin=False)

    data["custom_providers"] = custom
    _save_settings_json(data)
    apply_provider_catalog(data)
    return {"vendor_key": save_key, "builtin": False}


def delete_provider(vendor_key: str) -> dict:
    """删除一个自定义供应商。内置供应商不允许删除（只能禁用）。"""
    vendor_key = (vendor_key or "").strip()
    if vendor_key in BUILTIN_VENDOR_KEYS:
        raise ValueError("内置供应商不可删除，可改为禁用。")
    data = _load_settings_json()
    custom = data.get("custom_providers", {})
    if not isinstance(custom, dict) or vendor_key not in custom:
        raise ValueError(f"未找到自定义供应商: {vendor_key}")
    del custom[vendor_key]
    data["custom_providers"] = custom
    # 同时清掉可能残留的 override
    overrides = data.get("provider_overrides", {})
    if isinstance(overrides, dict) and vendor_key in overrides:
        del overrides[vendor_key]
        data["provider_overrides"] = overrides
    _save_settings_json(data)
    apply_provider_catalog(data)
    return {"vendor_key": vendor_key, "deleted": True}


def set_provider_enabled(vendor_key: str, enabled: bool) -> dict:
    """启用/禁用某供应商（内置走 overrides，自定义直接改）。"""
    vendor_key = (vendor_key or "").strip()
    if vendor_key not in VENDORS_PRESETS:
        raise ValueError(f"未找到供应商: {vendor_key}")
    enabled = bool(enabled)
    data = _load_settings_json()
    if vendor_key in BUILTIN_VENDOR_KEYS:
        overrides = data.get("provider_overrides", {})
        if not isinstance(overrides, dict):
            overrides = {}
        ov = overrides.get(vendor_key, {})
        if not isinstance(ov, dict):
            ov = {}
        ov["enabled"] = enabled
        overrides[vendor_key] = ov
        data["provider_overrides"] = overrides
    else:
        custom = data.get("custom_providers", {})
        if isinstance(custom, dict) and vendor_key in custom and isinstance(custom[vendor_key], dict):
            custom[vendor_key]["enabled"] = enabled
            data["custom_providers"] = custom
    _save_settings_json(data)
    apply_provider_catalog(data)
    return {"vendor_key": vendor_key, "enabled": enabled}


apply_provider_catalog()


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
_vlm_analyze_cfg = _get_config(ACTIVE_VLM_ANALYZE_VENDOR, "VLM ANALYZE")

# ── LLM 相关 ──────────────────────────────────────────
LLM_API_KEY          = _llm_cfg["api_key"]
LLM_BASE_URL         = _llm_cfg["base_url"]
LLM_DASHSCOPE_HTTP   = _llm_cfg.get("dashscope_base_http", "")
MODEL_LLM            = _llm_cfg["models"]["llm"]

# ── 翻译专用 LLM（DeepSeek V4 Flash）──────────────────
_translate_cfg = _get_config(TRANSLATE_LLM_VENDOR, "TRANSLATE LLM")
TRANSLATE_MODEL = _translate_cfg["models"]["llm"]

# ── VLM 相关 ──────────────────────────────────────────
VLM_API_KEY          = _vlm_cfg["api_key"]
VLM_BASE_URL         = _vlm_cfg["base_url"]
VLM_DASHSCOPE_HTTP   = _vlm_cfg.get("dashscope_base_http", "")
VLM_COMPAT_URL       = _vlm_cfg["base_url"]   # OpenAI 兼容 URL
MODEL_VLM            = _vlm_cfg["models"]["vlm"]

# ── VLM 识图分析（分析用户上传的定妆照，写提示词）───────
VLM_ANALYZE_API_KEY  = _vlm_analyze_cfg["api_key"]
VLM_ANALYZE_BASE_URL = _vlm_analyze_cfg["base_url"]
MODEL_VLM_ANALYZE    = _vlm_analyze_cfg["models"].get("vlm", MODEL_VLM)

# ── IMG 相关 ──────────────────────────────────────────
IMG_API_KEY          = _img_cfg["api_key"]
IMG_BASE_URL         = _img_cfg["base_url"]
IMG_DASHSCOPE_HTTP   = _img_cfg.get("dashscope_base_http", "")
MODEL_IMG            = _img_cfg["models"]["img"]
IMG_EXTRA_PARAMS     = _img_cfg.get("extra_params", {})

MODEL_IMG_CAST       = MODEL_IMG
MODEL_IMG_STORY      = MODEL_IMG

# ── 向后兼容别名（让旧代码不报错）──────────────────────
API_KEY              = IMG_API_KEY       # 旧代码里 API_KEY 默认指生图厂商
APP_SECRET           = _img_cfg.get("app_secret", "")
BASE_URL             = IMG_BASE_URL
DASHSCOPE_BASE_HTTP  = IMG_DASHSCOPE_HTTP
EXTRA_PARAMS         = IMG_EXTRA_PARAMS
MODELS               = _img_cfg["models"]

# ================================================================
# ⚙️ 动态加载本地自定义模型名覆盖 (data/model_settings.json)
# ================================================================
def load_dynamic_settings():
    global MODEL_LLM, MODEL_VLM, MODEL_VLM_ANALYZE, MODEL_IMG, MODEL_IMG_CAST, MODEL_IMG_STORY, MODELS
    global ACTIVE_LLM_VENDOR, ACTIVE_VLM_VENDOR, ACTIVE_IMG_VENDOR, ACTIVE_VLM_ANALYZE_VENDOR
    global LLM_API_KEY, LLM_BASE_URL, VLM_API_KEY, VLM_BASE_URL, IMG_API_KEY, IMG_BASE_URL
    global VLM_ANALYZE_API_KEY, VLM_ANALYZE_BASE_URL
    import json
    settings_file = Path(__file__).resolve().parent.parent / "data" / "model_settings.json"
    if settings_file.exists():
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 1. 恢复厂商绑定（持久化厂商选择）
            stored_vendors = data.get("active_vendors", {})
            if stored_vendors.get("llm"):
                ACTIVE_LLM_VENDOR = stored_vendors["llm"]
            if stored_vendors.get("vlm"):
                ACTIVE_VLM_VENDOR = stored_vendors["vlm"]
            if stored_vendors.get("vlm_analyze"):
                ACTIVE_VLM_ANALYZE_VENDOR = stored_vendors["vlm_analyze"]
            if stored_vendors.get("img_cast") or stored_vendors.get("img_story"):
                ACTIVE_IMG_VENDOR = stored_vendors.get("img_cast") or stored_vendors.get("img_story") or ACTIVE_IMG_VENDOR

            # 2. 重新计算各厂商的 key/url（因为厂商可能变了）
            _llm_cfg = VENDORS_PRESETS.get(ACTIVE_LLM_VENDOR, {})
            _vlm_cfg = VENDORS_PRESETS.get(ACTIVE_VLM_VENDOR, {})
            _img_cfg = VENDORS_PRESETS.get(ACTIVE_IMG_VENDOR, {})
            _vlm_analyze_cfg = VENDORS_PRESETS.get(ACTIVE_VLM_ANALYZE_VENDOR, _vlm_cfg)
            LLM_API_KEY = _llm_cfg.get("api_key", "")
            LLM_BASE_URL = _llm_cfg.get("base_url", "")
            VLM_API_KEY = _vlm_cfg.get("api_key", "")
            VLM_BASE_URL = _vlm_cfg.get("base_url", "")
            IMG_API_KEY = _img_cfg.get("api_key", "")
            IMG_BASE_URL = _img_cfg.get("base_url", "")
            VLM_ANALYZE_API_KEY = _vlm_analyze_cfg.get("api_key", VLM_API_KEY)
            VLM_ANALYZE_BASE_URL = _vlm_analyze_cfg.get("base_url", VLM_BASE_URL)

            # 3. 加载模型名覆盖
            if data.get("MODEL_LLM"):
                MODEL_LLM = data["MODEL_LLM"]
            if data.get("MODEL_VLM"):
                MODEL_VLM = data["MODEL_VLM"]
            if data.get("MODEL_VLM_ANALYZE"):
                MODEL_VLM_ANALYZE = data["MODEL_VLM_ANALYZE"]

            if data.get("MODEL_IMG_CAST"):
                MODEL_IMG_CAST = data["MODEL_IMG_CAST"]
            elif data.get("MODEL_IMG"):
                MODEL_IMG_CAST = data["MODEL_IMG"]

            if data.get("MODEL_IMG_STORY"):
                MODEL_IMG_STORY = data["MODEL_IMG_STORY"]
            elif data.get("MODEL_IMG"):
                MODEL_IMG_STORY = data["MODEL_IMG"]

            MODEL_IMG = MODEL_IMG_STORY
            if MODELS and isinstance(MODELS, dict):
                MODELS["img"] = MODEL_IMG

            print(f"🧠 [model_presets] Loaded overrides: LLM={MODEL_LLM}, VLM={MODEL_VLM}, IMG_CAST={MODEL_IMG_CAST}, IMG_STORY={MODEL_IMG_STORY}")
            print(f"   Vendors: LLM={ACTIVE_LLM_VENDOR}, VLM={ACTIVE_VLM_VENDOR}, IMG={ACTIVE_IMG_VENDOR}")
        except Exception as e:
            print(f"⚠️ [model_presets] Failed to load dynamic settings: {e}")

load_dynamic_settings()


# ================================================================
# 🔄 动态厂商切换（供前端 UI / start_app.py 调用）
# ================================================================

# 厂商 key → .env 环境变量名的映射表（用于 API Key 读写）
VENDOR_ENV_KEY_MAP = {
    "aliyun_dashscope": "ALIYUN_DASHSCOPE_API_KEY",
    "deepseek_v4_pro":    "DEEPSEEK_API_KEY",
    "deepseek_v4_flash":  "DEEPSEEK_API_KEY",
    "doubao_v4":          "DOUBAO_V4_API_KEY",
    "doubao":             "DOUBAO_API_KEY",
    "nano_banana":        "NANO_BANANA_API_KEY",
    "starflow_liblib":    "STARFLOW_LIBLIB_API_KEY",
    "gribo_text":         "GRIBO_TEXT_API_KEY",
    "gribo_img":          "GRIBO_IMG_API_KEY",
    "volc_ark_vlm":       "VOLC_ARK_API_KEY",
}

# 角色标识 → 对应 ACTIVE_*_VENDOR 变量名
ROLE_TO_ACTIVE_VAR = {
    "llm":         "ACTIVE_LLM_VENDOR",
    "vlm":         "ACTIVE_VLM_VENDOR",
    "vlm_analyze": "ACTIVE_VLM_ANALYZE_VENDOR",
    "img_cast":    "ACTIVE_IMG_VENDOR",
    "img_story":   "ACTIVE_IMG_VENDOR",
}


def get_vendor_list(active_vendor_keys: dict = None) -> list:
    """
    返回厂商的公开信息列表（自动合并同 key 的变体，如 DeepSeek Pro/Flash → 一个 DeepSeek）。
    如果提供 active_vendor_keys，则只返回 has_key=true 的厂商 + 当前正在用的厂商。
    每项包含: vendor_key, vendor_name, base_url, has_key, masked_key, supported_roles,
               default_models, model_variants
    """
    active_keys_set = set(active_vendor_keys.values()) if active_vendor_keys else set()

    # 第一遍：收集所有有 key 的厂商（原始条目）
    raw = []
    for vk, cfg in VENDORS_PRESETS.items():
        # 已禁用的供应商不展示（除非正被某角色占用）
        if not cfg.get("enabled", True) and vk not in active_keys_set:
            continue
        has_key = bool(cfg.get("api_key", "").strip())
        if active_vendor_keys and not has_key and vk not in active_keys_set:
            continue
        api_key_raw = cfg.get("api_key", "")
        masked_key = api_key_raw[:8] + "***" if len(api_key_raw) > 12 else (api_key_raw[:4] + "***" if api_key_raw else "")
        models = cfg.get("models", {})
        supported_roles = []
        if models.get("llm"): supported_roles.append("llm")
        if models.get("vlm"): supported_roles.append("vlm")
        if models.get("img"): supported_roles.append("img")
        env_key = VENDOR_ENV_KEY_MAP.get(vk, "")
        raw.append({
            "vendor_key": vk,
            "vendor_name": cfg.get("vendor_name", vk),
            "base_url": cfg.get("base_url", ""),
            "has_key": has_key,
            "masked_key": masked_key,
            "supported_roles": supported_roles,
            "default_models": {
                "llm": models.get("llm", ""),
                "vlm": models.get("vlm", ""),
                "img": models.get("img", ""),
            },
            "_env_key": env_key,
            "_base_url": cfg.get("base_url", ""),
            "_model_names": list(dict.fromkeys(m for m in models.values() if m)),
        })

    # 第二遍：按 base_url 合并同厂商变体（同一 base_url = 同一厂商）
    # 如果某个 variant 是当前正在用的 active key，则不合并
    groups = {}       # base_url → merged entry
    alias_map = {}    # 所有 variant key → primary key
    for entry in raw:
        gk = entry["_base_url"]  # 主分组键：base_url
        if gk not in groups:
            groups[gk] = {
                "vendor_key": entry["vendor_key"],
                "vendor_name": _simplify_vendor_name(entry["vendor_name"]),
                "base_url": entry["base_url"],
                "has_key": entry["has_key"],
                "masked_key": entry["masked_key"],
                "supported_roles": list(entry["supported_roles"]),
                "default_models": {
                    "llm": entry["default_models"]["llm"],
                    "vlm": entry["default_models"]["vlm"],
                    "img": entry["default_models"]["img"],
                },
                "model_variants": list(entry["_model_names"]),
            }
        else:
            g = groups[gk]
            for r in entry["supported_roles"]:
                if r not in g["supported_roles"]:
                    g["supported_roles"].append(r)
            for role in ["llm", "vlm", "img"]:
                if not g["default_models"].get(role) and entry["default_models"].get(role):
                    g["default_models"][role] = entry["default_models"][role]
            for m in entry["_model_names"]:
                if m not in g["model_variants"]:
                    g["model_variants"].append(m)
        alias_map[entry["vendor_key"]] = groups[gk]["vendor_key"]

    # 更新 active_vendor_keys 中的别名 → 主 key（透明重映射）
    if active_vendor_keys:
        for role_key, vk in list(active_vendor_keys.items()):
            if vk in alias_map and alias_map[vk] != vk:
                active_vendor_keys[role_key] = alias_map[vk]

    # 剥离内部字段，产出最终列表
    result = []
    for gk, g in groups.items():
        g.pop("_aliases", None)
        g.pop("_env_key", None)
        g.pop("_base_url", None)
        g.pop("_model_names", None)
        # 补齐原始 API Key（本地桌面，安全可控）
        vk = g["vendor_key"]
        g["api_key"] = VENDORS_PRESETS.get(vk, {}).get("api_key", "")
        result.append(g)

    return result


def _simplify_vendor_name(name: str) -> str:
    """去掉厂商名中的模型后缀，如 'DeepSeek V4 Pro' → 'DeepSeek', 'Gribo Text' → 'Gribo'"""
    import re
    name = re.sub(r'\s*\(.*?\)\s*$', '', name)
    name = re.sub(r'\s+V\d+(\s+(Pro|Flash|Max|Lite|Turbo|Mini))?$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+Seedream\s*[\d.]+$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+(Text|Image|Img)(\s+.*)?$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+(ARK)(\s+.*)?$', '', name, flags=re.IGNORECASE)
    return name.strip()
    return name.strip()


def get_active_vendor_keys() -> dict:
    """
    返回当前各角色绑定的厂商 key。
    """
    return {
        "llm": ACTIVE_LLM_VENDOR,
        "vlm": ACTIVE_VLM_VENDOR,
        "vlm_analyze": ACTIVE_VLM_ANALYZE_VENDOR,
        "img_cast": ACTIVE_IMG_VENDOR,
        "img_story": ACTIVE_IMG_VENDOR,
    }


def get_vendor_env_key(vendor_key: str) -> str:
    """获取厂商对应的 .env 环境变量名"""
    return VENDOR_ENV_KEY_MAP.get(vendor_key, "")


def switch_vendor(role: str, vendor_key: str) -> dict:
    """
    动态切换某角色到指定厂商，并重新计算所有导出变量。

    role: "llm" | "vlm" | "vlm_analyze" | "img_cast" | "img_story"
    """
    global ACTIVE_LLM_VENDOR, ACTIVE_VLM_VENDOR, ACTIVE_VLM_ANALYZE_VENDOR, ACTIVE_IMG_VENDOR
    global LLM_API_KEY, LLM_BASE_URL, LLM_DASHSCOPE_HTTP, MODEL_LLM
    global VLM_API_KEY, VLM_BASE_URL, VLM_DASHSCOPE_HTTP, VLM_COMPAT_URL, MODEL_VLM
    global VLM_ANALYZE_API_KEY, VLM_ANALYZE_BASE_URL, MODEL_VLM_ANALYZE
    global IMG_API_KEY, IMG_BASE_URL, IMG_DASHSCOPE_HTTP, MODEL_IMG
    global MODEL_IMG_CAST, MODEL_IMG_STORY
    global TRANSLATE_MODEL, API_KEY, APP_SECRET, BASE_URL, DASHSCOPE_BASE_HTTP, EXTRA_PARAMS, MODELS

    cfg = VENDORS_PRESETS.get(vendor_key)
    if not cfg:
        raise ValueError(f"未找到厂商预设: {vendor_key}")
    if not cfg.get("enabled", True):
        raise ValueError(f"供应商已被禁用，无法绑定: {cfg.get('vendor_name', vendor_key)}")

    # 角色兼容性校验：该供应商需配置了对应角色的模型
    role_model_key = "img" if role in ("img_cast", "img_story") else (
        "vlm" if role in ("vlm", "vlm_analyze") else "llm")
    if not cfg.get("models", {}).get(role_model_key) and not cfg.get("model_variants"):
        print(f"⚠️ [model_presets] {cfg.get('vendor_name', vendor_key)} 未预置 {role_model_key} 模型名，仍允许绑定但需手动填写模型名")

    if role in ("llm",):
        ACTIVE_LLM_VENDOR = vendor_key
    elif role in ("vlm",):
        ACTIVE_VLM_VENDOR = vendor_key
    elif role in ("vlm_analyze",):
        ACTIVE_VLM_ANALYZE_VENDOR = vendor_key
    elif role in ("img_cast", "img_story"):
        ACTIVE_IMG_VENDOR = vendor_key
    else:
        raise ValueError(f"未知角色: {role}（应为 llm/vlm/vlm_analyze/img_cast/img_story）")

    # 重新计算所有导出变量
    _llm_cfg = _get_config(ACTIVE_LLM_VENDOR, "LLM")
    _vlm_cfg = _get_config(ACTIVE_VLM_VENDOR, "VLM")
    _img_cfg = _get_config(ACTIVE_IMG_VENDOR, "IMG")
    _vlm_analyze_cfg = _get_config(ACTIVE_VLM_ANALYZE_VENDOR, "VLM ANALYZE")

    LLM_API_KEY        = _llm_cfg["api_key"]
    LLM_BASE_URL       = _llm_cfg["base_url"]
    LLM_DASHSCOPE_HTTP = _llm_cfg.get("dashscope_base_http", "")
    MODEL_LLM          = _llm_cfg["models"]["llm"]

    VLM_API_KEY        = _vlm_cfg["api_key"]
    VLM_BASE_URL       = _vlm_cfg["base_url"]
    VLM_DASHSCOPE_HTTP = _vlm_cfg.get("dashscope_base_http", "")
    VLM_COMPAT_URL     = _vlm_cfg["base_url"]
    MODEL_VLM          = _vlm_cfg["models"].get("vlm", "")

    VLM_ANALYZE_API_KEY  = _vlm_analyze_cfg["api_key"]
    VLM_ANALYZE_BASE_URL = _vlm_analyze_cfg["base_url"]
    MODEL_VLM_ANALYZE    = _vlm_analyze_cfg["models"].get("vlm", MODEL_VLM)

    IMG_API_KEY        = _img_cfg["api_key"]
    IMG_BASE_URL       = _img_cfg["base_url"]
    IMG_DASHSCOPE_HTTP = _img_cfg.get("dashscope_base_http", "")
    MODEL_IMG          = _img_cfg["models"].get("img", "")
    IMG_EXTRA_PARAMS   = _img_cfg.get("extra_params", {})

    MODEL_IMG_CAST     = MODEL_IMG
    MODEL_IMG_STORY    = MODEL_IMG

    # 向后兼容别名
    API_KEY             = IMG_API_KEY
    APP_SECRET          = _img_cfg.get("app_secret", "")
    BASE_URL            = IMG_BASE_URL
    DASHSCOPE_BASE_HTTP = IMG_DASHSCOPE_HTTP
    EXTRA_PARAMS        = IMG_EXTRA_PARAMS
    MODELS              = _img_cfg["models"]

    result = {
        "role": role,
        "vendor_key": vendor_key,
        "vendor_name": cfg.get("vendor_name", vendor_key),
        "base_url": cfg.get("base_url", ""),
        "model": {
            "llm": MODEL_LLM,
            "vlm": MODEL_VLM,
            "vlm_analyze": MODEL_VLM_ANALYZE,
            "img_cast": MODEL_IMG_CAST,
            "img_story": MODEL_IMG_STORY,
        }
    }

    print(f"🔄 [model_presets] 切换 {role} → {cfg.get('vendor_name')} | LLM={MODEL_LLM}, VLM={MODEL_VLM}, IMG={MODEL_IMG}")
    return result


# ================================================================
# 📝 模型名历史记忆（供前端 model_history 下拉）
# ================================================================

def get_model_history(slot_key: str) -> list:
    """读取某 slot 的历史模型名列表（不含当前值）"""
    import json
    settings_file = Path(__file__).resolve().parent.parent / "data" / "model_settings.json"
    try:
        if settings_file.exists():
            with open(settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            history = data.get("model_history", {}).get(slot_key, [])
            if isinstance(history, list):
                return history
    except Exception:
        pass
    return []


def save_model_history(slot_key: str, model_name: str):
    """保存某 slot 的当前模型名到历史列表（去重，最大 20 条）"""
    import json
    settings_file = Path(__file__).resolve().parent.parent / "data" / "model_settings.json"

    data = {}
    if settings_file.exists():
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass

    history = data.get("model_history", {})
    if not isinstance(history, dict):
        history = {}

    slot_history = history.get(slot_key, [])
    if not isinstance(slot_history, list):
        slot_history = []

    # 去重 + 加到头 + 截断
    if model_name in slot_history:
        slot_history.remove(model_name)
    slot_history.insert(0, model_name)
    slot_history = slot_history[:20]

    history[slot_key] = slot_history
    data["model_history"] = history

    settings_file.parent.mkdir(parents=True, exist_ok=True)
    with open(settings_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

