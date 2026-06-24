"""
✂️ 图像处理器与裁切脚手架 (src/image_processor.py)
处理 16 宫格的物理均分切割以及 Real-ESRGAN 高清放大。
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


def _imread_unicode(path: Path):
    """
    兼容 Windows 中文路径读取图片：
    优先使用 np.fromfile + cv2.imdecode，避免 cv2.imread 在非 ASCII 路径下失败。
    """
    p = Path(path)
    try:
        data = np.fromfile(str(p), dtype=np.uint8)
        if data.size == 0:
            return None
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is not None:
            return img
    except Exception:
        pass
    # 回退：保留原逻辑
    return cv2.imread(str(p))


def _imwrite_unicode(path: Path, img) -> bool:
    """
    兼容 Windows 中文路径写图片：
    先 cv2.imencode，再由 Python 写字节，避免 cv2.imwrite 路径编码问题。
    """
    p = Path(path)
    ext = p.suffix or ".png"
    ok, enc = cv2.imencode(ext, img)
    if not ok:
        return False
    try:
        p.write_bytes(enc.tobytes())
        return True
    except Exception:
        return False


def upscale_image(img_path: Path) -> bool:
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
        return True
    if not _REALESRGAN_EXE.is_file():
        if not _missing_exe_warned:
            print(
                "[upscale] 未找到 toolsrealesrgan/realesrgan-ncnn-vulkan.exe，将自动跳过超分并直接使用原图。"
            )
            _missing_exe_warned = True
        return True

    # 强制使用用户指定方案：realesr-animevideov3 x3
    model = "realesr-animevideov3"
    scale = "3"
    gpu = (os.environ.get("REALESRGAN_GPU") or "").strip()

    src = Path(img_path).resolve()
    tmp = src.parent / f"{src.stem}.realesrgan_tmp{src.suffix}"
    if tmp.exists():
        tmp.unlink()

    before_img = _imread_unicode(src)
    bw = bh = None
    if before_img is not None:
        bh, bw = before_img.shape[:2]

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
        print(f"[upscale] ⚠️ 调用失败 {src.name} (已自动跳过超分，保留原图兜底): {e}")
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return True
    except subprocess.TimeoutExpired:
        print(f"[upscale] ⚠️ 超时 {src.name} (已自动跳过超分，保留原图兜底)")
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return True

    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        tail = err[-400:] if err else "(无输出)"
        print(f"[upscale] ⚠️ {src.name} 超分失败 (已自动跳过超分，保留原图兜底) (code={r.returncode}): {tail}")
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return True

    if not tmp.is_file() or tmp.stat().st_size < 64:
        print(f"[upscale] ⚠️ {src.name} 输出异常或过小 (已自动跳过超分，保留原图兜底)")
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return True

    try:
        os.replace(tmp, src)
        after_img = _imread_unicode(src)
        if after_img is not None and bw and bh:
            ah, aw = after_img.shape[:2]
            sx = round(aw / bw, 2) if bw else 0
            sy = round(ah / bh, 2) if bh else 0
            print(
                f"[upscale] {src.name}: {bw}x{bh} -> {aw}x{ah} "
                f"(≈{sx}x/{sy}x, model={model}, -s {scale})"
            )
        elif after_img is not None:
            ah, aw = after_img.shape[:2]
            print(f"[upscale] {src.name}: -> {aw}x{ah} (model={model}, -s {scale})")
        return True
    except OSError as e:
        print(f"[upscale] ⚠️ 覆盖原图失败 {src.name} (已自动跳过超分，保留原图兜底): {e}")
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return True

def process_16_grid(image_path: Path, output_dir: Path, start_idx: int, grid_mode: str = "4x4", skip_indices=None) -> int:
    """
    将 NxN 宫格图按像素均分为 N*N 张子图（不做去白边；格子已铺满画布）。
    返回下一个可用的 subshot_id 序号。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    img = _imread_unicode(image_path)
    if img is None:
        raise ValueError(f"无法读取图片: {image_path}")

    if grid_mode == "2x2":
        N = 2
    elif grid_mode == "3x3":
        N = 3
    else:
        N = 4

    h, w = img.shape[:2]
    cell_h, cell_w = h // N, w // N
    
    current_idx = start_idx
    
    for row in range(N):
        for col in range(N):
            if skip_indices and current_idx in skip_indices:
                print(f"  [Slice] 跳过已手动重绘的分镜 S_{current_idx:03d}.png")
                current_idx += 1
                continue

            # 1. 物理等分提取子网格
            y1, y2 = row * cell_h, (row + 1) * cell_h
            x1, x2 = col * cell_w, (col + 1) * cell_w
            cell = img[y1:y2, x1:x2]

            out_path = output_dir / f"S_{current_idx:03d}.png"
            if not _imwrite_unicode(out_path, cell):
                raise ValueError(f"无法写入切图结果: {out_path}")
            
            # Real-ESRGAN 高清：失败则删除该图并中止当前批次，交给 Step2 重试。
            if not upscale_image(out_path):
                out_path.unlink(missing_ok=True)
                raise ValueError(f"高清放大失败: {out_path.name} (model=realesr-animevideov3, scale=3)")
            
            current_idx += 1
            
    return current_idx
