"""
✂️ 图像处理器与裁切脚手架 (src/image_processor.py)
处理 16 宫格的切割、去白边以及 Real-ESRGAN 高清放大
"""
import os
import subprocess
import cv2
import numpy as np
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parent.parent
_REALESRGAN_DIR = _AGENT_ROOT / "toolsrealesrgan"
_REALESRGAN_EXE = _REALESRGAN_DIR / "realesrgan-ncnn-vulkan.exe"
_missing_exe_warned = False


def upscale_image(img_path: Path) -> None:
    """
    调用 `toolsrealesrgan/realesrgan-ncnn-vulkan.exe` 对单张子图做超分，成功则覆盖原 `S_XXX.png`。

    未找到 exe 时仅首次打印提示并跳过，不中断裁切流程。可用环境变量关闭或调参：

    - REALESRGAN_DISABLE：设为 1 / true 则跳过放大；
    - REALESRGAN_MODEL：默认 realesr-animevideov3；
    - REALESRGAN_SCALE：默认 3（可选 2、3、4，需与模型档位一致）；
    - REALESRGAN_GPU：留空为自动选卡；某些双显卡机型可设 0 或 1 对应 `-g`。
    """
    global _missing_exe_warned
    if os.environ.get("REALESRGAN_DISABLE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return
    if not _REALESRGAN_EXE.is_file():
        if not _missing_exe_warned:
            print(
                "[upscale] 未找到 toolsrealesrgan/realesrgan-ncnn-vulkan.exe，已跳过高清；"
                "请按「高清组块使用指南」放入完整发行包文件。"
            )
            _missing_exe_warned = True
        return

    model = (os.environ.get("REALESRGAN_MODEL") or "realesr-animevideov3").strip()
    scale = (os.environ.get("REALESRGAN_SCALE") or "3").strip()
    gpu = (os.environ.get("REALESRGAN_GPU") or "").strip()

    src = Path(img_path).resolve()
    tmp = src.parent / f"{src.stem}.realesrgan_tmp{src.suffix}"
    if tmp.exists():
        tmp.unlink()

    cmd = [
        str(_REALESRGAN_EXE),
        "-i",
        str(src),
        "-o",
        str(tmp),
        "-n",
        model,
        "-s",
        scale,
    ]
    if gpu:
        cmd.extend(["-g", gpu])

    try:
        r = subprocess.run(
            cmd,
            cwd=str(_REALESRGAN_DIR),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except OSError as e:
        print(f"[upscale] 调用失败 {src.name}: {e}")
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return
    except subprocess.TimeoutExpired:
        print(f"[upscale] 超时 {src.name}")
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return

    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        tail = err[-400:] if err else "(无输出)"
        print(f"[upscale] {src.name} 失败 (code={r.returncode}): {tail}")
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return

    if not tmp.is_file() or tmp.stat().st_size < 64:
        print(f"[upscale] {src.name} 输出异常或过小，保留原图")
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return

    try:
        os.replace(tmp, src)
    except OSError as e:
        print(f"[upscale] 覆盖原图失败 {src.name}: {e}")
        if tmp.exists():
            tmp.unlink(missing_ok=True)

def process_16_grid(image_path: Path, output_dir: Path, start_idx: int) -> int:
    """
    将 4x4 宫格图裁切为最多 16 张单图，利用 OpenCV 识别有效轮廓去除白边。
    返回下一个可用的 subshot_id 序号。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"无法读取图片: {image_path}")

    h, w = img.shape[:2]
    cell_h, cell_w = h // 4, w // 4
    
    current_idx = start_idx
    
    for row in range(4):
        for col in range(4):
            # 1. 物理等分提取子网格
            y1, y2 = row * cell_h, (row + 1) * cell_h
            x1, x2 = col * cell_w, (col + 1) * cell_w
            cell = img[y1:y2, x1:x2]
            
            # 2. 灰度与边缘检测，用于智能去白边
            gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
            # 假设白边接近 255，反转阈值
            _, thresh = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if contours:
                # 找到面积最大的轮廓（通常是漫画画面的主体边框）
                c = max(contours, key=cv2.contourArea)
                x, y, cw, ch = cv2.boundingRect(c)
                
                # 适度增加一点内边距，避免裁切过紧
                pad = 8
                x = max(0, x - pad)
                y = max(0, y - pad)
                cw = min(cell_w - x, cw + 2 * pad)
                ch = min(cell_h - y, ch + 2 * pad)
                cropped = cell[y:y+ch, x:x+cw]
            else:
                # 如果没找到有效轮廓，原样保留
                cropped = cell
                
            out_path = output_dir / f"S_{current_idx:03d}.png"
            cv2.imwrite(str(out_path), cropped)
            
            # 3. 触发预留的高清放大器
            upscale_image(out_path)
            
            current_idx += 1
            
    return current_idx
