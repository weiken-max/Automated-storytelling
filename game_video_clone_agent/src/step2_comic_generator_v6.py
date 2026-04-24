"""
🚀 视觉小说导演版 - 第三阶段：自适应调度器 (comic_generator_v6.py)
==============================================================
功能：读取导演剧本，执行宫格生图、分剪与章节配音。
依据：PROJECT_MASTER_PLAN.md 中的“2x2宫格柔性适配”原则。
"""

import json
import os
import sys
import asyncio
import math
from pathlib import Path
from PIL import Image
import re

# ── 自动对齐项目根目录 ──
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(BASE_DIR / "src") not in sys.path:
    sys.path.insert(0, str(BASE_DIR / "src"))

# 导入配置与引擎
from src.style_config import (
    NARRATIVE_V6_PATH, IMG_DIR, AUDIO_DIR,
    VOICE_ROLE, VOICE_RATE, VOICE_PITCH
)
from src.project_vault import backup as vault_backup  # 🔒 导入金库备份接口
from src.image_engine import generate_grid_image  # 复用成熟的底层生图能力

# ── Windows GBK 终端编码修复 ──
if hasattr(sys.stdout, "buffer"):
    from io import TextIOWrapper
    sys.stdout = TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ================================================================
#  🎨 生图与裁剪逻辑
# ================================================================

def _is_degraded_prompt(prompt_text: str) -> bool:
    p = (prompt_text or "").strip().lower()
    return (
        p.startswith("cinematic historical flat illustration for")
        or p == "cinematic shot"
        or "[fallback_triggered]" in p
    )

def preflight_validate_narrative(narrative_data: dict):
    """Step2 质量闸门：阻断退化提示词进入生图环节。"""
    chapters = narrative_data.get("director_chapters", [])
    all_shots = []
    for chap in chapters:
        all_shots.extend(chap.get("shots", []))

    if not all_shots:
        raise RuntimeError("Step2 前置校验失败：没有可用分镜 shots。")

    prompts = []
    degraded = 0
    missing = 0
    for s in all_shots:
        vp = (s.get("visual_prompt") or "").strip()
        if not vp:
            missing += 1
            continue
        prompts.append(vp)
        if _is_degraded_prompt(vp):
            degraded += 1

    total = len(all_shots)
    if missing > 0:
        raise RuntimeError(f"Step2 前置校验失败：存在空 visual_prompt（{missing}/{total}）。请先重跑 Step1。")

    unique_ratio = len(set(prompts)) / max(1, len(prompts))
    degraded_ratio = degraded / max(1, len(prompts))
    if unique_ratio < 0.60:
        raise RuntimeError(
            f"Step2 前置校验失败：提示词重复率过高（unique_ratio={unique_ratio:.2f}）。请先重跑 Step1。"
        )
    if degraded_ratio > 0.25:
        raise RuntimeError(
            f"Step2 前置校验失败：检测到退化提示词占比过高（degraded_ratio={degraded_ratio:.2f}）。请先重跑 Step1。"
        )
    print(
        f"[Preflight] 通过：shots={total}, unique_ratio={unique_ratio:.2f}, degraded_ratio={degraded_ratio:.2f}"
    )

def process_image_batches(narrative_data: dict):
    """提取所有 Shot 并按 4 个一组进行 2x2 生图 (V6.6 结构化版)"""
    all_shots = []
    for chap in narrative_data['director_chapters']:
        all_shots.extend(chap['shots'])
    
    all_shots.sort(key=lambda x: int(x['shot_id']))
    total_shots = len(all_shots)
    total_grids = math.ceil(total_shots / 4)
    
    print(f"[Image Generator] 共有 {total_shots} 个分镜，计划生成 {total_grids} 组宫格...")
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    
    for i in range(total_grids):
        batch = all_shots[i*4 : (i+1)*4]
        
        all_exist = True
        for s in batch:
            if not (IMG_DIR / f"{int(s['shot_id']):04d}.png").exists():
                all_exist = False
                break
        if all_exist: continue

        grid_id = i + 1
        print(f"\n  [Grid {grid_id}/{total_grids}] 正在通过隔离引擎生图...", flush=True)
        
        grid_path = IMG_DIR / f"grid_v6_{grid_id:03d}.png"
        max_grid_retries = 3
        for attempt in range(max_grid_retries):
            success = generate_grid_image(batch, grid_path)
            if success and grid_path.exists():
                crop_and_save_shots(grid_path, batch)
                break
            else:
                print(f"      ⚠️  [Grid Retry] 第 {attempt+1} 次失败，正在执行物理冷却...", flush=True)
                import time
                time.sleep(5)
        
        if not grid_path.exists():
            print(f"      ❌  [Grid Failed] 第 {grid_id} 组宫格历经三次重试依然熔断，跳过。", flush=True)

