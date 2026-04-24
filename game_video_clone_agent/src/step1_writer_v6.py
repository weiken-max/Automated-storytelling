"""
🚀 视觉小说导播引擎 V7.1 - 物理隔离一致性版 (step1_director_v7.py)
==============================================================
重构：
1. 物理锁：按 Shot ID 强制隔离主角年龄，GPT 无法跨段干扰。
2. 语义补丁：物理剔除、合并旁白中的孤儿标点，杜绝音频丢失。
3. 解析锁：强开启 JSON 模式，彻底封死“通用保底词”污染风险。
# 🧪 V9.2 全局风格锁定：氰化物风格 (Cyanide and Happiness)
STYLE_ANCHOR = "Cyanide and Happiness comic style, minimalist stick-figure character, bold black outlines, flat colors, no shading, humorous and simple illustration."
"""

import json
import re
import sys
import base64
import time
from datetime import datetime
from pathlib import Path
from openai import OpenAI

# ── Windows GBK 终端编码修复 ──
if hasattr(sys.stdout, "buffer"):
    from io import TextIOWrapper
    sys.stdout = TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 自动对齐项目根目录 ──
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.style_config import (
    VLM_API_KEY, VLM_BASE_URL, MODEL_VLM,
    FULL_STORY_V6_PATH, NARRATIVE_V6_PATH,
    STYLE_ANCHOR, BATCH_SIZE, timeout,
    CURRENT_PROJECT_PATH, IMG_DIR, AUDIO_DIR,
    SCRIPT_DIR, REFS_DIR, OUTPUT_DIR
)
import shutil

# 🧠 VISUAL DIRECTOR V7.1 - 物理隔离版
VISUAL_SYSTEM_PROMPT = """You are a Cinematic Director. 
Task: Translate my Chinese narration into High-Quality Stable Diffusion Prompts (English).

【PROTAGONIST ANCHOR】 (MUST USE FOR CHARACTER): {CHARACTER_ANCHOR}

【VISUAL RULES】:
1. **Consistency**: Use ONLY the above Anchor for the protagonist's look. Do NOT mix other ages or clothes.
2. **Crowd Separation**: NPCs should be blurry or distinct from the protagonist.
3. **Style**: {STYLE_ANCHOR}. Everything MUST be flat 2D comic style. NO 3D, NO realism.
4. **Cinematography**: Add lighting, angle, and atmosphere based on narration.

    Output purely in JSON format: 
    {{ "prompts": [
        {{"shot_id": "0001", "visual_prompt": "Prompt text...", "has_protagonist": true}}
    ] }}"""

# 质量闸门参数（可按项目偏好微调）
PROMPT_MIN_LEN = 60
PROMPT_MAX_RETRIES = 3
PROMPT_MIN_UNIQUE_RATIO = 0.70

def _looks_like_generic_fallback(prompt_text: str) -> bool:
    """识别明显退化的通用兜底句。"""
    p = (prompt_text or "").strip().lower()
    return (
        p.startswith("cinematic historical flat illustration for")
        or p == "cinematic shot"
        or ("high quality" in p and len(p) < 120)
    )

def _validate_prompt_payload(parsed: dict, expected_count: int):
    """严格校验 VLM 返回结构与提示词质量。"""
    if not isinstance(parsed, dict):
        return False, "返回结果不是 JSON 对象"

    prompts = parsed.get("prompts")
    if not isinstance(prompts, list):
        return False, "缺少 prompts 数组"
    if len(prompts) != expected_count:
        return False, f"prompts 数量不匹配: expected={expected_count}, got={len(prompts)}"

    cleaned = []
    generic_hits = 0
    for idx, item in enumerate(prompts):
        if not isinstance(item, dict):
            return False, f"prompts[{idx}] 不是对象"
        vp = (item.get("visual_prompt") or "").strip()
        if len(vp) < PROMPT_MIN_LEN:
            return False, f"prompts[{idx}] 文本过短({len(vp)}<{PROMPT_MIN_LEN})"
        if _looks_like_generic_fallback(vp):
            generic_hits += 1
        cleaned.append(vp)

    unique_ratio = len(set(cleaned)) / max(1, len(cleaned))
    if unique_ratio < PROMPT_MIN_UNIQUE_RATIO:
        return False, f"批次提示词重复率过高(unique_ratio={unique_ratio:.2f})"
    if generic_hits > 0:
        return False, f"检测到通用退化提示词 {generic_hits} 条"

    return True, "ok"

