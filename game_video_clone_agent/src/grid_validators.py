"""
16 宫格生图落盘后的校验：16:9、宽高可被 4 整除；六条理论分割线（竖 3 + 横 3）须沿全长足够连续。

设计对齐裁切假设：process_16_grid 按整图四等分切 16 份；合规宫格应在 W/4、W/2、3W/4 与 H/4、H/2、3H/4
处有可从一侧贯穿到另一侧的分界（黑线/边缘）。不齐布局（行间错位）除贯通度外，还会在「四行/四列格带」上暴露为
多条分割线峰值相对中位数同时偏斜（默认允许 1 个带离群，见 GRID_RULER_QUARTER_MAX_OUTLIERS）。
"""
from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np

# 允许的长宽比相对 16/9 的相对误差
_ASPECT_TOL = float(os.getenv("GRID_ASPECT_TOLERANCE", "0.02"))

# ── 六线贯通校验（竖 3 + 横 3）────────────────────────────────────────────
_GRID_RULER_BAND_PX = max(1, int(os.getenv("GRID_RULER_BAND_PX", "4")))
# 沿整条线方向上，「有足够分界信号」的采样点占比下限
_GRID_RULER_MIN_COVER = float(os.getenv("GRID_RULER_MIN_COVER", "0.72"))
# 允许的最长「弱分界」连续段占全线长度的比例上限（超过则视为断线）
_GRID_RULER_MAX_GAP_FRAC = float(os.getenv("GRID_RULER_MAX_GAP_FRAC", "0.22"))
# 设为 1 时恢复旧版基于带状峰数量的校验（不推荐）
_GRID_VALIDATOR_LEGACY = os.getenv("GRID_VALIDATOR_LEGACY", "").strip().lower() in (
    "1",
    "true",
    "yes",
)


