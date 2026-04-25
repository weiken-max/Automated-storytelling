"""
🚀 视觉动力核心 (src/image_engine.py) — v4.3 错误预警版
======================================================
功能：一键切换生图厂商 (阿里/豆包/Gemini)，统一接口调用。
新增：精准识别余额不足/限流/鉴权错误，立即中文报警。
"""

import os, sys, json, base64, time, asyncio, httpx, requests
from pathlib import Path
from io import BytesIO
from PIL import Image
import io

# ── 自动对齐项目根目录 ──
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.style_config import (
    IMG_API_KEY, IMG_BASE_URL, MODEL_IMG, IMG_EXTRA_PARAMS,
    STYLE_ANCHOR, NEGATIVE_PROMPT, IMG_SIZE,
    CHARACTER_REF_MAP, REFS_OTHER
)
from src.model_presets import ACTIVE_IMG_VENDOR

# ================================================================
# 0. 统一错误预警系统
# ================================================================

class APIQuotaError(Exception):
    """API 余额耗尽或配额超限，需要立即人工介入"""
    pass

class APIAuthError(Exception):
    """API Key 无效或鉴权失败"""
    pass

def _alert(vendor_name: str, error_type: str, detail: str):
    """打印醒目的中文警报，确保用户不会漏看"""
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  🚨 【紧急警报】{vendor_name} — {error_type}")
    print(f"  📋 详情: {detail}")
    print(f"  ⚠️  请立即检查并处理，生产流程已中断！")
    print(f"{sep}\n")

def _check_http_error(status_code: int, response_text: str, vendor_name: str):
    """
    统一 HTTP 错误分析器。
    遇到余额/鉴权问题直接抛出异常，让流程停下来。
    遇到限流则只警告（可继续重试）。
    """
    text_lower = response_text.lower()

    # ── 余额耗尽 / 配额超限 ──
    quota_keywords = [
        "insufficient balance", "余额不足", "balance", "quota exceeded",
        "arrearage", "欠费", "insufficient_quota", "billing",
        "payment required", "account balance", "credit",
    ]
    if status_code == 402 or any(k in text_lower for k in quota_keywords):
        _alert(vendor_name, "❌ 余额不足 / 配额超限",
               f"HTTP {status_code} | 响应: {response_text[:200]}")
        raise APIQuotaError(f"{vendor_name} 余额耗尽：{response_text[:200]}")

    # ── API Key 无效 / 鉴权失败 ──
    auth_keywords = [
        "invalid api key", "unauthorized", "authentication", "api key",
        "invalid_api_key", "permission denied", "access denied",
        "forbidden", "invalid key", "key not found",
    ]
    if status_code == 401 or status_code == 403 or any(k in text_lower for k in auth_keywords):
        _alert(vendor_name, "🔑 API Key 无效 / 鉴权失败",
               f"HTTP {status_code} | 响应: {response_text[:200]}")
        raise APIAuthError(f"{vendor_name} 鉴权失败：{response_text[:200]}")

    # ── 限流（429）—— 警告但不中断，由调用方决定是否重试 ──
    if status_code == 429:
        _alert(vendor_name, "⏳ 触发限流 (429 Rate Limit)",
               f"响应: {response_text[:200]} | 建议：在 model_presets.py 中增大 cooldown 值")
        # 不抛异常，返回 False 让调用方处理

    # ── 服务器错误（5xx）──
    if status_code >= 500:
        print(f"\n  ⚠️  [{vendor_name}] 服务端错误 HTTP {status_code}，可能是临时故障，建议稍后重试。")
        print(f"  响应: {response_text[:200]}\n")


# ================================================================
# 1. 冷却锁管理
# ================================================================
_last_gen_time = 0

async def _wait_for_cooldown():
    global _last_gen_time
    cooldown = IMG_EXTRA_PARAMS.get("cooldown", 0)
    if cooldown <= 0: return
    elapsed = time.time() - _last_gen_time
    if elapsed < cooldown and _last_gen_time > 0:
        wait = cooldown - elapsed
        print(f"  └─ ⏳ [常规冷却] 强制休眠 {wait:.1f} 秒...")
        await asyncio.sleep(wait)