def crop_and_save_shots(grid_path: Path, shots_metadata: list):
    """将 16:9 的宫格图裁剪为 4 张独立的横屏图片 (0001.png, 0002.png...)"""
    try:
        grid_img = Image.open(grid_path)
        w, h = grid_img.size
        print(f"    📏 Grid 尺寸: {w}x{h} (比例: {w/h:.2f})", flush=True)
        
        # 即使模型生成的不是绝对精准的 2x2，我们也通过 4 等分坐标强制锁定
        pw, ph = w // 2, h // 2
        
        # 定义 2x2 坐标 (左上, 右上, 左下, 右下)
        coords = [
            (0, 0, pw, ph), (pw, 0, w, ph),
            (0, ph, pw, h), (pw, ph, w, h)
        ]
        
        for idx, shot in enumerate(shots_metadata):
            if idx >= len(coords): break
            shot_file = IMG_DIR / f"{int(shot['shot_id']):04d}.png"
            box = coords[idx]
            panel = grid_img.crop(box)
            # 最终导出前，强制做一次 16:9 的 Resize/Pad 兼容 (可选，这里先直接存)
            panel.save(shot_file)
            # 🔒 实时备份分镜图到金库
            vault_backup(shot_file, f"storyboards/{shot_file.name}")
            print(f"    └─ 保存并备份分镜: {shot_file.name}", flush=True)
            
    except Exception as e:
        print(f"  [ERR] 裁剪失败: {e}", flush=True)

# ================================================================
#  🎙️ 语音生成逻辑
# ================================================================

async def _generate_single_audio(shot, audio_dir):
    """单体分镜原子配音任务"""
    try:
        import edge_tts
        sid = shot['shot_id']
        clean_text = shot.get('narration', '').strip()
        if not clean_text:
            return
            
        audio_file = audio_dir / f"shot_{int(sid):04d}.mp3"
        
        # 🔒 断点续传：已存在的不再重复请求
        if audio_file.exists() and audio_file.stat().st_size > 0:
            return

        print(f"    └─ [Shot {sid}] 配音中: {clean_text[:12]}...")
        
        for attempt in range(3):
            try:
                communicate = edge_tts.Communicate(clean_text, VOICE_ROLE, rate=VOICE_RATE, pitch=VOICE_PITCH)
                await communicate.save(audio_file)
                if audio_file.exists():
                    vault_backup(audio_file, f"audio/{audio_file.name}")
                    break
            except Exception as e:
                print(f"      ⚠️ [Shot {sid}] 接口波动 {attempt+1}: {e}")
                await asyncio.sleep(2)
                
        await asyncio.sleep(0.4) # 轻微抖动防风控
    except Exception as e:
        print(f"    🚫 [Shot {shot.get('shot_id')}] 严重异常: {e}")

async def process_all_audio(narrative_data: dict):
    """
    [V6.6.1 加固版] 显式章节遍历，保障 100 镜全量产出。
    """
    print(f"\n🎙️ [Step 2 Audio] 启动高压原子化配音总线...")
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    import edge_tts
    
    chapters = narrative_data.get('director_chapters', [])
    total_chapters = len(chapters)
    
    for idx, chap in enumerate(chapters):
        chap_title = chap.get('chapter_title', f"Chapter {idx+1}")
        shots = chap.get('shots', [])
        print(f"\n  ▶ 正在处理章节 [{idx+1}/{total_chapters}]: {chap_title} (共 {len(shots)} 镜)...")
        
        # 🚀 高压并发引擎开启：剥离串行锁定，改为异步合拢
        tasks = [_generate_single_audio(shot, AUDIO_DIR) for shot in shots]
        await asyncio.gather(*tasks)
        
        # 🧊 章节间心跳冷却
        print(f"  √ 章节 [{idx+1}] 配音任务同步完成。")
        await asyncio.sleep(1.0)

    print("\n[OK] 全量原子化音频生产已锁定。")

# ================================================================
# ================================================================
#  ▶️ 入口驱动 (V6.6 异步安全版)
# ================================================================

async def combined_main():
    """统一的异步入口"""
    if not NARRATIVE_V6_PATH.exists():
        raise RuntimeError(f"Step2 前置缺失：找不到 V6 导演剧本 -> {NARRATIVE_V6_PATH}")

    with open(NARRATIVE_V6_PATH, "r", encoding="utf-8") as f:
        narrative_data = json.load(f)

    # 0. Step2 质量闸门
    preflight_validate_narrative(narrative_data)

    # 1. 处理图片 (断点续传模式)
    process_image_batches(narrative_data)

    # 2. 处理原子音频 (原生异步)
    await process_all_audio(narrative_data)
    
    print(f"\n[OK] V6 结构化生产任务已全部完成！")

def main():
    """原子级入口，防止 Windows Loop 冲突"""
    import nest_asyncio
    nest_asyncio.apply()
    # BUG-10 修复：asyncio.run() 在 Python 3.12+ 更稳定，不再使用已废弃的 get_event_loop()
    try:
        asyncio.run(combined_main())
    except Exception as e:
        print(f"  [Critical] 生产总线运行时冲突: {e}")


if __name__ == "__main__":
    main()
