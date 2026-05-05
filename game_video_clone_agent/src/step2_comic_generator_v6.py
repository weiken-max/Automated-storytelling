"""
🎨 16 宫格爆兵流水线 (src/step2_comic_generator_v6.py)
读取 final narrative，每次聚合 16 个 prompt，生成 4x4 宫格，并调用切图脚手架落盘
"""
import json
import os
import sys
import asyncio
import subprocess
from pathlib import Path
from dotenv import load_dotenv
import cv2
import numpy as np
from datetime import datetime
from io import BytesIO
from PIL import Image

# ── Windows GBK 终端编码修复 ──
if hasattr(sys.stdout, "buffer"):
    from io import TextIOWrapper
    sys.stdout = TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.run_context import get_paths, get_current_run_id
from src.project_vault import backup as vault_backup
from src.image_engine import generate_image
from src.image_processor import process_16_grid
from src.grid_validators import validate_grid_comic_layout
from src.visual_era_context import build_image_global_prefix

NARRATIVE_FINAL_PATH = None
STORYBOARDS_DIR = None
LOGS_DIR = None
MAX_BATCH_RETRIES = 3
RUN_ID = "unknown"


def _chain_step3() -> None:
    """
    Step2 成功后链式调用 Step3。
    由环境变量 CHAIN_STEP3=1 激活（Hub 在拉起 Step2 时注入）。
    链式调用时故意清除 CHAIN_STEP3，防止 Step3 再次触发链式死循环。
    成功后写 logs/step3_chained_ok.json，Hub 据此跳过第二次 Step3。
    """
    print("\n[CHAIN] CHAIN_STEP3=1 已激活，自动链式执行 Step3 (step3_assembler_v6.py)...")
    env = {k: v for k, v in os.environ.items() if k != "CHAIN_STEP3"}
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(
            [sys.executable, str(BASE_DIR / "src" / "step3_assembler_v6.py")],
            cwd=str(BASE_DIR),
            env=env,
        )
        if proc.returncode == 0:
            if LOGS_DIR:
                import time as _time
                LOGS_DIR.mkdir(parents=True, exist_ok=True)
                (LOGS_DIR / "step3_chained_ok.json").write_text(
                    json.dumps({"ok": True, "ts": _time.time()}, ensure_ascii=False),
                    encoding="utf-8",
                )
            print("[CHAIN] Step3 链式执行完成！成片已落盘。")
        else:
            print(f"[CHAIN] Step3 链式执行失败 (exit={proc.returncode})，Hub 将在下次机会重试。")
    except Exception as e:
        print(f"[CHAIN] Step3 链式调用异常: {e}")


class Step2StageError(Exception):
    def __init__(self, stage: str, message: str, error_code: str = "STEP2_STAGE_ERROR", raw_response_snippet: str = ""):
        super().__init__(message)
        self.stage = stage
        self.error_code = error_code
        self.raw_response_snippet = (raw_response_snippet or "")[:500]