def _update_last_gen_time():
    global _last_gen_time
    _last_gen_time = time.time()


# ================================================================
# 1.5 宫格提示词包装器 (V5.0 Gemini 专供)
# ================================================================

def wrap_grid_prompt(batch_panels: list) -> str:
    if len(batch_panels) != 4:
        while len(batch_panels) < 4:
            batch_panels.append({"shot_id": "VOID", "image_prompt": "Empty white background, no content."})

    template = (
        "[LAYOUT CONSTRAINT: MANDATORY 2x2 GRID]\n"
        "You MUST divide the 16:9 canvas into 4 EQUAL-SIZED RECTANGULAR PANELS strictly in 2 rows and 2 columns. "
        "Use thin white gutter lines to separate the 4 panels. DO NOT create more or fewer than 4 panels.\n\n"
        "[PANEL INDEXING]\n"
        f"- Top-Left: {batch_panels[0]['image_prompt']}\n"
        f"- Top-Right: {batch_panels[1]['image_prompt']}\n"
        f"- Bottom-Left: {batch_panels[2]['image_prompt']}\n"
        f"- Bottom-Right: {batch_panels[3]['image_prompt']}\n\n"
        "[STYLE & COMPOSITION]\n"
        "Each panel should be an independent 16:9 landscape cinematic shot. No collage, no overlapping. "
        "Strictly follow the reference characters for each panel."
    )
    return template


# ================================================================
# 2. 各厂商具体适配器
# ================================================================

# --- [适配器 A] 豆包 (Volcengine Ark SDK) ---
async def _generate_doubao(prompt: str, image_refs: list = None, size: str = None) -> bytes:
    VENDOR = "豆包 (火山方舟)"
    from volcenginesdkarkruntime import Ark
    client = Ark(api_key=IMG_API_KEY, base_url=f"{IMG_BASE_URL.rstrip('/')}/api/v3")

    payload_images = []
    if image_refs:
        for ref in image_refs:
            if ref.startswith("data:"): payload_images.append(ref)
            else: payload_images.append(f"data:image/png;base64,{ref}")

    use_size = size or IMG_EXTRA_PARAMS.get("size", "1312x736")
    use_stream = IMG_EXTRA_PARAMS.get("stream", True)

    try:
        resp = client.images.generate(
            model=MODEL_IMG,
            prompt=prompt,
            image=payload_images if payload_images else None,
            size=use_size,
            response_format="url",
            stream=use_stream,
            watermark=False
        )

        img_url = None
        if use_stream:
            for event in resp:
                if event and event.type == "image_generation.partial_succeeded":
                    img_url = event.url
                    break
        else:
            if resp.data: img_url = resp.data[0].url

        if img_url:
            r = requests.get(img_url, timeout=60)
            return r.content

    except APIQuotaError:
        raise  # 向上传播，中断流程
    except APIAuthError:
        raise
    except Exception as e:
        err_str = str(e).lower()
        # SDK 层面的错误也做关键词匹配
        if any(k in err_str for k in ["balance", "quota", "billing", "arrearage", "insufficient"]):
            _alert(VENDOR, "❌ 余额不足 / 配额超限", str(e))
            raise APIQuotaError(str(e))
        if any(k in err_str for k in ["auth", "unauthorized", "invalid key", "api key"]):
            _alert(VENDOR, "🔑 API Key 无效", str(e))
            raise APIAuthError(str(e))
        print(f"  └─ ❌ [{VENDOR}] 生图异常: {e}")
    return None