def _imread_unicode(path: Path):
    p = Path(path)
    try:
        data = np.fromfile(str(p), dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return cv2.imread(str(p))


def _longest_weak_run_frac(strong: np.ndarray) -> float:
    """strong[i] 为 True 表示该采样点处分界信号足够；返回最长连续 False 段长度占比。"""
    if strong.size == 0:
        return 1.0
    weak = ~strong
    best = 0
    cur = 0
    for v in weak.flat:
        if v:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best / float(strong.size)


def _profile_vertical_ruler(
    abs_x: np.ndarray,
    abs_y: np.ndarray,
    gray: np.ndarray,
    x_center: int,
    band_px: int,
    h: int,
    w: int,
) -> np.ndarray:
    """沿竖线窄条，对每个 y 一行一行聚合边缘强度 + 暗线辅助，长度 H。"""
    x1 = max(0, x_center - band_px)
    x2 = min(w, x_center + band_px + 1)
    gx = abs_x[:, x1:x2].mean(axis=1).astype(np.float64)
    gy = abs_y[:, x1:x2].mean(axis=1).astype(np.float64)
    dark = (gray[:, x1:x2] < 65).astype(np.float64).mean(axis=1)
    return gx + 0.35 * gy + 38.0 * dark


def _profile_horizontal_ruler(
    abs_x: np.ndarray,
    abs_y: np.ndarray,
    gray: np.ndarray,
    y_center: int,
    band_px: int,
    h: int,
    w: int,
) -> np.ndarray:
    """沿横线窄条，对每个 x 一列一列聚合，长度 W。"""
    y1 = max(0, y_center - band_px)
    y2 = min(h, y_center + band_px + 1)
    gx = abs_x[y1:y2, :].mean(axis=0).astype(np.float64)
    gy = abs_y[y1:y2, :].mean(axis=0).astype(np.float64)
    dark = (gray[y1:y2, :] < 65).astype(np.float64).mean(axis=0)
    return gx + 0.35 * gy + 38.0 * dark


def _smooth_1d(prof: np.ndarray) -> np.ndarray:
    """轻度平滑，减弱单行格子内容跨过理论线时的尖峰噪声。"""
    n = prof.size
    k = max(5, min(n // 80, 31))
    if k % 2 == 0:
        k += 1
    pad = k // 2
    p = np.pad(prof.astype(np.float64), (pad, pad), mode="edge")
    ker = np.ones((k,), dtype=np.float64) / float(k)
    out = np.convolve(p, ker, mode="valid")
    return out.astype(np.float64)


def _continuity_from_profile(prof: np.ndarray, label: str) -> None:
    """同一维序列上判贯通：覆盖率 + 最大间断。"""
    if prof.size < 8:
        raise ValueError(f"{label}: 采样长度过短")
    prof = _smooth_1d(prof)
    thr = float(np.percentile(prof, 40))
    thr = max(thr, float(np.percentile(prof, 18)) * 1.02)
    strong = prof >= thr * 0.82
    cover = float(np.mean(strong))
    gap_frac = _longest_weak_run_frac(strong)
    if cover < _GRID_RULER_MIN_COVER:
        raise ValueError(
            f"{label}: 分界线贯通不足 cover={cover:.3f} (need>={_GRID_RULER_MIN_COVER}); "
            f"thr≈{thr:.2f}"
        )
    if gap_frac > _GRID_RULER_MAX_GAP_FRAC:
        raise ValueError(
            f"{label}: 分界线疑似中断 gap_frac={gap_frac:.3f} (need<={_GRID_RULER_MAX_GAP_FRAC})"
        )


def _peak_x_in_band(
    mag: np.ndarray, y0: int, y1: int, x_center: int, search_px: int, w: int
) -> int:
    """在 [y0,y1) 行、x≈x_center 附近找边缘能量最强的列（竖线应落在同一条 x 上）。"""
    x1 = max(0, x_center - search_px)
    x2 = min(w, x_center + search_px + 1)
    sub = mag[y0:y1, x1:x2]
    col_sum = sub.sum(axis=0)
    return x1 + int(np.argmax(col_sum))


def _peak_y_in_band(
    mag: np.ndarray, x0: int, x1: int, y_center: int, search_py: int, h: int
) -> int:
    """在 [x0,x1) 列、y≈y_center 附近找边缘能量最强的行（横线应落在同一条 y 上）。"""
    y1 = max(0, y_center - search_py)
    y2 = min(h, y_center + search_py + 1)
    sub = mag[y1:y2, x0:x1]
    row_sum = sub.sum(axis=1)
    return y1 + int(np.argmax(row_sum))


def _count_outliers_from_median(vals: list[int], tol: float) -> int:
    """返回与中位数偏差超过 tol 的采样点个数。"""
    if not vals:
        return 0
    med = float(np.median(np.asarray(vals, dtype=np.float64)))
    return sum(1 for v in vals if abs(float(v) - med) > tol)


def _validate_ruler_quarter_bands_alignment(
    mag: np.ndarray, h: int, w: int, xs: list[int], ys: list[int]
) -> None:
    """
    与 process_16_grid 一致：理论分割线应贯通整幅。仅在「半幅」比较峰值易漏检行间错位（错位图上下仍可能对齐）。

    做法：每条竖线在四行格带内各求一次峰值 x；每条横线在四列格带内各求一次峰值 y。
    合规图允许单行/单列因内容干扰产生一个离群峰值；行间错位则常表现为 ≥2 个带相对中位数偏斜。
    """
    search_px = max(12, int(w * 0.04))
    search_py = max(12, int(h * 0.04))
    tol_xy = max(10, int(min(w, h) * 0.018))
    max_outliers = int(os.getenv("GRID_RULER_QUARTER_MAX_OUTLIERS", "1"))

    for i, xc in enumerate(xs, start=1):
        xs_band: list[int] = []
        for r in range(4):
            y0 = int(r * h / 4)
            y1 = int((r + 1) * h / 4)
            xs_band.append(_peak_x_in_band(mag, y0, y1, xc, search_px, w))
        bad = _count_outliers_from_median(xs_band, tol_xy)
        if bad > max_outliers:
            med = float(np.median(np.asarray(xs_band, dtype=np.float64)))
            raise ValueError(
                f"竖线#{i} 四行格带内 x 与中位数偏差过大: xs={xs_band}, med≈{med:.1f}, "
                f"outliers>{tol_xy}px 的有 {bad} 处 (允许<={max_outliers})，疑似宫格不齐"
            )

    for i, yc in enumerate(ys, start=1):
        ys_band: list[int] = []
        for c in range(4):
            x0 = int(c * w / 4)
            x1 = int((c + 1) * w / 4)
            ys_band.append(_peak_y_in_band(mag, x0, x1, yc, search_py, h))
        bad = _count_outliers_from_median(ys_band, tol_xy)
        if bad > max_outliers:
            med = float(np.median(np.asarray(ys_band, dtype=np.float64)))
            raise ValueError(
                f"横线#{i} 四列格带内 y 与中位数偏差过大: ys={ys_band}, med≈{med:.1f}, "
                f"outliers>{tol_xy}px 的有 {bad} 处 (允许<={max_outliers})，疑似宫格不齐"
            )


def _validate_six_rulers_continuous(img: np.ndarray) -> None:
    """
    在理论 W/4、W/2、3W/4 三条竖线、H/4、H/2、3H/4 三条横线上，
    检验窄条内边缘/暗线响应沿全长是否足够连续（对齐规整 4×4；可拦不齐宫格）。
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    abs_x = np.abs(gx)
    abs_y = np.abs(gy)
    mag = abs_x + abs_y

    band = _GRID_RULER_BAND_PX
    xs = [w // 4, w // 2, (3 * w) // 4]
    ys = [h // 4, h // 2, (3 * h) // 4]

    for i, xc in enumerate(xs, start=1):
        prof = _profile_vertical_ruler(abs_x, abs_y, gray, xc, band, h, w)
        _continuity_from_profile(prof, f"竖线#{i}(x≈{xc})")

    for i, yc in enumerate(ys, start=1):
        prof = _profile_horizontal_ruler(abs_x, abs_y, gray, yc, band, h, w)
        _continuity_from_profile(prof, f"横线#{i}(y≈{yc})")

    _validate_ruler_quarter_bands_alignment(mag, h, w, xs, ys)


# ── 旧版校验（仅 GRID_VALIDATOR_LEGACY=1 时使用）──────────────────────────
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


def _validate_4x4_dividers_legacy(img: np.ndarray) -> None:
    """旧版：带状峰数量检测（易误杀合规图，仅 legacy 开启）。"""
    _DIVIDER_SEARCH_TOL_RATIO = float(os.getenv("GRID_DIVIDER_SEARCH_TOL_RATIO", "0.08"))
    _DIVIDER_MIN_STRENGTH_RATIO = float(os.getenv("GRID_DIVIDER_MIN_STRENGTH_RATIO", "0.60"))
    _DIVIDER_MIN_CONTINUITY = float(os.getenv("GRID_DIVIDER_MIN_CONTINUITY", "0.50"))

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    abs_x = np.abs(grad_x)
    abs_y = np.abs(grad_y)

    dark_mask = (gray < 65).astype(np.float32)
    col_score = abs_x.mean(axis=0) + 40.0 * dark_mask.mean(axis=0)
    row_score = abs_y.mean(axis=1) + 40.0 * dark_mask.mean(axis=1)

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

    min_col_gap = max(4, int((w / 4) * 0.12))
    min_row_gap = max(4, int((h / 4) * 0.12))
    if not (found_cols[0] + min_col_gap < found_cols[1] < found_cols[2] - min_col_gap):
        raise ValueError(f"竖向分割线位置异常: found={found_cols}, expect≈{expected_cols}")
    if not (found_rows[0] + min_row_gap < found_rows[1] < found_rows[2] - min_row_gap):
        raise ValueError(f"横向分割线位置异常: found={found_rows}, expect≈{expected_rows}")

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
                f"need>={col_gate:.3f}, continuity={continuity:.3f}"
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
                f"need>={row_gate:.3f}, continuity={continuity:.3f}"
            )

    expected_cols_arr = np.array(expected_cols, dtype=np.int32)
    expected_rows_arr = np.array(expected_rows, dtype=np.int32)
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
        if np.any(np.abs(peaks_arr - expected_cols_arr) > pos_tol_x):
            raise ValueError(
                f"第{r+1}行分割线位置漂移: peaks={peaks_arr.tolist()}, expect≈{expected_cols_arr.tolist()}"
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
        if np.any(np.abs(peaks_arr - expected_rows_arr) > pos_tol_y):
            raise ValueError(
                f"第{c+1}列分割线位置漂移: peaks={peaks_arr.tolist()}, expect≈{expected_rows_arr.tolist()}"
            )


# ── 新版校验：全局寻峰 4×4 结构检测 ──────────────────────────────────────────

def _find_n_peaks(profile: np.ndarray, n: int, min_dist: int, edge_margin: int) -> list[int]:
    """
    在 1D 投影曲线中贪心选取 n 个最高且间距 ≥ min_dist 的峰。
    峰定义为平滑后严格大于左右邻点的位置（排除边缘 margin）。
    返回排序后的峰坐标列表；不足 n 个则返回实际找到的数量。
    """
    length = profile.size
    if length < 3:
        return []

    smooth = _smooth_1d(profile)

    # 收集所有局部最大值（排除边缘 margin）
    candidates: list[tuple[float, int]] = []
    for i in range(1, length - 1):
        if smooth[i] > smooth[i - 1] and smooth[i] >= smooth[i + 1]:
            if edge_margin <= i <= length - 1 - edge_margin:
                candidates.append((float(smooth[i]), i))

    if not candidates:
        return []

    # 按峰高降序排列，贪心选取（保证间距 ≥ min_dist）
    candidates.sort(key=lambda x: x[0], reverse=True)

    picked: list[int] = []
    for _height, idx in candidates:
        if all(abs(idx - p) >= min_dist for p in picked):
            picked.append(idx)
        if len(picked) >= n:
            break

    return sorted(picked)


def _find_grid_dividers_global(img: np.ndarray) -> tuple[list[int], list[int]]:
    """
    全图投影自动发现实际分割线位置，不假设线恰好在 W/4 等数学位置。
    返回 (col_dividers, row_dividers)，理想情况各含 3 个坐标。
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)

    # 暗像素辅助：漫画/线稿风格中分割线通常为深色线
    dark = (gray < 70).astype(np.float32)

    # 垂直投影：每列累加水平边缘强度 + 暗像素响应
    col_profile = np.abs(gx).mean(axis=0).astype(np.float64) + 45.0 * dark.mean(axis=0)
    # 水平投影：每行累加垂直边缘强度 + 暗像素响应
    row_profile = np.abs(gy).mean(axis=1).astype(np.float64) + 45.0 * dark.mean(axis=1)

    min_dist = max(20, min(w, h) // 6)
    edge_margin = max(10, min(w, h) // 12)

    col_peaks = _find_n_peaks(col_profile, n=3, min_dist=min_dist, edge_margin=edge_margin)
    row_peaks = _find_n_peaks(row_profile, n=3, min_dist=min_dist, edge_margin=edge_margin)

    return col_peaks, row_peaks


def _validate_4x4_structure(img: np.ndarray) -> None:
    """
    新版宽松校验：全局寻峰验证 4×4 结构是否存在。

    只检查：
    - 恰好 3 条竖分割线 + 3 条横分割线；
    - 相邻分割线间距大致均匀（变异系数 ≤ GRID_SPACING_MAX_CV，默认 0.50）。
    
    不要求线沿全长贯通、不要求线恰好在 W/4/H/4 等理论位置。
    这样可以把「线略偏/略断但结构正确」的合格图放行，
    同时拦住合并格、不等大、非 4×4 的真不合格图。
    """
    h, w = img.shape[:2]
    col_peaks, row_peaks = _find_grid_dividers_global(img)

    # ── 数量检查 ──
    if len(col_peaks) != 3:
        raise ValueError(
            f"检测到 {len(col_peaks)} 条竖分割线（期望 3 条），col_peaks={col_peaks}，疑似非 4×4 布局"
        )
    if len(row_peaks) != 3:
        raise ValueError(
            f"检测到 {len(row_peaks)} 条横分割线（期望 3 条），row_peaks={row_peaks}，疑似非 4×4 布局"
        )

    # ── 间距均匀性检查 ──
    col_gaps = [col_peaks[i + 1] - col_peaks[i] for i in range(2)]
    row_gaps = [row_peaks[i + 1] - row_peaks[i] for i in range(2)]

    mean_col = float(np.mean(col_gaps))
    mean_row = float(np.mean(row_gaps))

    cv_col = float(np.std(col_gaps) / mean_col) if mean_col > 0 else 999.0
    cv_row = float(np.std(row_gaps) / mean_row) if mean_row > 0 else 999.0

    # 生图模型常产出略偏的 4×4 线位；过严会反复重试仍失败。可用环境变量收紧/放宽。
    max_cv = float(os.getenv("GRID_SPACING_MAX_CV", "0.50"))

    if cv_col > max_cv:
        raise ValueError(
            f"竖分割线间距不均匀: CV={cv_col:.3f} (允许≤{max_cv}), "
            f"col_peaks={col_peaks}, gaps={col_gaps}，疑似面板大小不一"
        )
    if cv_row > max_cv:
        raise ValueError(
            f"横分割线间距不均匀: CV={cv_row:.3f} (允许≤{max_cv}), "
            f"row_peaks={row_peaks}, gaps={row_gaps}，疑似面板大小不一"
        )

    # ── 理论锚点贴合检查（防止“整齐但整体偏位”的假 4×4） ──
    expected_cols = [w // 4, w // 2, (3 * w) // 4]
    expected_rows = [h // 4, h // 2, (3 * h) // 4]
    max_dev_ratio = float(os.getenv("GRID_PEAK_ANCHOR_MAX_DEV_RATIO", "0.15"))

    col_devs = [abs(col_peaks[i] - expected_cols[i]) for i in range(3)]
    row_devs = [abs(row_peaks[i] - expected_rows[i]) for i in range(3)]
    max_col_dev_ratio = max(col_devs) / float(w)
    max_row_dev_ratio = max(row_devs) / float(h)

    if max_col_dev_ratio > max_dev_ratio:
        raise ValueError(
            f"竖分割线偏离理论锚点过大: max_dev_ratio={max_col_dev_ratio:.3f} "
            f"(允许≤{max_dev_ratio}), col_peaks={col_peaks}, expected={expected_cols}"
        )
    if max_row_dev_ratio > max_dev_ratio:
        raise ValueError(
            f"横分割线偏离理论锚点过大: max_dev_ratio={max_row_dev_ratio:.3f} "
            f"(允许≤{max_dev_ratio}), row_peaks={row_peaks}, expected={expected_rows}"
        )

    # 调试输出：便于了解实际检测到的分割线位置
    print(
        f"  ✓ [Grid4x4] 结构通过: col_peaks={col_peaks} (预期≈{expected_cols}), "
        f"row_peaks={row_peaks} (预期≈{expected_rows}), "
        f"CV_col={cv_col:.3f}, CV_row={cv_row:.3f}, "
        f"max_dev_col={max_col_dev_ratio:.3f}, max_dev_row={max_row_dev_ratio:.3f}"
    )


def validate_grid_comic_layout(grid_path: Path) -> None:
    """
    读取已落盘的宫格 PNG，校验：
    - 横屏 16:9（在容差内）；
    - 宽高均可被 4 整除（与 process_16_grid 一致）；
    - 默认：全局寻峰 4×4 结构检测（容忍线位偏移）；
    - 环境变量 GRID_VALIDATOR_LEGACY=1 时使用旧版带状峰/六线贯通校验。
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

    if _GRID_VALIDATOR_LEGACY:
        _validate_4x4_dividers_legacy(img)
    else:
        _validate_4x4_structure(img)