def _dump_prompt_failure_log(chunk_shots: list, reason: str, raw_text: str):
    """失败可观测：落盘原始返回和失败原因，便于复盘。"""
    try:
        logs_dir = BASE_DIR / "data" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        shot_ids = [s.get("shot_id", "?") for s in chunk_shots]
        payload = {
            "ts": ts,
            "reason": reason,
            "shot_ids": shot_ids,
            "input": chunk_shots,
            "raw_text": raw_text or ""
        }
        log_path = logs_dir / f"step1_prompt_fail_{ts}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"    🧾 失败日志已保存: {log_path}")
    except Exception as e:
        print(f"    ⚠️ 失败日志写入告警: {e}")

def encode_image_to_b64(image_path: Path):
    """同 image_engine 同款的高质量图片编码"""
    from PIL import Image
    import io
    try:
        with Image.open(image_path) as img:
            # 缩放至 VLM 友好尺寸
            img.thumbnail((512, 512))
            buffered = io.BytesIO()
            img.convert("RGB").save(buffered, format="JPEG", quality=85)
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"      ⚠️  图片编码失败: {e}")
        return None

def call_vlm_visual_batch(chunk_shots: list, era: str, anchor_prompt: str, anchor_image_b64: str = None):
    """视觉翻译枢纽 (V8.0 多模态物理对位版)"""
    client = OpenAI(api_key=VLM_API_KEY, base_url=VLM_BASE_URL)
    
    shots_input = json.dumps(chunk_shots, ensure_ascii=False)
    system_prompt = VISUAL_SYSTEM_PROMPT.format(
        ERA=era, 
        CHARACTER_ANCHOR=anchor_prompt, 
        STYLE_ANCHOR=STYLE_ANCHOR
    )

    # 构造多模态消息：让导播“亲眼看见”主角定妆照
    content = [{"type": "text", "text": f"Character physical reference is provided in the image. Narration to translate:\n{shots_input}"}]
    if anchor_image_b64:
        content.insert(0, {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{anchor_image_b64}"}
        })

    last_reason = "unknown"
    last_raw_text = ""
    for attempt in range(1, PROMPT_MAX_RETRIES + 1):
        try:
            user_content = list(content)
            if attempt > 1:
                user_content.append({
                    "type": "text",
                    "text": (
                        "Previous output was invalid/too generic. "
                        "Regenerate strictly: one distinct cinematic prompt per shot; "
                        "include action, setting, camera angle, lighting and atmosphere; "
                        "avoid generic filler text."
                    )
                })

            response = client.chat.completions.create(
                model=MODEL_VLM,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                response_format={"type": "json_object"},
                timeout=timeout
            )
            raw_text = (response.choices[0].message.content or "").strip()
            last_raw_text = raw_text
            # 兼容处理 Markdown 干扰
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[-1].split("```")[0].strip()

            parsed = json.loads(raw_text)
            ok, reason = _validate_prompt_payload(parsed, expected_count=len(chunk_shots))
            if ok:
                if attempt > 1:
                    print(f"    ✅ VLM 第 {attempt} 次重试通过质检。")
                return parsed

            last_reason = reason
            print(f"    ⚠️ VLM 第 {attempt} 次返回不合格: {reason}")
            _dump_prompt_failure_log(chunk_shots, f"attempt_{attempt}: {reason}", last_raw_text)
            time.sleep(1.2)
        except Exception as e:
            last_reason = f"VLM 调用/解析异常: {e}"
            print(f"    ⚠️ VLM 第 {attempt} 次异常: {e}")
            _dump_prompt_failure_log(chunk_shots, f"attempt_{attempt}: {last_reason}", last_raw_text)
            time.sleep(1.2)

    raise RuntimeError(
        f"VLM 连续 {PROMPT_MAX_RETRIES} 次未产出合格逐镜头提示词，已中断。"
        f"最后原因: {last_reason}"
    )