# --- [适配器 B] 阿里云 (DashScope) ---
async def _generate_aliyun(prompt: str, image_refs: list = None, size: str = None) -> bytes:
    VENDOR = "阿里云 DashScope"
    from dashscope import MultiModalConversation
    import dashscope
    dashscope.base_http_api_url = IMG_EXTRA_PARAMS.get("dashscope_base_http", "https://dashscope.aliyuncs.com/api/v1")

    content = []
    if image_refs:
        for ref in image_refs:
            if os.path.exists(ref): content.append({"image": f"file://{os.path.abspath(ref)}"})
            else: content.append({"image": ref})
    content.append({"text": prompt})

    def _call():
        return MultiModalConversation.call(
            api_key=IMG_API_KEY,
            model=MODEL_IMG,
            messages=[{"role": "user", "content": content}],
            negative_prompt=NEGATIVE_PROMPT,
            parameters={"size": size or IMG_SIZE}
        )

    response = await asyncio.to_thread(_call)

    # 阿里云返回的错误码分析
    status = response.status_code
    if status != 200:
        err_text = getattr(response, 'message', '') or getattr(response, 'code', '') or str(response)
        err_lower = str(err_text).lower()

        if status == 402 or any(k in err_lower for k in ["arrearage", "balance", "quota", "欠费"]):
            _alert(VENDOR, "❌ 余额不足 / 账户欠费",
                   f"code={getattr(response, 'code', '?')} | {err_text}")
            raise APIQuotaError(f"{VENDOR}: {err_text}")

        if status in (401, 403) or "auth" in err_lower or "invalid" in err_lower:
            _alert(VENDOR, "🔑 API Key 无效 / 鉴权失败",
                   f"code={getattr(response, 'code', '?')} | {err_text}")
            raise APIAuthError(f"{VENDOR}: {err_text}")

        _check_http_error(status, str(err_text), VENDOR)
        print(f"  └─ ❌ [{VENDOR}] 错误 HTTP {status}: {err_text}")
        return None

    img_url = response.output.choices[0].message.content[0].get("image")
    if img_url:
        r = requests.get(img_url, timeout=60)
        return r.content
    return None


# --- [适配器 D] OpenAI 兼容生图接口 (gribo_img 专用) ---
async def _generate_openai_images(prompt: str, image_refs: list = None, size: str = None) -> bytes:
    """使用 OpenAI /v1/images/generations 公岗调用生图（gribo 代理支持）"""
    VENDOR = "Gribo Image (OpenAI层)"
    from openai import OpenAI as _OAI
    client = _OAI(
        api_key=IMG_API_KEY,
        base_url=IMG_BASE_URL.rstrip("/") + "/v1"
    )
    try:
        # 如果有参考图，拼接成文字描述传入（该接口不支持图片输入）
        resp = client.images.generate(
            model=MODEL_IMG,
            prompt=prompt[:4000],  # 防止prompt过长
            n=1,
            size="1792x1024",  # 16:9最接近的尺寸
            response_format="b64_json"
        )
        if resp.data and resp.data[0].b64_json:
            return base64.b64decode(resp.data[0].b64_json)
        print(f"  └─ ⚠️  [{VENDOR}] 返回了空数据")
        return None
    except Exception as e:
        err_str = str(e).lower()
        if any(k in err_str for k in ["balance", "quota", "billing", "insufficient"]):
            _alert(VENDOR, "❌ 余额不足", str(e))
            raise APIQuotaError(str(e))
        if any(k in err_str for k in ["auth", "unauthorized", "invalid", "forbidden"]):
            _alert(VENDOR, "🔑 鉴权失败", str(e))
            raise APIAuthError(str(e))
        print(f"  └─ ❌ [{VENDOR}] 生图异常: {e}")
        return None

async def _generate_gemini(prompt: str, image_refs: list = None, size: str = None) -> bytes:
    VENDOR = "Gemini 中转站 (gemini_proxy_v3)"
    parts = [{"text": prompt}]
    if image_refs:
        for ref in image_refs:
            parts.append({
                "inlineData": {
                    "mimeType": "image/jpeg",
                    "data": ref.replace("data:image/png;base64,", "").replace("data:image/jpeg;base64,", "")
                }
            })
    
    # 修复：防止 URL 拼接出现 double /v1/v1beta 情况 (针对 Gribo 代理优化)
    clean_base = IMG_BASE_URL.rstrip('/')
    if clean_base.endswith("/v1"):
        clean_base = clean_base[:-3]
    
    gen_endpoint = IMG_EXTRA_PARAMS.get("gen_endpoint", "/v1beta/models/{model}:generateContent")
    url = f"{clean_base}{gen_endpoint.replace('{model}', MODEL_IMG)}?key={IMG_API_KEY}"
    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "aspectRatio": "16:9"
        }
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code == 200:
            result = resp.json()
            candidates = result.get("candidates", [])
            if candidates:
                res_parts = candidates[0].get("content", {}).get("parts", [])
                for p in res_parts:
                    if "inlineData" in p:
                        return base64.b64decode(p["inlineData"]["data"])
            # 返回200但没有图片，可能被内容过滤
            print(f"  └─ ⚠️  [{VENDOR}] 返回200但未包含图片（可能触发内容过滤）")
            return None

        # 非200的错误分析
        resp_text = resp.text
        # 会抛出 APIQuotaError / APIAuthError，或只打印警告
        _check_http_error(resp.status_code, resp_text, VENDOR)
        print(f"  └─ ❌ [{VENDOR}] HTTP {resp.status_code}: {resp_text[:300]}")
        return None