def _log_failure(run_id: str, batch_index: int, total_batches: int, start_idx: int, end_idx: int, attempt: int, err: Exception):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    stage = "UNKNOWN"
    error_code = "STEP2_UNKNOWN"
    raw_snippet = ""
    if isinstance(err, Step2StageError):
        stage = err.stage
        error_code = err.error_code
        raw_snippet = err.raw_response_snippet
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "run_id": run_id,
        "task_id": "step2",
        "batch_index": batch_index,
        "total_batches": total_batches,
        "subshot_range": f"S_{start_idx:03d}~S_{end_idx:03d}",
        "attempt": attempt,
        "stage": stage,
        "error_code": error_code,
        "error_type": type(err).__name__,
        "error_message": str(err)[:500],
        "raw_response_snippet": raw_snippet,
    }
    with (LOGS_DIR / "step2_failures.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _write_report(report: dict):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    (LOGS_DIR / "step2_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _bytes_debug_snippet(blob: bytes, head_len: int = 64) -> str:
    """提取返回字节头信息，便于定位“非图片/损坏图片”问题。"""
    if not blob:
        return "empty-bytes"
    head = blob[:head_len]
    hex_part = head.hex()
    text_part = head.decode("utf-8", errors="replace")
    return f"len={len(blob)} | text_head={text_part!r} | hex_head={hex_part}"

def chunk_list(lst, n):
    """将列表按步长 n 拆分"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def _collect_ordered_paths_for_batch(batch_shots: list) -> list:
    ordered: list[str] = []
    for shot in batch_shots:
        paths = shot.get("ref_image_paths")
        if isinstance(paths, list) and paths:
            for p in paths:
                ps = str(p).strip()
                if ps and ps not in ordered:
                    ordered.append(ps)
        al = str(shot.get("anchor_look") or "").strip()
        if al and al not in ordered:
            ordered.append(al)
    return ordered


def _path_to_anchor_key(abs_path: str, physical_anchors: dict) -> str:
    if not abs_path:
        return ""
    try:
        target = str(Path(abs_path).resolve())
    except Exception:
        target = str(abs_path)
    for k, v in (physical_anchors or {}).items():
        if not v:
            continue
        try:
            if str(Path(v).resolve()) == target:
                return str(k)
        except Exception:
            if str(v).strip() == target:
                return str(k)
    return ""


def _ref_key_to_english_label(ref_key: str, cast_registry: dict) -> str:
    cr = cast_registry or {}
    pro = cr.get("protagonist") or {}
    pname = str(pro.get("display_name_en") or "Protagonist").strip()
    if ref_key in {"child", "youth", "middle", "elderly"}:
        return f"{pname} (protagonist, life stage {ref_key})"
    if ref_key.startswith("supporting_"):
        rid = ref_key[len("supporting_"):]
        for s in cr.get("supporting") or []:
            if s.get("role_id") == rid:
                dn = str(s.get("display_name_en") or rid).strip()
                return f"{dn} (supporting)"
        return f"{rid} (supporting)"
    return ref_key or "reference"


def _build_global_ref_mapping_sentence(
    ordered_paths: list, physical_anchors: dict, cast_registry: dict
) -> str:
    if not ordered_paths:
        return ""
    parts: list[str] = []
    for i, p in enumerate(ordered_paths, 1):
        k = _path_to_anchor_key(p, physical_anchors)
        label = _ref_key_to_english_label(k, cast_registry) if k else f"reference_{i}"
        parts.append(f"{i}) {label}")
    return (
        "REFERENCE IMAGES ORDER (inline images follow this exact order; match each character face to the named reference only): "
        + "; ".join(parts)
        + "\n\n"
    )


def _save_valid_grid_image(img_bytes: bytes, grid_path: Path) -> tuple[bool, str]:
    """
    对生图返回做解码校验后再落盘，避免写入损坏字节导致后续 OpenCV 读取崩溃。
    """
    if not img_bytes:
        return False, "empty-bytes"
    try:
        arr = np.frombuffer(img_bytes, dtype=np.uint8)
        decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if decoded is not None:
            # Windows + 中文路径下 cv2.imwrite 可能返回 False，改为先编码再用 Python 写盘。
            ok_enc, enc = cv2.imencode(".png", decoded)
            if not ok_enc:
                return False, "io-write-failed | cv2.imencode returned False"
            try:
                grid_path.write_bytes(enc.tobytes())
                return True, "opencv"
            except Exception as write_err:
                return False, f"io-write-failed | path={grid_path} | err={write_err}"

        # OpenCV 解码失败时，尝试 Pillow 兜底（常见于部分编码格式兼容性差异）
        try:
            pil_img = Image.open(BytesIO(img_bytes)).convert("RGB")
            pil_img.save(grid_path, format="PNG")
            return True, "pillow-fallback"
        except Exception as pil_err:
            return False, f"decode-failed | {_bytes_debug_snippet(img_bytes)} | pillow_err={pil_err}"
    except Exception as e:
        return False, f"decode-exception={e} | {_bytes_debug_snippet(img_bytes)}"

async def generate_grid_batch(
    batch_shots: list,
    batch_index: int,
    total_batches: int,
    global_era_prefix: str = "",
    physical_anchors: dict | None = None,
    cast_registry: dict | None = None,
):
    """提交 16 宫格生图请求"""
    print(f"\n  [Grid Render] 正在生成第 {batch_index}/{total_batches} 批次 (包含 {len(batch_shots)} 个分镜)...")

    ordered_paths = _collect_ordered_paths_for_batch(batch_shots)
    global_ref_txt = _build_global_ref_mapping_sentence(
        ordered_paths, physical_anchors or {}, cast_registry or {}
    )

    # 构建聚合 Prompt（前置时代锁 + 参考图序说明 + 宫格硬约束）
    combined_prompt = (global_era_prefix or "") + global_ref_txt + (
        "Generate ONE single 16:9 landscape canvas comic page. "
        "Strict 4×4 grid only: exactly 16 EQUAL rectangular panels; NO merged cells; NO 5×3 or irregular layouts. "
        "Panel order is HARD RULE: left-to-right, top-to-bottom, Panel 1…16. "
        "Do not shuffle or mirror. "
        "Cyanide and Happiness comic style, flat illustration, pure 2D. "
    )
    combined_prompt += "The grid contains the following sequential scenes:\n"

    batch_refs: list[str] = list(ordered_paths)
    for i, shot in enumerate(batch_shots):
        combined_prompt += f"Panel {i+1}: {shot['visual_prompt']}\n"

    # 尾批不足 16 时强制补齐空面板，保持“16:9 + 4x4 + Panel 1..16”硬约束不变形。
    if len(batch_shots) < 16:
        for panel_idx in range(len(batch_shots) + 1, 17):
            combined_prompt += (
                f"Panel {panel_idx}: EMPTY PANEL. "
                "Pure white background, no character, no object, no text.\n"
            )
        
    # 生图 API：Gemini 在 imageConfig 中传档位；使用 2560x1440 对应 16:9 + 2K（见 _build_gemini_image_config）。
    try:
        img_bytes = await generate_image(
            prompt=combined_prompt,
            image_refs=batch_refs,
            size="2560x1440",
        )
    except Exception as e:
        raise Step2StageError("IMAGE_GEN_API", f"调用生图模型异常: {e}", error_code="IMAGE_GEN_API_EXCEPTION")
    
    if not img_bytes:
        raise Step2StageError("IMAGE_GEN_API", f"第 {batch_index} 批次生成失败（空响应）。", error_code="IMAGE_GEN_EMPTY_RESPONSE")

    grid_path = STORYBOARDS_DIR / f"grid_batch_{batch_index:03d}.png"
    ok, detail = _save_valid_grid_image(img_bytes, grid_path)
    if not ok:
        stage = "IO_WRITE" if str(detail).startswith("io-write-failed") else "IMAGE_DECODE"
        code = "IO_WRITE_FAILED" if stage == "IO_WRITE" else "IMAGE_DECODE_FAILED"
        raise Step2StageError(
            stage,
            f"第 {batch_index} 批次栅格图保存失败（{stage}）。",
            error_code=code,
            raw_response_snippet=detail,
        )
    if detail == "pillow-fallback":
        print(f"  ⚠️ 第 {batch_index} 批次使用 Pillow 兜底解码成功（OpenCV 不兼容该返回格式）。")

    try:
        validate_grid_comic_layout(grid_path)
    except ValueError as ve:
        raise Step2StageError(
            "GRID_VALIDATION",
            f"第 {batch_index} 批次宫格图未通过布局校验（将重试）：{ve}",
            error_code="GRID_LAYOUT_INVALID",
            raw_response_snippet=str(ve)[:200],
        )
    return grid_path

async def main():
    global NARRATIVE_FINAL_PATH, STORYBOARDS_DIR, LOGS_DIR, RUN_ID
    paths = get_paths(create_if_missing=False)
    if not paths:
        print("❌ 未检测到当前 Run-ID。请先执行 story_planner/step1 初始化运行批次。")
        sys.exit(1)
    NARRATIVE_FINAL_PATH = paths["scripts_dir"] / "narrative_v6_final.json"
    STORYBOARDS_DIR = paths["storyboards_dir"]
    LOGS_DIR = paths["logs_dir"]
    RUN_ID = get_current_run_id() or "unknown"

    print("\n=======================================================")
    print("[Phase 4-A] 16 宫格生成与智能裁切")
    print(f"[Run] 当前批次: {RUN_ID}")
    print("=======================================================")
    
    if not NARRATIVE_FINAL_PATH.exists():
        print("❌ 找不到叙事蓝图 narrative_v6_final.json，请先执行 Phase 3。")
        sys.exit(1)
        
    data = json.loads(NARRATIVE_FINAL_PATH.read_text(encoding="utf-8"))
    timeline = data.get("timeline", [])
    
    if not timeline:
        print("❌ 蓝图 timeline 为空。")
        sys.exit(1)

    era_raw = (data.get("metadata") or {}).get("era")
    global_era_prefix = build_image_global_prefix(era_raw)

    full_story_path = paths["scripts_dir"] / "full_story_v6.json"
    physical_flat: dict = {}
    cast_reg: dict = {}
    if full_story_path.exists():
        try:
            fs_doc = json.loads(full_story_path.read_text(encoding="utf-8"))
            md_fs = fs_doc.get("master_design") or {}
            physical_flat = md_fs.get("physical_char_anchors") or {}
            cast_reg = md_fs.get("cast_registry") or {}
            if not era_raw:
                era_raw = (fs_doc.get("metadata") or {}).get("era")
                global_era_prefix = build_image_global_prefix(era_raw)
        except Exception:
            pass
        
    STORYBOARDS_DIR.mkdir(parents=True, exist_ok=True)
    
    # 清理旧数据
    for f in STORYBOARDS_DIR.glob("*.png"):
        f.unlink()
        
    # 按 16 个一组分批
    batches = list(chunk_list(timeline, 16))
    total_batches = len(batches)
    current_subshot_idx = 1
    successful_batches = 0
    failed_batches = 0

    for i, batch in enumerate(batches, 1):
        batch_start = current_subshot_idx
        batch_end = current_subshot_idx + len(batch) - 1
        batch_ok = False

        for attempt in range(1, MAX_BATCH_RETRIES + 1):
            try:
                grid_path = await generate_grid_batch(
                    batch,
                    i,
                    total_batches,
                    global_era_prefix=global_era_prefix,
                    physical_anchors=physical_flat,
                    cast_registry=cast_reg,
                )
                print("  [Process] 正在进行 16 宫格均分切图与 Real-ESRGAN 高清...")
                try:
                    next_idx = process_16_grid(grid_path, STORYBOARDS_DIR, current_subshot_idx)
                except Exception as crop_err:
                    stage = "UPSCALE" if "realesrgan" in str(crop_err).lower() else "GRID_CROP"
                    code = "UPSCALE_FAILED" if stage == "UPSCALE" else "GRID_CROP_FAILED"
                    raise Step2StageError(stage, f"第 {i} 批次切图/高清失败: {crop_err}", error_code=code)
                vault_backup(grid_path, f"storyboards/{grid_path.name}")
                current_subshot_idx = next_idx
                successful_batches += 1
                batch_ok = True
                print(f"  ✅ 第 {i} 批次完成（attempt {attempt}/{MAX_BATCH_RETRIES}）。")
                break
            except Exception as e:
                _log_failure(RUN_ID, i, total_batches, batch_start, batch_end, attempt, e)
                print(f"  ❌ 第 {i} 批次失败（attempt {attempt}/{MAX_BATCH_RETRIES}）: {e}")
                if attempt >= MAX_BATCH_RETRIES:
                    failed_batches += 1
                    report = {
                        "ok": False,
                        "run_id": RUN_ID,
                        "total_batches": total_batches,
                        "successful_batches": successful_batches,
                        "failed_batches": failed_batches,
                        "total_shots": len(timeline),
                        "generated_shots": len(list(STORYBOARDS_DIR.glob('S_*.png'))),
                        "blocking_batch": i,
                        "subshot_range": f"S_{batch_start:03d}~S_{batch_end:03d}",
                        "reason": str(e)[:500],
                    }
                    _write_report(report)
                    raise Step2StageError(
                        "BATCH_ABORTED",
                        f"第 {i}/{total_batches} 批次连续 {MAX_BATCH_RETRIES} 次失败，已中止 Step2。"
                    )

        if not batch_ok:
            # 理论上不会到这里；到这里意味着已在上方抛错中止。
            break
            
    # 因为存在尾部批次不满 16 个的情况，多切出来的冗余纯白/黑图可以在这里清理（这里保留简单实现）
    # 实际所需总分镜数就是 len(timeline)
    for f in STORYBOARDS_DIR.glob("S_*.png"):
        idx_str = f.stem.split('_')[1]
        if int(idx_str) > len(timeline):
            f.unlink()
            
    generated_shots = len(list(STORYBOARDS_DIR.glob("S_*.png")))
    report = {
        "ok": True,
        "run_id": RUN_ID,
        "total_batches": total_batches,
        "successful_batches": successful_batches,
        "failed_batches": failed_batches,
        "total_shots": len(timeline),
        "generated_shots": generated_shots,
    }
    _write_report(report)
    print(f"\n[DONE] 所有分镜图像生成并裁切完成！单镜图已落盘至 {STORYBOARDS_DIR}")
    print(
        f"[Report] batches={successful_batches}/{total_batches} | "
        f"shots={generated_shots}/{len(timeline)} | report={LOGS_DIR / 'step2_report.json'}"
    )

    # 链式 Step3：仅当 Hub 注入 CHAIN_STEP3=1 时执行
    if os.environ.get("CHAIN_STEP3") == "1":
        _chain_step3()

if __name__ == "__main__":
    asyncio.run(main())