def get_stage_anchor(shot_id: int, master_plan: dict):
    """根据分镜 ID 物理对位生命阶段，并返回物理图片路径"""
    physical_anchors = master_plan.get("physical_char_anchors", {})
    stage_map = master_plan.get("stage_map", [])
    
    current_stage = "middle"
    for entry in stage_map:
        if entry["start_shot"] <= shot_id <= entry["end_shot"]:
            current_stage = entry["stage"]
            break
    # 🧪 V7.2 返回物理文件路径，确保生图引擎能“找得着”图
    return physical_anchors.get(current_stage, physical_anchors.get("middle", ""))

def validate_stage_map(stage_map: list):
    """轻量校验 stage_map 的结构与区间重叠，仅告警不阻断。"""
    if not isinstance(stage_map, list) or not stage_map:
        return

    normalized = []
    for idx, entry in enumerate(stage_map):
        if not isinstance(entry, dict):
            print(f"  ⚠️ [StageMap] 第 {idx+1} 项不是对象，已跳过校验。")
            continue

        stage = entry.get("stage", "unknown")
        start = entry.get("start_shot")
        end = entry.get("end_shot")

        if not isinstance(start, int) or not isinstance(end, int):
            print(f"  ⚠️ [StageMap] 阶段 {stage} 的 start_shot/end_shot 不是整数。")
            continue
        if start > end:
            print(f"  ⚠️ [StageMap] 阶段 {stage} 区间非法: start_shot({start}) > end_shot({end})。")
            continue

        normalized.append((start, end, stage))

    normalized.sort(key=lambda x: (x[0], x[1]))

    for i in range(1, len(normalized)):
        prev_start, prev_end, prev_stage = normalized[i - 1]
        cur_start, cur_end, cur_stage = normalized[i]
        if cur_start <= prev_end:
            print(
                "  ⚠️ [StageMap] 检测到区间重叠: "
                f"{prev_stage}[{prev_start}-{prev_end}] 与 "
                f"{cur_stage}[{cur_start}-{cur_end}]。"
            )