# ================================================================
# 3. 统一分发门面 (Facade)
# ================================================================
def _encode_and_resize(path: Path):
    """读取图片并按需进行等比例缩放压缩 (Armor-Plated Payload)"""
    try:
        with Image.open(path) as img:
            MAX_SIZE = 768
            if max(img.size) > MAX_SIZE:
                ratio = MAX_SIZE / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            buffered = io.BytesIO()
            img.convert("RGB").save(buffered, format="JPEG", quality=85)
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"  ⚠️ [ImageEngine] 编码图片失败 {path.name}: {e}")
        return None

async def generate_image(prompt: str,
                         image_refs: list = None,
                         tags: list = None,
                         scenes: list = None,
                         size: str = None,
                         vendor_key: str = None) -> bytes:
    """
    通用生图接口。
    遇到余额/鉴权错误会抛出 APIQuotaError / APIAuthError，让调用方知道需要人工介入。
    """
    await _wait_for_cooldown()

    vendor = vendor_key or ACTIVE_IMG_VENDOR

    # ── 🚩 V7.8 物理路经对位补丁：强制转换路径为 B64 ──
    final_image_refs = []
    
    # 1. 如果传入的是物理路径列表 (V7.2+ 显式注入的 anchor_look)
    if image_refs:
        for ref_path in image_refs:
            if isinstance(ref_path, str) and not ref_path.startswith("data:"):
                p = Path(ref_path)
                if p.exists():
                    b64 = _encode_and_resize(p)
                    if b64: final_image_refs.append(b64)
                    else: print(f"      ⚠️  [ImageEngine] 物理图编码失败: {p}")
                else: 
                    # 如果不是文件路径，可能是 base64 字符串本身或其他
                    final_image_refs.append(ref_path)
            else:
                final_image_refs.append(ref_path)

    # 2. 如果传入的是角色标签或场景标签 (旧版逻辑)
    if not final_image_refs and (tags or scenes):
        if tags:
            for tag in tags:
                ref_dir = CHARACTER_REF_MAP.get(tag)
                if ref_dir and ref_dir.exists():
                    for img_p in ref_dir.glob("triple_view.png"):
                        b64 = _encode_and_resize(img_p)
                        if b64: final_image_refs.append(b64)

    # ── 🚩 V6.6 核心一致性协议：视觉隔离 (Crowd Suppression) ──
    # 如果完全没有主角标签，则向 Prompt 注入高权重的负向压制，防止路人撞脸
    if not any(t in ["child", "youth", "middle", "elderly", "protagonist"] for t in (tags or [])):
        # 强制注入高权重负向词（模拟 Stable Diffusion 权重语法，某些 VLM 能识别此类强调）
        CROWD_SUPPRESSION = "\n[NEGATIVE CONSTRAINT: AVOID THE FOLLOWING CHARACTER FEATURES AT ALL COSTS: (red jacket:1.5), (black messy hair:1.5)]"
        prompt += CROWD_SUPPRESSION
        print(f"      🛡️  [CrowdSuppression] 已注入主角特征压制协议。")

    if STYLE_ANCHOR not in prompt:
        full_prompt = f"Style: {STYLE_ANCHOR}\nAction: {prompt}"
    else:
        full_prompt = prompt

    result_bytes = None

    if "doubao" in vendor or "seedream" in vendor:
        result_bytes = await _generate_doubao(full_prompt, final_image_refs, size)
    elif "aliyun" in vendor or "dashscope" in vendor:
        result_bytes = await _generate_aliyun(full_prompt, final_image_refs, size)
    elif "gemini" in vendor or "banana" in vendor or "gribo" in vendor:
        result_bytes = await _generate_gemini(full_prompt, final_image_refs, size)
    elif "starflow" in vendor:
        print("  ⚠️ 星流 (LibLib) 适配器将在后续阶段完善。")
        result_bytes = None
    else:
        print(f"  ❌ 未知厂商 [ {vendor} ]，无法分发生图任务。")

    if result_bytes:
        _update_last_gen_time()

    return result_bytes

