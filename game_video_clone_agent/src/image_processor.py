"""
✂️ 图像处理器与裁切脚手架 (src/image_processor.py)
处理 16 宫格的切割、去白边以及预留放大接口
"""
import cv2
import numpy as np
from pathlib import Path

def upscale_image(img_path: Path):
    """
    【预留接口】：轻量级高清放大模型接入点。
    目前直接 pass。后续可在此处无缝接入 Real-ESRGAN 等本地放大模型，
    将裁切后较小的子图放大至 1080p 或更高分辨率。
    """
    pass

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