def main():
    global_topic = "未知主题"
    if CURRENT_PROJECT_PATH.exists():
        with open(CURRENT_PROJECT_PATH, "r", encoding="utf-8") as f:
            global_topic = json.load(f).get("project_name", "未知主题")
    
    print(f"\n🎬 [Step 1B] 导播引擎 V7.1 启动 (强制物理隔离版)...")

    if not FULL_STORY_V6_PATH.exists():
        raise RuntimeError(f"Step1 前置缺失：剧本不存在 -> {FULL_STORY_V6_PATH}")

    with open(FULL_STORY_V6_PATH, "r", encoding="utf-8") as f:
        full_data = json.load(f)

    meta = full_data.get("metadata", {})
    master_plan = full_data.get("master_design", {})
    full_narration = master_plan.get("full_narration", "")
    validate_stage_map(master_plan.get("stage_map", []))

    # 🧪 V14.0 工业级资产超量清场：启动新副本前，全量抹除库内素材 (杜绝所有旧项目残留)
    print(f"  ├─ 物理隔离：正在强制闪抹历史生产路径...")
    for target_dir in [IMG_DIR, AUDIO_DIR, OUTPUT_DIR]: # 移除了 SCRIPT_DIR 和 REFS_DIR 保留原始物料
        if target_dir.exists():
            try:
                shutil.rmtree(target_dir)
            except Exception as e:
                print(f"  ⚠️  清理 {target_dir.name} 告警 (进程占用中?): {e}")
        target_dir.mkdir(parents=True, exist_ok=True)

    if NARRATIVE_V6_PATH.exists():
        try:
            NARRATIVE_V6_PATH.unlink()
            print(f"  ├─ 物理隔离：旧版分镜剧本已由于物理由于删除。")
        except Exception as e:
            print(f"  ⚠️  物理隔离告警：无法删除旧剧本 ({e})")

    # 1. 语义补丁：合并标点，防止音频丢失
    # 我们先按标签拆分，但如果某一段只有标点，我们强制将其合并到前一个肉段
    raw_parts = re.split(r'\[?CUT_?\d+\]?', full_narration)
    clean_parts = []
    for p in raw_parts:
        text = p.strip().lstrip(':： ')
        if not text: continue
        # 🧪 V8.0 物理补丁：精确匹配标点残留
        if re.fullmatch(r'[\s，。！？、…“”"\'\']+', text):
            if clean_parts: clean_parts[-1] += text
            continue
        clean_parts.append(text)
    
    all_shots = []
    for idx, part in enumerate(clean_parts):
        sid = idx + 1
        all_shots.append({
            "shot_id": f"{sid:04d}",
            "narration": part,
            "anchor_look": get_stage_anchor(sid, master_plan)
        })

    print(f"  ├─ 剧本语义降噪完成：已物理合并标签残留，当前共 {len(all_shots)} 镜。")

    # 🧪 V14.1 工业审计：分镜数量合法性校验 (仅拦截 > 150 镜的膨胀异常)
    if len(all_shots) > 150:
        raise RuntimeError(f"分镜数量严重异常：{len(all_shots)} 镜（超过 150 镜工业红线）")

    # 2. 段落化物理翻译
    processed_shots = []
    # 🧪 V7.1：为了防止 Batch 内跨年龄导致的混淆，我们强制按 Anchor 的连续性进行 Batch 分组
    i = 0
    while i < len(all_shots):
        current_anchor = all_shots[i]['anchor_look']
        # 寻找这一批次内相同 Anchor 的分镜
        batch = []
        for j in range(i, min(i + BATCH_SIZE, len(all_shots))):
            if all_shots[j]['anchor_look'] == current_anchor:
                batch.append(all_shots[j])
            else:
                break
        
        i += len(batch)
        print(f"  ├─ 进度: {i}/{len(all_shots)} (对位母照: {Path(current_anchor).name if current_anchor else 'None'})")
        
        # 🧪 V8.0 物理对位：编码这张母照并传给 VLM
        anchor_b64 = None
        if current_anchor and Path(current_anchor).exists():
            anchor_b64 = encode_image_to_b64(Path(current_anchor))
        
        res = call_vlm_visual_batch(batch, meta.get('era', '历史'), current_anchor, anchor_b64)
        
        prompts = res["prompts"]
        for idx_b, shot_meta in enumerate(batch):
            p_data = prompts[idx_b]
            shot_meta['visual_prompt'] = p_data.get('visual_prompt', '').strip()
            shot_meta['has_protagonist'] = p_data.get('has_protagonist', True)
            processed_shots.append(shot_meta)

    # 🧪 V9.9 熔断保障：强制检验分镜完整性
    if len(processed_shots) != len(all_shots):
        raise RuntimeError(
            f"生产管线偏差：预期 {len(all_shots)} 镜，实出 {len(processed_shots)} 镜，禁止入库"
        )

    # 增量存档
    save_data = {
        "metadata": meta,
        "director_chapters": [{"chapter_id": 1, "shots": processed_shots}]
    }
    
    # 🧪 原子化物理写入：先写 Temp，再 Rename，防止磁盘读写死锁
    temp_path = NARRATIVE_V6_PATH.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    
    if NARRATIVE_V6_PATH.exists(): NARRATIVE_V6_PATH.unlink()
    temp_path.rename(NARRATIVE_V6_PATH)

    print(f"\n[OK] V7.1 物理隔离导播剧本已由于锁定：{NARRATIVE_V6_PATH}")

if __name__ == "__main__":
    main()