# ================================================================
# 4. 高层包装器 (供 V6 同步调用)
# ================================================================
def generate_grid_image(batch_metadata: list, output_path: Path) -> bool:
    """批量生成 2x2 宫格图并保存 (集成多阶段人生样张与主角出现判定)"""
    prompts_list = [s.get('visual_prompt', s.get('shot_summary', '')) for s in batch_metadata]
    
    # ── 🚨 V6.5 核心逻辑：智能搜集多阶段标签 ──
    batch_tags = set()
    batch_scenes = set()
    batch_refs = set() # 🧪 V7.3 物理参考
    
    has_any_protagonist = False
    for s in batch_metadata:
        # 检测主角是否现身
        is_protagonist_here = s.get("has_protagonist", False)
        # 兼容性兜底：如果没打 has_protagonist 标签但 character_tags 里有主角，也算现身
        if not is_protagonist_here:
            chars = s.get("character_tags", [])
            if any(c in ["主角", "protagonist"] for c in chars):
                is_protagonist_here = True

        if is_protagonist_here:
            has_any_protagonist = True
            # 🧪 V8.3 [Phase2 修复] 取消"无字段就静默回退 middle"的隐患。
            # 优先级：1) shot 自带 protagonist_stage  2) 反推自 anchor_look 路径  3) middle 兜底 + 显式告警
            stage = s.get("protagonist_stage")
            if not stage:
                a_look_str = str(s.get("anchor_look") or "")
                for known_stage in ("child", "youth", "middle", "elderly"):
                    if f"protagonist_{known_stage}" in a_look_str:
                        stage = known_stage
                        break
            if not stage:
                stage = "middle"
                print(
                    f"      ⚠️ [Stage] shot {s.get('shot_id')} 无法识别人生阶段，"
                    "回退 middle（请检查 step1 是否正确写入 protagonist_stage）。"
                )
            batch_tags.add(stage)
        
        # 配角与其他标签仍按原逻辑（可选）
        chars = s.get("character_tags", [])
        if any(c in ["配角", "supporting"] for c in chars):
            batch_tags.add("supporting")

        s_tag = s.get("scene_tag")
        if s_tag and s_tag != "null":
            batch_scenes.add(s_tag)
            
        # 🧪 V7.3 核心：搜集物理定妆照路径
        a_look = s.get("anchor_look")
        if a_look and Path(a_look).exists():
            batch_refs.add(a_look)

    # 包装提示词
    panels = [{"image_prompt": p} for p in prompts_list]
    full_prompt = wrap_grid_prompt(panels)
    
    print(f"    🔍 [V7.3 Physical Binding] 需求：主角={has_any_protagonist} | 物理定妆={len(batch_refs)}张 | 阶段={batch_tags}")

    try:
        # ── 🚨 V6.6 asyncio 并发补丁 ──
        coro = generate_image(
            full_prompt, 
            image_refs=list(batch_refs), # 🔒 注入物理路径列表
            tags=list(batch_tags), 
            scenes=list(batch_scenes)
        )
        
        try:
            # 尝试获取当前线程已有的事件循环
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果 Loop 正在运行，使用 run_coroutine_threadsafe 或直接 run（取决于环境）
                # 这里我们采用一种更鲁棒的同步执行方案
                import nest_asyncio
                nest_asyncio.apply()
                img_bytes = loop.run_until_complete(coro)
            else:
                img_bytes = loop.run_until_complete(coro)
        except RuntimeError:
            # 如果当前线程没 Loop，则创建一个新的
            img_bytes = asyncio.run(coro)

        if img_bytes:
            output_path.write_bytes(img_bytes)
            return True
        return False
    except Exception as e:
        print(f"  [ERR] generate_grid_image 失败: {e}")
        return False
