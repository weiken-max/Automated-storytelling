"""
16 宫格生图落盘后的硬校验：16:9 横屏、宽高等分 4×4，不通过则打回重试。
"""
from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np

# 允许的长宽比相对 16/9 的相对误差
_ASPECT_TOL = float(os.getenv("GRID_ASPECT_TOLERANCE", "0.02"))
_DIVIDER_SEARCH_TOL_RATIO = float(os.getenv("GRID_DIVIDER_SEARCH_TOL_RATIO", "0.08"))
_DIVIDER_MIN_STRENGTH_RATIO = float(os.getenv("GRID_DIVIDER_MIN_STRENGTH_RATIO", "0.60"))
_DIVIDER_MIN_CONTINUITY = float(os.getenv("GRID_DIVIDER_MIN_CONTINUITY", "0.50"))


def _imread_unicode(path: Path):
    p = Path(path)
    try:
        data = np.fromfile(str(p), dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return cv2.imread(str(p))


def _find_divider_index(
    score_1d: np.ndarray,
    expected_idx: int,
    max_idx: int,
    search_tol_ratio: float,
) -> int:
    search_tol = max(6, int(max_idx * search_tol_ratio))
    left = max(0, expected_idx - search_tol)
    right = min(max_idx - 1, expected_idx + search_tol)
    if right <= left:
        return expected_idx
    local = score_1d[left : right + 1]
    return int(left + int(np.argmax(local)))


def _extract_peak_centers(score_1d: np.ndarray, gate: float) -> list[int]:
    n = int(score_1d.shape[0])
    if n < 5:
        return []
    k = max(9, int(n * 0.01))
    if k % 2 == 0:
        k += 1
    kernel = np.ones((k,), dtype=np.float32) / float(k)
    smooth = np.convolve(score_1d.astype(np.float32), kernel, mode="same")

    candidates: list[tuple[float, int]] = []
    for i in range(1, n - 1):
        v = float(smooth[i])
        if v < gate:
            continue
        if v >= float(smooth[i - 1]) and v > float(smooth[i + 1]):
            candidates.append((v, i))

    if not candidates:
        return []
    candidates.sort(key=lambda x: x[0], reverse=True)
    min_dist = max(12, int(n * 0.12))
    picked: list[int] = []
    for _, idx in candidates:
        if all(abs(idx - p) >= min_dist for p in picked):
            picked.append(int(idx))
        if len(picked) >= 6:
            break
    return sorted(picked)


def _validate_4x4_dividers(img: np.ndarray) -> None:
    """
    校验 4x4 内部分割线是否存在：
    - 竖线应在 w/4, w/2, 3w/4 附近；
    - 横线应在 h/4, h/2, 3h/4 附近；
    - 每条线需有足够“强度 + 贯穿度”。
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 利用梯度 + 深色像素占比联合评估分割线显著性。
    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    abs_x = np.abs(grad_x)
    abs_y = np.abs(grad_y)

    dark_mask = (gray < 65).astype(np.float32)
    col_score = abs_x.mean(axis=0) + 40.0 * dark_mask.mean(axis=0)
    row_score = abs_y.mean(axis=1) + 40.0 * dark_mask.mean(axis=1)

    # 使用高分位数作为“有效分割线”最低强度门槛，适应不同画面复杂度。
    col_gate = max(1e-6, float(np.percentile(col_score, 90)) * _DIVIDER_MIN_STRENGTH_RATIO)
    row_gate = max(1e-6, float(np.percentile(row_score, 90)) * _DIVIDER_MIN_STRENGTH_RATIO)

    expected_cols = [w // 4, w // 2, (3 * w) // 4]
    expected_rows = [h // 4, h // 2, (3 * h) // 4]

    found_cols = [
        _find_divider_index(col_score, e, w, _DIVIDER_SEARCH_TOL_RATIO) for e in expected_cols
    ]
    found_rows = [
        _find_divider_index(row_score, e, h, _DIVIDER_SEARCH_TOL_RATIO) for e in expected_rows
    ]

    # 避免三条线坍缩到近邻同一位置，至少保持 12% 单格宽/高间距。
    min_col_gap = max(4, int((w / 4) * 0.12))
    min_row_gap = max(4, int((h / 4) * 0.12))
    if not (found_cols[0] + min_col_gap < found_cols[1] < found_cols[2] - min_col_gap):
        raise ValueError(f"竖向分割线位置异常: found={found_cols}, expect≈{expected_cols}")
    if not (found_rows[0] + min_row_gap < found_rows[1] < found_rows[2] - min_row_gap):
        raise ValueError(f"横向分割线位置异常: found={found_rows}, expect≈{expected_rows}")

    # 贯穿度：在对应列/行上，边缘响应超过阈值的比例需足够高。
    edge_x_thr = max(5.0, float(np.percentile(abs_x, 80)))
    edge_y_thr = max(5.0, float(np.percentile(abs_y, 80)))
    dark_thr = 80
    band = 2
    for idx, x in enumerate(found_cols, 1):
        strength = float(col_score[x])
        lx = max(0, x - band)
        rx = min(w - 1, x + band)
        edge_hit = (abs_x[:, lx : rx + 1] > edge_x_thr).any(axis=1)
        dark_hit = (gray[:, lx : rx + 1] < dark_thr).any(axis=1)
        continuity = float((edge_hit | dark_hit).mean())
        if strength < col_gate or continuity < _DIVIDER_MIN_CONTINUITY:
            raise ValueError(
                f"竖向分割线#{idx}弱或不连续: x={x}, score={strength:.3f}, "
                f"need>={col_gate:.3f}, continuity={continuity:.3f}, "
                f"need>={_DIVIDER_MIN_CONTINUITY:.3f}"
            )

    for idx, y in enumerate(found_rows, 1):
        strength = float(row_score[y])
        ly = max(0, y - band)
        ry = min(h - 1, y + band)
        edge_hit = (abs_y[ly : ry + 1, :] > edge_y_thr).any(axis=0)
        dark_hit = (gray[ly : ry + 1, :] < dark_thr).any(axis=0)
        continuity = float((edge_hit | dark_hit).mean())
        if strength < row_gate or continuity < _DIVIDER_MIN_CONTINUITY:
            raise ValueError(
                f"横向分割线#{idx}弱或不连续: y={y}, score={strength:.3f}, "
                f"need>={row_gate:.3f}, continuity={continuity:.3f}, "
                f"need>={_DIVIDER_MIN_CONTINUITY:.3f}"
            )

    # 分行/分列一致性：每个“行带/列带”内都应只有 3 条主分割线（排除边框）。
    expected_cols = np.array(expected_cols, dtype=np.int32)
    expected_rows = np.array(expected_rows, dtype=np.int32)
    pos_tol_x = max(10, int(w * 0.10))
    pos_tol_y = max(10, int(h * 0.10))

    for r in range(4):
        y1 = int(r * h / 4)
        y2 = int((r + 1) * h / 4)
        band_abs_x = abs_x[y1:y2, :]
        band_dark = dark_mask[y1:y2, :]
        band_col_score = band_abs_x.mean(axis=0) + 40.0 * band_dark.mean(axis=0)
        band_gate = max(1e-6, float(np.percentile(band_col_score, 90)) * 0.72)
        peaks = _extract_peak_centers(band_col_score, band_gate)
        peaks = [p for p in peaks if int(0.05 * w) <= p <= int(0.95 * w)]
        if len(peaks) != 3:
            raise ValueError(f"第{r+1}行分割线数量异常: peaks={peaks}, expect=3")
        peaks_arr = np.array(sorted(peaks), dtype=np.int32)
        if np.any(np.abs(peaks_arr - expected_cols) > pos_tol_x):
            raise ValueError(
                f"第{r+1}行分割线位置漂移: peaks={peaks_arr.tolist()}, expect≈{expected_cols.tolist()}"
            )

    for c in range(4):
        x1 = int(c * w / 4)
        x2 = int((c + 1) * w / 4)
        band_abs_y = abs_y[:, x1:x2]
        band_dark = dark_mask[:, x1:x2]
        band_row_score = band_abs_y.mean(axis=1) + 40.0 * band_dark.mean(axis=1)
        band_gate = max(1e-6, float(np.percentile(band_row_score, 90)) * 0.72)
        peaks = _extract_peak_centers(band_row_score, band_gate)
        peaks = [p for p in peaks if int(0.05 * h) <= p <= int(0.95 * h)]
        if len(peaks) != 3:
            raise ValueError(f"第{c+1}列分割线数量异常: peaks={peaks}, expect=3")
        peaks_arr = np.array(sorted(peaks), dtype=np.int32)
        if np.any(np.abs(peaks_arr - expected_rows) > pos_tol_y):
            raise ValueError(
                f"第{c+1}列分割线位置漂移: peaks={peaks_arr.tolist()}, expect≈{expected_rows.tolist()}"
            )


def validate_grid_comic_layout(grid_path: Path) -> None:
    """
    读取已落盘的宫格 PNG，校验：
    - 横屏 16:9（在容差内）；
    - 宽高均可被 4 整除（与 process_16_grid 一致）。

    不通过时抛出 ValueError，由 Step2 批次重试捕获。
    """
    img = _imread_unicode(grid_path)
    if img is None:
        raise ValueError(f"无法读取宫格图: {grid_path}")

    h, w = img.shape[:2]
    if w <= 0 or h <= 0:
        raise ValueError(f"宫格图尺寸异常: {w}x{h}")

    ratio = w / h
    target = 16 / 9
    if abs(ratio - target) / target > _ASPECT_TOL:
        raise ValueError(
            f"宫格非 16:9 横屏: {w}x{h} (ratio={ratio:.4f}, expect≈{target:.4f})"
        )

    if w % 4 != 0 or h % 4 != 0:
        raise ValueError(
            f"宫格宽高不可被 4 整除，无法均分 4×4: {w}x{h}"
        )

    _validate_4x4_dividers(img)
