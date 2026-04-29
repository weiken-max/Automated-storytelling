"""
🎨 16 宫格爆兵流水线 (src/step2_comic_generator_v6.py)
读取 final narrative，每次聚合 16 个 prompt，生成 4x4 宫格，并调用切图脚手架落盘
"""
import json
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv
import cv2
import numpy as np

# ── Windows GBK 终端编码修复 ──
if hasattr(sys.stdout, "buffer"):
    from io import TextIOWrapper
    sys.stdout = TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
DATA_DIR = BASE_DIR / "data"

from src.style_config import SCRIPT_DIR
from src.project_vault import backup as vault_backup
from src.image_engine import generate_image
from src.image_processor import process_16_grid

NARRATIVE_FINAL_PATH = SCRIPT_DIR / "narrative_v6_final.json"
STORYBOARDS_DIR = DATA_DIR / "storyboards"

def chunk_list(lst, n):
    """将列表按步长 n 拆分"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

async def generate_grid_batch(batch_shots: list, batch_index: int, total_batches: int):
    """提交 16 宫格生图请求"""
    print(f"\n  [Grid Render] 正在生成第 {batch_index}/{total_batches} 批次 (包含 {len(batch_shots)} 个分镜)...")
    
    # 构建聚合 Prompt
    combined_prompt = (
        "Generate ONE single 16:9 canvas comic page. "
        "Use a strict 4x4 grid (16 panels total). "
        "Panel order is HARD RULE: from left to right, top to bottom, exactly Panel 1 to Panel 16. "
        "Do not shuffle panel positions. Do not mirror sequence. "
        "Cyanide and Happiness comic style, flat illustration, pure 2D. "
    )
    combined_prompt += "The grid contains the following sequential scenes:\n"

    batch_refs = []
    for i, shot in enumerate(batch_shots):
        combined_prompt += f"Panel {i+1}: {shot['visual_prompt']}\n"
        anchor_look = str(shot.get("anchor_look") or "").strip()
        if anchor_look and anchor_look not in batch_refs:
            batch_refs.append(anchor_look)

    # 尾批不足 16 时强制补齐空面板，保持“16:9 + 4x4 + Panel 1..16”硬约束不变形。
    if len(batch_shots) < 16:
        for panel_idx in range(len(batch_shots) + 1, 17):
            combined_prompt += (
                f"Panel {panel_idx}: EMPTY PANEL. "
                "Pure white background, no character, no object, no text.\n"
            )
        
    # 生图 API 调用 (建议使用至少 4K 分辨率，若 API 支持的话；这里采用 2k/4k 通用档)
    img_bytes = await generate_image(
        prompt=combined_prompt,
        image_refs=batch_refs,
        size="4k"
    )
    
    if img_bytes:
        grid_path = STORYBOARDS_DIR / f"grid_batch_{batch_index:03d}.png"
        grid_path.write_bytes(img_bytes)
        return grid_path
    else:
        print(f"  ❌ 第 {batch_index} 批次生成失败。")
        return None

async def main():
    print("\n=======================================================")
    print("[Phase 4-A] 16 宫格生成与智能裁切")
    print("=======================================================")
    
    if not NARRATIVE_FINAL_PATH.exists():
        print("❌ 找不到叙事蓝图 narrative_v6_final.json，请先执行 Phase 3。")
        sys.exit(1)
        
    data = json.loads(NARRATIVE_FINAL_PATH.read_text(encoding="utf-8"))
    timeline = data.get("timeline", [])
    
    if not timeline:
        print("❌ 蓝图 timeline 为空。")
        sys.exit(1)
        
    STORYBOARDS_DIR.mkdir(parents=True, exist_ok=True)
    
    # 清理旧数据
    for f in STORYBOARDS_DIR.glob("*.png"):
        f.unlink()
        
    # 按 16 个一组分批
    batches = list(chunk_list(timeline, 16))
    total_batches = len(batches)
    
    current_subshot_idx = 1

    def _create_placeholder_subshots(start_idx: int, count: int):
        """
        当某批 16 宫格失败时，补齐占位图，确保 S_XXX 与 timeline 索引严格对齐。
        """
        for k in range(count):
            out_path = STORYBOARDS_DIR / f"S_{start_idx + k:03d}.png"
            black = np.zeros((768, 1024, 3), dtype=np.uint8)
            cv2.imwrite(str(out_path), black)
    
    for i, batch in enumerate(batches, 1):
        grid_path = await generate_grid_batch(batch, i, total_batches)
        if grid_path:
            print(f"  [Process] 正在进行 OpenCV 轮廓切图与去白边...")
            # 裁切并将游标向后推移
            current_subshot_idx = process_16_grid(grid_path, STORYBOARDS_DIR, current_subshot_idx)
            vault_backup(grid_path, f"storyboards/{grid_path.name}")
        else:
            print(f"  [Fallback] 第 {i} 批次失败，补齐 {len(batch)} 张占位图以保持编号连续。")
            _create_placeholder_subshots(current_subshot_idx, len(batch))
            current_subshot_idx += len(batch)
            
    # 因为存在尾部批次不满 16 个的情况，多切出来的冗余纯白/黑图可以在这里清理（这里保留简单实现）
    # 实际所需总分镜数就是 len(timeline)
    for f in STORYBOARDS_DIR.glob("S_*.png"):
        idx_str = f.stem.split('_')[1]
        if int(idx_str) > len(timeline):
            f.unlink()
            
    print(f"\n[DONE] 所有分镜图像生成并裁切完成！单镜图已落盘至 {STORYBOARDS_DIR}")

if __name__ == "__main__":
    asyncio.run(main())
