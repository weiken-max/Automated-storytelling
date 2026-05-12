"""
🎞️ 剧情解构与物理时间轴底座 (src/step1_writer_v6.py)
==========================================================
阶段二 (Phase 2)：读取纯净长文案 -> 生成音频/SRT -> LLM 按行号切 Beat（默认 6–10 段，硬上限 10）-> 产出 pseudo_srt.json
阶段三 (Phase 3)：LLM 打 <subshot> + visual_prompt（默认可并行最多 3 路 Beat，环境变量 PHASE3_MAX_WORKERS）-> 线性插值 trigger_time -> 产出 narrative_v6_final.json
"""

import json
import os
import shutil
import sys
import argparse
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# ── 路径与环境配置 ──
load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
DATA_DIR = BASE_DIR / "data"

from src.api_audit import PHASE_AUDIO_BEATS, PHASE_STORYBOARD, log_event
from src.style_config import LLM_API_KEY, LLM_BASE_URL, MODEL_LLM, VOICE_ROLE, VOICE_RATE
from src.project_vault import backup as vault_backup
from src.run_context import get_paths, get_current_run_id
from src.visual_era_context import build_writer_era_section

MODEL_WRITER = MODEL_LLM

_paths = get_paths(create_if_missing=True)
SCRIPTS_DIR = _paths["scripts_dir"]
AUDIO_DIR = _paths["audio_dir"]
LOGS_DIR = _paths["logs_dir"]
FULL_STORY_V6_PATH = SCRIPTS_DIR / "full_story_v6.json"
REFS_PROMPT_PATH = SCRIPTS_DIR / "refs-prompt.json"
PSEUDO_SRT_PATH = SCRIPTS_DIR / "pseudo_srt.json"
MASTER_SRT_PATH = AUDIO_DIR / "master_srt.json"
NARRATIVE_FINAL_PATH = SCRIPTS_DIR / "narrative_v6_final.json"

# Edge-TTS 单次合成常见硬上限约 600s（10min），长旁白需分块拼接音轨与字幕
TTS_CHUNK_MAX_CHARS = 2200
TTS_NETWORK_MAX_RETRIES = 4
TTS_NETWORK_RETRY_BASE_SEC = 1.5


def get_client():
    return OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)


# ── Phase 2 Beat 数量（影响 Phase 3 的 LLM 往返次数：每 Beat 约 2 次调用）────────
MIN_BEATS_PHASE2 = 6
MAX_BEATS_PHASE2 = 10

# ── Phase 3 专用常量与异常 ──────────────────────────────────────────────────
MAX_VISION_LLM_RETRIES = 5  # 每个 Beat 最多重试次数（两步各自计入同一轮）
# Phase 3 并行：同时处理的 Beat 数上限（单 Beat 内部仍为 tag→prompt 串行）。设为 1 即退回串行。
PHASE3_MAX_WORKERS_DEFAULT = 3


def _phase3_pool_workers(n_beats: int) -> int:
    raw = os.environ.get("PHASE3_MAX_WORKERS", str(PHASE3_MAX_WORKERS_DEFAULT))
    try:
        w = int(raw.strip())
    except ValueError:
        w = PHASE3_MAX_WORKERS_DEFAULT
    if n_beats <= 0:
        return 1
    return max(1, min(w, n_beats))


def _phase3_text_anchors_from_refs_prompt(refs_path: Path) -> dict:
    """将 scripts/refs-prompt.json 转为 Phase3「角色外观语义锚点」扁平 dict（键与 physical_char_anchors 逻辑键对齐）。"""
    if not refs_path.is_file():
        return {}
    try:
        data = json.loads(refs_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict] = {}
    pro = data.get("protagonist")
    if isinstance(pro, dict):
        for st, d in (pro.get("stage_prompts") or {}).items():
            if isinstance(d, dict):
                block = {k: d[k] for k in ("english_prompt", "anchor_description") if d.get(k)}
                if block:
                    out[str(st)] = block
    for x in data.get("supporting") or []:
        if not isinstance(x, dict):
            continue
        rid = str(x.get("role_id") or "").strip()
        if not rid:
            continue
        key = f"supporting_{rid}"
        block = {}
        for k in ("english_prompt", "anchor_description", "display_name_en"):
            v = x.get(k)
            if v is not None and str(v).strip():
                block[k] = v
        if block:
            out[key] = block
    return out


class Phase3BeatError(Exception):
    """Phase 3 某个 Beat 分镜失败，携带诊断信息供主循环打印后 sys.exit(1)。"""

    def __init__(self, beat_id: str, stage: str, detail: str, beat_time_range: str = ""):
        self.beat_id = beat_id
        self.stage = stage
        self.detail = detail
        self.beat_time_range = beat_time_range
        super().__init__(f"[{beat_id}][{stage}] {detail}")


def _extract_json_object(raw: str) -> dict | None:
    t = (raw or "").strip()
    if not t:
        return None
    try:
        data = json.loads(t)
        return data if isinstance(data, dict) else None
    except Exception:
        pass

    if t.startswith("```"):
        lines = t.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
        try:
            data = json.loads(t)
            return data if isinstance(data, dict) else None
        except Exception:
            pass

    start = t.find("{")
    end = t.rfind("}")
    if start >= 0 and end > start:
        body = t[start : end + 1]
        try:
            data = json.loads(body)
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    return None


def _dump_phase3_llm_raw(stage: str, beat_id: str, attempt: int, raw: str, meta: str = "") -> None:
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        safe_beat = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in (beat_id or "unknown"))
        path = LOGS_DIR / f"phase3_{stage}_{safe_beat}_attempt{attempt}.log"
        payload = f"[meta]\n{meta}\n\n[raw]\n{raw or ''}\n"
        path.write_text(payload, encoding="utf-8")
    except Exception:
        pass


def parse_vtt_time(vtt_time_str: str) -> float:
    """解析 VTT 时间戳 (00:00:02.500) 为秒数"""
    parts = vtt_time_str.replace(',', '.').split(':')
    seconds = 0.0
    if len(parts) == 3:
        h, m, s = parts
        seconds = int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        seconds = int(m) * 60 + float(s)
    return round(seconds, 3)


def _seconds_to_vtt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    sec = seconds % 60
    whole = int(sec)
    ms = int(round((sec - whole) * 1000))
    if ms >= 1000:
        whole += 1
        ms = 0
    return f"{h:02d}:{m:02d}:{whole:02d},{ms:03d}"


def _ffprobe_duration_seconds(media_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(media_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        return -1.0
    try:
        return float((proc.stdout or "0").strip() or "0")
    except ValueError:
        return -1.0


def _parse_vtt_lines_to_srt_data(lines: list) -> list:
    """将 VTT 行列表解析为 master_srt 风格的 cue 列表。"""
    srt_data = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if '-->' in line:
            times = line.split('-->')
            start_time = parse_vtt_time(times[0].strip())
            end_time = parse_vtt_time(times[1].strip())

            if i + 1 < len(lines):
                text_content = lines[i + 1].strip()
                j = i + 2
                while j < len(lines) and lines[j].strip() and '-->' not in lines[j]:
                    text_content += " " + lines[j].strip()
                    j += 1

                if len(text_content.replace(' ', '')) > 0:
                    srt_data.append({
                        "start_time": start_time,
                        "end_time": end_time,
                        "text": text_content,
                    })
                i = j - 1
        i += 1
    return srt_data


def _split_text_for_edge_tts(text: str, max_chars: int = TTS_CHUNK_MAX_CHARS) -> list[str]:
    """按句号等切分长旁白，避免单次 Edge 合成触发 ~600s 音频截断。"""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        j = min(i + max_chars, n)
        if j < n:
            best = -1
            for sep in ("。", "！", "？", "\n"):
                p = text.rfind(sep, i, j)
                if p > best:
                    best = p
            if best >= i + max(120, max_chars // 5):
                j = best + 1
        chunk = text[i:j].strip()
        if chunk:
            chunks.append(chunk)
        i = j
    return chunks


def _run_edge_tts_to_files(text: str, audio_path: Path, vtt_path: Path) -> None:
    temp_txt = audio_path.with_suffix(".txt")
    temp_txt.write_text(text, encoding="utf-8")
    cmd_candidates = [
        [
            "edge-tts",
            "-f", str(temp_txt),
            "--write-media", str(audio_path),
            "--write-subtitles", str(vtt_path),
            "--voice", str(VOICE_ROLE),
            "--rate", str(VOICE_RATE),
        ],
        [
            sys.executable,
            "-m",
            "edge_tts",
            "-f", str(temp_txt),
            "--write-media", str(audio_path),
            "--write-subtitles", str(vtt_path),
            "--voice", str(VOICE_ROLE),
            "--rate", str(VOICE_RATE),
        ],
    ]
    try:
        for idx, cmd in enumerate(cmd_candidates, start=1):
            try:
                for attempt in range(1, TTS_NETWORK_MAX_RETRIES + 1):
                    try:
                        t_edge = time.perf_counter()
                        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        log_event(
                            PHASE_AUDIO_BEATS,
                            "edge_tts",
                            "tts_edge",
                            ok=True,
                            duration_ms=(time.perf_counter() - t_edge) * 1000,
                            attempt=attempt,
                            extra={"cmd_candidate": idx, "voice": str(VOICE_ROLE)},
                        )
                        return
                    except subprocess.CalledProcessError as e:
                        raw_err = e.stderr if e.stderr is not None else e.output
                        if isinstance(raw_err, bytes):
                            err_text = raw_err.decode("utf-8", errors="ignore")
                        else:
                            err_text = str(raw_err or "")
                        transient = any(
                            key in err_text
                            for key in (
                                "ClientConnectorError",
                                "ConnectionResetError",
                                "Cannot connect to host",
                                "TimeoutError",
                                "ServerDisconnectedError",
                            )
                        )
                        log_event(
                            PHASE_AUDIO_BEATS,
                            "edge_tts",
                            "tts_edge",
                            ok=False,
                            duration_ms=(time.perf_counter() - t_edge) * 1000,
                            attempt=attempt,
                            error=err_text[:400],
                            extra={"cmd_candidate": idx, "transient": transient},
                        )
                        if transient and attempt < TTS_NETWORK_MAX_RETRIES:
                            backoff = TTS_NETWORK_RETRY_BASE_SEC * (2 ** (attempt - 1))
                            print(
                                f"  ⚠️ [TTS] 网络抖动（命令候选 {idx}）第 {attempt}/{TTS_NETWORK_MAX_RETRIES} 次失败，"
                                f"{backoff:.1f}s 后重试..."
                            )
                            time.sleep(backoff)
                            continue
                        raise RuntimeError(err_text)
            except FileNotFoundError:
                if idx == len(cmd_candidates):
                    raise
                continue
        raise FileNotFoundError("edge-tts command/module not found")
    except FileNotFoundError:
        print("❌ [FATAL] 找不到 edge-tts 命令。请在终端运行: pip install edge-tts")
        sys.exit(1)
    except RuntimeError as e:
        print(f"❌ [TTS] 音频生成失败: {e}")
        sys.exit(1)
    finally:
        temp_txt.unlink(missing_ok=True)


def _concat_mp3_files(part_paths: list[Path], out_path: Path) -> None:
    if not shutil.which("ffmpeg"):
        print("❌ [FATAL] 拼接长音频需要 ffmpeg，请安装并加入 PATH。")
        sys.exit(1)
    if len(part_paths) == 1:
        shutil.copyfile(part_paths[0], out_path)
        return
    fd, list_path = tempfile.mkstemp(suffix=".txt", text=True)
    os.close(fd)
    try:
        list_file = Path(list_path)
        lines = []
        for p in part_paths:
            pp = p.resolve().as_posix().replace("'", "'\\''")
            lines.append(f"file '{pp}'")
        list_file.write_text("\n".join(lines), encoding="utf-8")
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(out_path),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    finally:
        try:
            list_file.unlink(missing_ok=True)
        except Exception:
            pass


def _generate_master_audio_chunked(text: str, audio_path: Path) -> list:
    chunks = _split_text_for_edge_tts(text, TTS_CHUNK_MAX_CHARS)
    print(f"  🔊 [TTS] 长旁白分 {len(chunks)} 段合成（每段约 ≤{TTS_CHUNK_MAX_CHARS} 字，规避 Edge 单次 ~10 分钟截断）...")
    vtt_path = audio_path.with_suffix(".vtt")
    tmp_root = audio_path.parent / "_tts_chunk_merge"
    tmp_root.mkdir(parents=True, exist_ok=True)
    merged_cues: list[dict] = []
    mp3_parts: list[Path] = []
    offset_sec = 0.0
    try:
        for idx, ch in enumerate(chunks):
            part_mp3 = tmp_root / f"part_{idx:03d}.mp3"
            part_vtt = tmp_root / f"part_{idx:03d}.vtt"
            _run_edge_tts_to_files(ch, part_mp3, part_vtt)
            dur = _ffprobe_duration_seconds(part_mp3)
            if dur <= 0:
                print(f"❌ [TTS] 分块 {idx + 1} 音轨时长异常")
                sys.exit(1)
            vtt_lines = part_vtt.read_text(encoding="utf-8").strip().split("\n")
            part_cues = _parse_vtt_lines_to_srt_data(vtt_lines)
            for c in part_cues:
                merged_cues.append({
                    "start_time": round(c["start_time"] + offset_sec, 3),
                    "end_time": round(c["end_time"] + offset_sec, 3),
                    "text": c["text"],
                })
            offset_sec += dur
            mp3_parts.append(part_mp3)

        _concat_mp3_files(mp3_parts, audio_path)
        final_dur = _ffprobe_duration_seconds(audio_path)
        if merged_cues and final_dur > 0:
            last_end = max(x["end_time"] for x in merged_cues)
            drift = abs(final_dur - last_end)
            if drift > 0.5:
                print(f"  ⚠️ [TTS] 拼接后音长 {final_dur:.2f}s 与字幕末轴 {last_end:.2f}s 相差 {drift:.2f}s（通常可接受）")

        # 写出合并后的 WebVTT，便于人工核对
        vtt_body = ["WEBVTT", ""]
        for i, c in enumerate(merged_cues, 1):
            vtt_body.append(str(i))
            vtt_body.append(
                f"{_seconds_to_vtt_timestamp(c['start_time'])} --> {_seconds_to_vtt_timestamp(c['end_time'])}"
            )
            vtt_body.append(c["text"])
            vtt_body.append("")
        vtt_path.write_text("\n".join(vtt_body), encoding="utf-8")

        MASTER_SRT_PATH.write_text(json.dumps(merged_cues, ensure_ascii=False, indent=2), encoding="utf-8")
        vault_backup(MASTER_SRT_PATH, f"audio/{MASTER_SRT_PATH.name}")
        print(f"  ✅ [TTS] 分块拼接完成，音轨约 {final_dur:.1f}s，共 {len(merged_cues)} 条字幕轴。")
        return merged_cues
    finally:
        try:
            shutil.rmtree(tmp_root, ignore_errors=True)
        except Exception:
            pass


def generate_master_audio_and_srt(text: str, audio_path: Path) -> list:
    """调用 edge-tts 生成音频并解析 VTT 为 JSON SRT，构建绝对物理时间轴。
    长文本自动分块合成并拼接，避免 Edge 单次 ~600s 截断导致「有字幕、无声音」。"""
    if len(text) > TTS_CHUNK_MAX_CHARS:
        return _generate_master_audio_chunked(text, audio_path)

    print("  🔊 [TTS] 正在调用 Edge-TTS 生成主音频与物理字幕...")
    vtt_path = audio_path.with_suffix(".vtt")
    _run_edge_tts_to_files(text, audio_path, vtt_path)

    lines = vtt_path.read_text(encoding="utf-8").strip().split("\n")
    srt_data = _parse_vtt_lines_to_srt_data(lines)

    audio_dur = _ffprobe_duration_seconds(audio_path)
    if srt_data and audio_dur > 0:
        last_end = max(x["end_time"] for x in srt_data)
        if last_end > audio_dur + 1.0:
            print(
                f"  ⚠️ [TTS] 检测到音轨 {audio_dur:.1f}s 短于字幕末轴 {last_end:.1f}s（Edge 单次合成可能被截断），"
                f"改用分块重合成..."
            )
            return _generate_master_audio_chunked(text, audio_path)

    MASTER_SRT_PATH.write_text(json.dumps(srt_data, ensure_ascii=False, indent=2), encoding="utf-8")
    vault_backup(MASTER_SRT_PATH, f"audio/{MASTER_SRT_PATH.name}")
    print(f"  ✅ [TTS] 物理时间轴锚定成功！共解析出 {len(srt_data)} 个微句子 (Cues)。")
    return srt_data

def chunk_beats_by_llm(srt_data: list) -> list:
    """通过行号锚定消除大模型时间幻觉，让LLM只做逻辑切分"""
    print("  🧠 [LLM] 正在给纯净文本打临时行号，并委派大模型进行 Beat 逻辑切分...")
    
    numbered_lines = []
    for idx, item in enumerate(srt_data):
        numbered_lines.append(f"[{idx}] {item['text']}")
    text_payload = "\n".join(numbered_lines)
    
    system_prompt = f"""你是一个顶级的电影剪辑指导。
任务：将我提供的【带行号的连续旁白】，按照叙事起伏划分为 {MIN_BEATS_PHASE2}-{MAX_BEATS_PHASE2} 个连续的剧情节拍 (Beat)。

【钢铁纪律】：
1. 完整覆盖：必须从行号 [0] 开始，一直覆盖到最大行号 [{len(srt_data)-1}]，绝不允许遗漏任何一句话。
2. 严丝合缝：下一个 Beat 的 start_index 必须严格等于上一个 Beat 的 end_index + 1。
3. 闭区间映射：start_index 和 end_index 都是闭区间（包含自身）。
4. 凝练总结：为每个 Beat 提炼一句 summary（15字以内）。

请输出严格的 JSON 格式：
{{
  "beats": [
    {{ "beat_id": "beat_1", "summary": "...", "start_index": 0, "end_index": 5 }},
    ...
  ]
}}"""

    client = get_client()
    try:
        t0 = time.perf_counter()
        response = client.chat.completions.create(
            model=MODEL_LLM,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"需要切分的行号文本：\n\n{text_payload}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.2
        )
        log_event(
            PHASE_AUDIO_BEATS,
            "beat_chunk_from_srt",
            "llm_chat",
            ok=True,
            duration_ms=(time.perf_counter() - t0) * 1000,
            model=MODEL_LLM,
            extra={"cue_lines": len(srt_data)},
        )
        result = json.loads(response.choices[0].message.content)
        beats_plan = result.get("beats", [])
        n_cues = len(srt_data)
        merged = _merge_overlapping_beat_ranges(beats_plan, n_cues)
        repaired = _repair_beat_ranges_full_coverage(merged, n_cues)
        if len(repaired) > MAX_BEATS_PHASE2:
            print(
                f"  ⚠️ [Beat] 修复后共 {len(repaired)} 个 Beat，超过上限 {MAX_BEATS_PHASE2}，"
                f"将合并最短的相邻节拍以控制 Phase 3 调用量。"
            )
            repaired = _cap_beat_ranges(repaired, MAX_BEATS_PHASE2)

        pseudo_srt = []
        for bi, r in enumerate(repaired):
            s_idx = int(r["s"])
            e_idx = int(r["e"])
            cues = srt_data[s_idx : e_idx + 1]
            beat_text = "".join(c["text"] for c in cues)
            beat_id = f"beat_{bi + 1}"
            pseudo_srt.append(
                {
                    "beat_id": beat_id,
                    "summary": r.get("summary", "情节推进"),
                    "start_time": cues[0]["start_time"],
                    "end_time": cues[-1]["end_time"],
                    "text": beat_text,
                    "cues": cues,
                }
            )

        print(f"  ✅ [LLM] Beat 拆解完毕，共切分为 {len(pseudo_srt)} 个节拍！（已修复行号覆盖空洞并重编号 beat_1…）")
        return pseudo_srt
    except Exception as e:
        try:
            log_event(
                PHASE_AUDIO_BEATS,
                "beat_chunk_from_srt",
                "llm_chat",
                ok=False,
                duration_ms=(time.perf_counter() - t0) * 1000,
                model=MODEL_LLM,
                error=str(e),
            )
        except Exception:
            pass
        print(f"❌ [LLM] Beat 划分失败: {e}")
        sys.exit(1)


# ==============================================================================
#  [Phase 3] 视觉重构与绝对时间戳插值算法
# ==============================================================================

def calculate_trigger_time(char_index: int, beat_cues: list) -> float:
    """核心算法：基于相对字符位置，在线性物理时间轴上进行插值"""
    current_len = 0
    for cue in beat_cues:
        cue_text = cue["text"]
        cue_len = len(cue_text)
        if cue_len == 0:
            continue
            
        # 判断当前字落在哪一个 cue 区间内
        if current_len <= char_index < current_len + cue_len:
            offset = char_index - current_len
            percentage = offset / cue_len
            t_trigger = cue["start_time"] + (cue["end_time"] - cue["start_time"]) * percentage
            return round(t_trigger, 3)
            
        current_len += cue_len
        
    # 防止下标越界溢出
    if beat_cues:
        return beat_cues[-1]["end_time"]
    return 0.0

def _extract_segments_from_tagged_text(tagged_text: str) -> list:
    """
    从带 <subshot> 标签的文本中提取有序分镜片段。
    标签作为分镜边界，不保留在最终文本里。
    """
    if not tagged_text:
        return []
    # 不能 strip：必须保留原始字符边界，避免破坏插值游标精度。
    # 仅过滤纯空白片段，内容本身保持原样。
    parts = tagged_text.split("<subshot>")
    return [p for p in parts if p and p.strip()]

def _pick_stage_anchor(stage: str, physical_anchors: dict) -> str:
    """按阶段优先匹配定妆照路径，匹配不到时回退到可用锚点。"""
    if not isinstance(physical_anchors, dict) or not physical_anchors:
        return ""
    if stage in physical_anchors and physical_anchors.get(stage):
        return str(physical_anchors.get(stage))
    for fallback in ("middle", "youth", "child", "elderly"):
        if physical_anchors.get(fallback):
            return str(physical_anchors.get(fallback))
    first = next(iter(physical_anchors.values()), "")
    return str(first) if first else ""

def _resolve_subshot_stage(subshot_id: int, stage_map: list) -> str:
    """根据 stage_map 的 shot 区间，为当前 subshot 选择人生阶段。"""
    if not isinstance(stage_map, list):
        return "middle"
    for item in stage_map:
        try:
            start = int(item.get("start_shot"))
            end = int(item.get("end_shot"))
            if start <= subshot_id <= end:
                return str(item.get("stage") or "middle")
        except Exception:
            continue
    return "middle"


def _infer_stage_from_visual_prompt(v_prompt: str) -> str | None:
    """
    从 visual_prompt 文案中解析人生阶段（与 LLM 输出的 youth version / elderly version 等对齐）。
    当 stage_map 使用虚构 shot 区间（如 1~333 全为 youth）时，以此覆盖，保证 anchor_look 与画面一致。
    """
    if not v_prompt:
        return None
    p = v_prompt.lower()
    if "elderly version" in p or "older/boss version" in p:
        return "elderly"
    if "youth version" in p or "young/poor version" in p:
        return "youth"
    if "child version" in p:
        return "child"
    if "middle version" in p or "mature/successful version" in p:
        return "middle"
    return None


def _estimate_min_subshots_for_text(text: str) -> int:
    text_len = len((text or "").strip())
    if text_len <= 30:
        return 2
    if text_len <= 60:
        return 3
    if text_len <= 100:
        return 4
    return 5


# 单镜文案过长时，时间轴上会出现「一图钉很久」；机械拆分时每段目标上限（汉字）
MAX_CHARS_PER_SUBSHOT_MECHANICAL = 96


def _merge_overlapping_beat_ranges(beats_plan: list, n_cues: int) -> list[dict]:
    """排序、钳制下标、合并重叠区间。"""
    rows: list[dict] = []
    for b in beats_plan or []:
        try:
            s = int(b.get("start_index", 0))
            e = int(b.get("end_index", 0))
        except (TypeError, ValueError):
            continue
        s = max(0, min(s, n_cues - 1))
        e = max(0, min(e, n_cues - 1))
        if e < s:
            s, e = e, s
        rows.append(
            {
                "s": s,
                "e": e,
                "summary": str(b.get("summary") or "情节推进").strip()[:80] or "情节推进",
            }
        )
    if not rows:
        return []
    rows.sort(key=lambda x: x["s"])
    merged: list[dict] = []
    for r in rows:
        if not merged:
            merged.append(dict(r))
            continue
        last = merged[-1]
        if r["s"] <= last["e"]:
            last["e"] = max(last["e"], r["e"])
            if len(r["summary"]) > len(last["summary"]):
                last["summary"] = r["summary"]
        else:
            merged.append(dict(r))
    return merged


def _repair_beat_ranges_full_coverage(ranges: list[dict], n_cues: int) -> list[dict]:
    """
    将 Beat 行区间连成 [0, n_cues-1] 无间隙：填补 LLM 漏掉的行号（避免出现「整段 beat 从叙事里消失」）。
    """
    if n_cues <= 0:
        return []
    if not ranges:
        return [{"s": 0, "e": n_cues - 1, "summary": "全篇叙事"}]
    out: list[dict] = []
    expect = 0
    for r in ranges:
        s, e = int(r["s"]), int(r["e"])
        if s > expect:
            s = expect
        e = max(e, s)
        if out and s <= out[-1]["e"]:
            out[-1]["e"] = max(out[-1]["e"], e)
            if len(r.get("summary", "")) > len(out[-1].get("summary", "")):
                out[-1]["summary"] = r["summary"]
        else:
            out.append({"s": s, "e": e, "summary": r.get("summary", "情节推进")})
        expect = out[-1]["e"] + 1
    if out[-1]["e"] < n_cues - 1:
        out[-1]["e"] = n_cues - 1
    return out


def _cap_beat_ranges(ranges: list[dict], max_beats: int) -> list[dict]:
    """
    当修复后的 Beat 数超过上限时，反复合并「相邻 pair 中 cue 跨度最短」的一对，
    直至数量 <= max_beats，保持 [0, n_cues-1] 完整覆盖且区间连续。
    """
    if max_beats <= 0 or len(ranges) <= max_beats:
        return ranges
    out: list[dict] = [dict(r) for r in ranges]
    while len(out) > max_beats:
        best_i = 0
        best_span = None
        for i in range(len(out) - 1):
            a, b = out[i], out[i + 1]
            span = (a["e"] - a["s"] + 1) + (b["e"] - b["s"] + 1)
            if best_span is None or span < best_span:
                best_span = span
                best_i = i
        a, b = out[best_i], out[best_i + 1]
        merged_summary = f"{a.get('summary', '')}；{b.get('summary', '')}".strip("；")[:80] or "情节推进"
        merged = {"s": int(a["s"]), "e": int(b["e"]), "summary": merged_summary}
        out[best_i : best_i + 2] = [merged]
    return out


def _enforce_subshot_segment_density(
    beat_text: str,
    text_segments: list[str],
    visual_prompts: list[str],
) -> tuple[list[str], list[str]]:
    """
    在 LLM 已返回的 subshot 基础上：
    1) 校验拼接与 beat 原文一致；
    2) 单段超过 MAX_CHARS_PER_SUBSHOT_MECHANICAL 时在句读处再切；
    3) 若总镜数仍低于字数下限要求，继续拆分最长段直至达标。
    """
    joined = "".join(text_segments)
    if joined != beat_text:
        print(
            f"  [Vision] 分镜拼接与 Beat 原文不一致（{len(joined)} vs {len(beat_text)} 字），跳过机械加镜。"
        )
        return text_segments, visual_prompts

    min_need = _estimate_min_subshots_for_text(beat_text)
    segs = list(text_segments)
    prompts = list(visual_prompts)

    def split_long_at_boundary(long: str, prompt: str) -> tuple[list[str], list[str]]:
        if len(long) <= MAX_CHARS_PER_SUBSHOT_MECHANICAL:
            return [long], [prompt]
        cut_hi = min(len(long), MAX_CHARS_PER_SUBSHOT_MECHANICAL + 24)
        best = -1
        for sep in ("。", "！", "？", "；", "，", "\n"):
            p = long.rfind(sep, 0, cut_hi)
            if p > MAX_CHARS_PER_SUBSHOT_MECHANICAL // 4:
                best = max(best, p)
        if best < 0:
            best = MAX_CHARS_PER_SUBSHOT_MECHANICAL - 1
        a, b = long[: best + 1], long[best + 1 :]
        if not b.strip():
            return [long], [prompt]
        cont = f"{prompt} (same scene, continued beat — slight angle or emphasis shift)"
        return [a, b], [prompt, cont]

    def split_for_min_density(long: str, prompt: str) -> tuple[list[str], list[str]]:
        """单段已不长但仍需加镜时：在句读或中点附近再切一刀。"""
        if len(long) < 8:
            return [long], [prompt]
        cut_hi = min(len(long), max(16, len(long) // 2) + 12)
        best = -1
        for sep in ("。", "！", "？", "；", "，", "、", "\n"):
            p = long.rfind(sep, 1, cut_hi)
            if p > 0:
                best = max(best, p)
        if best < 0:
            best = max(0, len(long) // 2 - 1)
        a, b = long[: best + 1], long[best + 1 :]
        if not b.strip():
            return [long], [prompt]
        cont = f"{prompt} (same scene, continued — slight angle or emphasis shift)"
        return [a, b], [prompt, cont]

    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(segs):
            if len(segs[i]) <= MAX_CHARS_PER_SUBSHOT_MECHANICAL:
                i += 1
                continue
            parts, ps = split_long_at_boundary(segs[i], prompts[i])
            if len(parts) == 1:
                i += 1
                continue
            segs[i : i + 1] = parts
            prompts[i : i + 1] = ps
            changed = True

    while len(segs) < min_need and segs:
        longest_i = max(range(len(segs)), key=lambda k: len(segs[k]))
        if len(segs[longest_i]) < 8:
            break
        long_s, pr = segs[longest_i], prompts[longest_i]
        parts, ps = (
            split_long_at_boundary(long_s, pr)
            if len(long_s) > MAX_CHARS_PER_SUBSHOT_MECHANICAL
            else split_for_min_density(long_s, pr)
        )
        if len(parts) == 1:
            break
        segs[longest_i : longest_i + 1] = parts
        prompts[longest_i : longest_i + 1] = ps

    if "".join(segs) != beat_text:
        return text_segments, visual_prompts
    if len(segs) != len(prompts):
        return text_segments, visual_prompts
    extra = len(segs) - len(text_segments)
    if extra > 0:
        print(
            f"  [Vision] 机械补镜 +{extra}（单镜过长或密度不足），缓解「一图钉过久」。"
        )
    return segs, prompts


def _is_stage_map_too_coarse(stage_map: list, beats: list = None) -> bool:
    if not isinstance(stage_map, list) or not stage_map:
        return True
    if len(stage_map) == 1:
        item = stage_map[0] if isinstance(stage_map[0], dict) else {}
        return int(item.get("start_shot", 0) or 0) <= 1 and int(item.get("end_shot", 0) or 0) >= 999

    # 多阶段 map，但首阶段区间过宽：所有实际镜头可能都落在第一阶段
    # 用 beats 文本预估算出总镜数下限，若首阶段 end_shot 超过预估总量 2 倍则判为过粗
    if beats:
        estimated_total = sum(
            _estimate_min_subshots_for_text((b.get("text", "") or ""))
            for b in beats
        )
        first_stage = stage_map[0] if isinstance(stage_map[0], dict) else {}
        first_end = int(first_stage.get("end_shot", 0) or 999999)
        if first_end >= estimated_total * 2:
            return True

    return False


def _auto_stage_map_by_llm(beats: list, detected_stages: list[str]) -> list:
    allowed = [s for s in (detected_stages or []) if s in {"child", "youth", "middle", "elderly"}]
    if not allowed:
        allowed = ["middle"]

    beat_briefs = []
    for b in beats:
        beat_briefs.append(
            {
                "beat_id": b.get("beat_id"),
                "summary": b.get("summary", ""),
                "text_preview": (b.get("text", "") or "")[:220],
            }
        )

    client = get_client()
    system_prompt = """你是“人生阶段时间线规划器”。
任务：按剧情推进，为每个 beat 分配主角阶段（child/youth/middle/elderly），然后输出连续的 shot 区间 stage_map。

规则：
1. 只能使用 allowed_stages 中的阶段。
2. 整体必须符合时间推进，不要反复来回跳阶段。
3. 输出 stage_map 必须连续、无重叠：下一个 start_shot = 上一个 end_shot + 1。
4. start_shot 从 1 开始，最后一个 end_shot 固定写 999999（兜底覆盖）。
5. 若某阶段在剧情中未出现，可不写入。

输出 JSON：
{
  "stage_map": [
    {"stage":"child","start_shot":1,"end_shot":8},
    {"stage":"middle","start_shot":9,"end_shot":999999}
  ]
}"""
    user_prompt = json.dumps(
        {
            "allowed_stages": allowed,
            "beats": beat_briefs,
        },
        ensure_ascii=False,
    )
    t_map = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=MODEL_WRITER,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        log_event(
            PHASE_STORYBOARD,
            "auto_stage_map",
            "llm_chat",
            ok=True,
            duration_ms=(time.perf_counter() - t_map) * 1000,
            model=MODEL_WRITER,
            extra={"beats": len(beats)},
        )
        data = json.loads(resp.choices[0].message.content)
        stage_map = data.get("stage_map", [])
        if not isinstance(stage_map, list) or not stage_map:
            raise ValueError("empty stage_map")
        norm = []
        prev_end = 0
        for item in stage_map:
            st = str(item.get("stage") or "").strip()
            if st not in allowed:
                continue
            start = int(item.get("start_shot", prev_end + 1))
            end = int(item.get("end_shot", start))
            if start != prev_end + 1:
                start = prev_end + 1
            if end < start:
                end = start
            norm.append({"stage": st, "start_shot": start, "end_shot": end})
            prev_end = end
        if not norm:
            raise ValueError("normalized stage_map empty")
        norm[-1]["end_shot"] = 999999
        return norm
    except Exception as e:
        log_event(
            PHASE_STORYBOARD,
            "auto_stage_map",
            "llm_chat",
            ok=False,
            duration_ms=(time.perf_counter() - t_map) * 1000,
            model=MODEL_WRITER,
            error=str(e),
        )
        print(f"  ⚠️ [StageMap] 自动生成失败，回退默认分段: {e}")
        if len(allowed) == 1:
            return [{"stage": allowed[0], "start_shot": 1, "end_shot": 999999}]
        # 多阶段时做简单均分回退，避免再次出现全程 middle
        total_proj = max(1, sum(_estimate_min_subshots_for_text((b.get('text', '') or '')) for b in beats))
        chunk = max(1, total_proj // len(allowed))
        fallback = []
        start = 1
        for idx, st in enumerate(allowed):
            if idx == len(allowed) - 1:
                end = 999999
            else:
                end = start + chunk - 1
            fallback.append({"stage": st, "start_shot": start, "end_shot": end})
            start = end + 1
        return fallback

# ==============================================================================
#  [Phase 3] 解耦 LLM 调用：第一次打标签 / 第二次生成提示词
# ==============================================================================

def _tag_subshots_only(beat: dict, attempt: int = 0) -> list[str]:
    """
    【第一次 LLM 调用】
    只在 beat 原文中插入 <subshot> 标签，返回切分好的 text_segments 列表。
    校验：拼接结果必须与 beat["text"] 字符完全一致。
    任何失败均返回空列表，由调用方（generate_visual_subshots）决定是否重试。
    """
    beat_text = beat["text"]
    beat_summary = beat.get("summary", "")

    system_prompt = """你是一个"高密度分镜切分器"。
任务：在给定的剧情节拍原文中，仅插入 <subshot> 标签来标记分镜切换点。

【钢铁纪律】：
1. 除插入 <subshot> 标签外，原文内容绝对不能改写、不能丢字、不能调换语序。
2. 核心目标是"切得更碎，不要保守"：允许并鼓励句内切分，不要只在句号处切。
3. 长句强制拆分：单句 >24 字至少切 2 段；单句 >40 字至少切 3 段。
4. 以下信号优先切镜：动作阶段变化、视角切换（人/物、远/近、外/内）、情绪或权力转折（但/却/忽然/随后/最终）、时间推进（片刻后/几天后/多年后）。
5. 分镜密度下限（按 beat 总字数）：<=30 字至少 2 镜；31~60 至少 3 镜；61~100 至少 4 镜；>100 至少 5 镜。
6. 输出前自检：去掉所有 <subshot> 后，剩余文字必须与输入原文逐字一致。

输出严格 JSON 格式（只需 tagged_text 一个字段）：
{
  "tagged_text": "原文第一段<subshot>原文第二段<subshot>原文第三段"
}"""

    client = get_client()
    try:
        t_tag = time.perf_counter()
        response = client.chat.completions.create(
            model=MODEL_WRITER,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Beat 概括（仅供参考，不影响原文）: {beat_summary}\n"
                        f"需要打分镜标签的原文：\n{beat_text}"
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        log_event(
            PHASE_STORYBOARD,
            f"phase3_tag_subshots/{beat.get('beat_id', '?')}",
            "llm_chat",
            ok=True,
            duration_ms=(time.perf_counter() - t_tag) * 1000,
            model=MODEL_WRITER,
            attempt=max(1, int(attempt or 1)),
            extra={"phase": "tag"},
        )
        choice = response.choices[0] if response.choices else None
        msg = choice.message if choice else None
        raw = (msg.content if msg else "") or ""
        result = _extract_json_object(raw)
        if result is None:
            finish_reason = getattr(choice, "finish_reason", None)
            refusal = getattr(msg, "refusal", None) if msg else None
            _dump_phase3_llm_raw(
                stage="tagging",
                beat_id=str(beat.get("beat_id", "unknown")),
                attempt=max(1, int(attempt or 1)),
                raw=raw,
                meta=f"finish_reason={finish_reason}\nrefusal={refusal}",
            )
            print("    ⚠️ [Tagging] LLM 返回非 JSON，已写入 logs/phase3_tagging_* 诊断文件。")
            return []
        tagged_text = (result.get("tagged_text") or "").strip()
        segments = _extract_segments_from_tagged_text(tagged_text)

        if not segments:
            print(f"    ⚠️ [Tagging] tagged_text 解析后为空列表。")
            return []

        joined = "".join(segments)
        if joined != beat_text:
            print(
                f"    ⚠️ [Tagging] 拼接不一致：期望 {len(beat_text)} 字，"
                f"实际 {len(joined)} 字，差异 {abs(len(joined) - len(beat_text))} 字。"
            )
            return []

        return segments
    except Exception as e:
        log_event(
            PHASE_STORYBOARD,
            f"phase3_tag_subshots/{beat.get('beat_id', '?')}",
            "llm_chat",
            ok=False,
            duration_ms=(time.perf_counter() - t_tag) * 1000,
            model=MODEL_WRITER,
            attempt=max(1, int(attempt or 1)),
            error=str(e),
            extra={"phase": "tag"},
        )
        print(f"    ⚠️ [Tagging] 调用异常: {e}")
        return []


def _ref_keys_to_paths(keys: list, physical_anchors: dict) -> list:
    paths: list[str] = []
    for k in keys or []:
        p = (physical_anchors or {}).get(k)
        if p:
            s = str(p).strip()
            if s and s not in paths:
                paths.append(s)
    return paths


def _normalize_per_shot_ref_keys(
    per_shot_raw: list,
    n: int,
    segments_with_meta: list,
    physical_anchors: dict,
) -> list:
    allowed = set(physical_anchors.keys())
    out: list[list[str]] = []
    for i in range(n):
        stage = (segments_with_meta[i].get("stage") if i < len(segments_with_meta) else None) or "middle"
        if stage not in allowed:
            stage = next((s for s in ("middle", "youth", "child", "elderly") if s in allowed), None)
            if stage is None:
                stage = next(iter(sorted(allowed)), "middle")
        raw_row = per_shot_raw[i] if i < len(per_shot_raw) and isinstance(per_shot_raw[i], list) else []
        row: list[str] = []
        for x in raw_row:
            xs = str(x).strip()
            if xs in allowed and xs not in row:
                row.append(xs)
        if stage in allowed and stage not in row:
            row.insert(0, stage)
        if not row:
            row = [stage] if stage in allowed else []
        out.append(row)
    return out


def _generate_visual_prompts(
    text_segments: list[str],
    beat: dict,
    attempt: int,
    prev_beat_summary: str,
    text_anchors: dict,
    physical_anchors: dict,
    stage_map: list,
    beat_start_subshot_id: int,
    era_raw: str | None = None,
    cast_registry: dict | None = None,
) -> tuple[list[str], list[list[str]]]:
    """
    【第二次 LLM 调用】
    针对已定稿的 text_segments，逐条生成英文 visual_prompts 与 per_shot_ref_keys。
    失败返回 ([], [])。
    """
    beat_summary = beat.get("summary", "")
    n = len(text_segments)

    segments_with_meta = []
    for i, seg in enumerate(text_segments):
        sid = beat_start_subshot_id + i
        stage = _resolve_subshot_stage(sid, stage_map)
        segments_with_meta.append(
            {
                "index": i + 1,
                "subshot_id": f"S_{sid:03d}",
                "stage": stage,
                "text": seg,
            }
        )

    prev_ctx = prev_beat_summary or "（开篇，无前情）"
    era_section = build_writer_era_section(era_raw)
    text_anchors_str = json.dumps(text_anchors, ensure_ascii=False, indent=2)
    physical_anchors_str = json.dumps(physical_anchors, ensure_ascii=False, indent=2)
    cast_registry = cast_registry or {}
    cast_blob = json.dumps(cast_registry, ensure_ascii=False, indent=2) if cast_registry else "{}"
    legal_keys = sorted((physical_anchors or {}).keys())
    key_help = ", ".join(legal_keys) if legal_keys else "(无)"

    system_prompt = (
        "你是一位 AI 分镜导演兼英文 prompt 写手。任务：为已切好的每条分镜文案生成一条英文 visual_prompt（用于生图），"
        "并输出 per_shot_ref_keys。\n\n"
        "【叙事与场记】\n"
        f"- 上一章节（前情摘要）：{prev_ctx}\n"
        f"- 当前章节概括：{beat_summary}\n"
        "同一条目列表内须强连贯：环境与光影方向应自然延续；禁止无交代的人物瞬移、场景跳切、光源突变。"
        "若叙事明确转场，在同一条英文 visual_prompt 中用一两句写清转场依据。\n\n"
        f"{era_section}"
        "【强制画风（须写入每条 visual_prompt 的英文正文，可嵌在叙事句中）】\n"
        "Cyanide and Happiness comic style, 2D vector / flat graphic cartoon, bold black outlines, vivid flat color fills, "
        "pure 2D, no photoreal skin texture, no 3D/CGI. 允许卡通级光向（key direction, warm/cool, simple hard-edge shadow shapes），"
        "禁止电影级体积光与写实 subsurface skin。\n"
        "主角人生阶段必须与输入 JSON 每条 segment 的 stage 一致。\n\n"
        "【角色外观语义锚点】\n"
        f"{text_anchors_str}\n\n"
        "【物理定妆锚点路径】（逻辑键 → 磁盘路径）\n"
        f"{physical_anchors_str}\n\n"
        "【已定案角色注册表 cast_registry】\n"
        "已注册角色必须用 display_name_en 点名，禁止 young man / old man / elderly stranger 等泛指。\n"
        f"{cast_blob}\n\n"
        "【每条 visual_prompt 的形式与内容】\n"
        "每条必须是**一段连续英文**（不要用 Subject:/Environment: 等小标题分行），用 3–6 个完整句子自然串联，但必须**隐含覆盖**以下维度（不必按固定顺序）：\n"
        "主体（谁/何物）；具体环境（须与前情连贯）；构图与景别；客观画面事件；光影连贯；\n"
        "★ 动态表情与肢体（核心要求：打破参考图的呆滞感！）：必须深度解析当前分镜的故事情节，强制赋予角色强烈且符合情境的情绪反应。\n"
        "1. 必须采用【核心情绪词 + 氰化物式五官拆解】组合。例如不要只写 mouth line，必须写：terrified expression, sharply angled frowning eyebrows, wide dilated dot eyes, screaming jagged mouth shape.\n"
        "2. 明确指令：绝不允许角色保持中立或被参考图的默认表情带偏（DO NOT copy the neutral expression from reference）。\n"
        "3. 肢体辅助：情绪必须配合夸张的肢体动作（如 recoiling in horror, pointing aggressively, slumping in defeat）。\n"
        "4. 脸部特写：当情绪是当前帧重点时，明确写明 close-up on explicit facial expression。\n\n"
        "【数量与输出】\n"
        f"1. visual_prompt 恰好 {n} 条，顺序与输入 segments 一致。\n"
        f"2. per_shot_ref_keys：与 visual_prompts 等长；每行为字符串数组，键必须从：{key_help} 选取。"
        "主角键与当条 stage 一致；配角用 supporting_<role_id>；仅锁脸时列入。\n\n"
        f'输出严格 JSON：{{"visual_prompts": [ ... 共 {n} 条 ... ], "per_shot_ref_keys": [ ... 共 {n} 行 ... ]}}'
    )

    client = get_client()
    try:
        t_vis = time.perf_counter()
        response = client.chat.completions.create(
            model=MODEL_WRITER,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"请为以下 {n} 个分镜段落逐条生成 visual_prompt 与 per_shot_ref_keys：\n\n"
                        + json.dumps(segments_with_meta, ensure_ascii=False, indent=2)
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.5,
        )
        log_event(
            PHASE_STORYBOARD,
            f"phase3_visual_prompts/{beat.get('beat_id', '?')}",
            "llm_chat",
            ok=True,
            duration_ms=(time.perf_counter() - t_vis) * 1000,
            model=MODEL_WRITER,
            attempt=max(1, int(attempt or 1)),
            extra={"n_segments": n, "phase": "prompts"},
        )
        choice = response.choices[0] if response.choices else None
        msg = choice.message if choice else None
        raw = (msg.content if msg else "") or ""
        result = _extract_json_object(raw)
        if result is None:
            finish_reason = getattr(choice, "finish_reason", None)
            refusal = getattr(msg, "refusal", None) if msg else None
            _dump_phase3_llm_raw(
                stage="prompts",
                beat_id=str(beat.get("beat_id", "unknown")),
                attempt=max(1, int(attempt or 1)),
                raw=raw,
                meta=f"finish_reason={finish_reason}\nrefusal={refusal}",
            )
            print("    ⚠️ [Prompts] LLM 返回非 JSON，已写入 logs/phase3_prompts_* 诊断文件。")
            return [], []
        prompts = result.get("visual_prompts", [])

        if not isinstance(prompts, list) or len(prompts) != n:
            print(
                f"    ⚠️ [Prompts] 返回数量不符：期望 {n}，"
                f"实际 {len(prompts) if isinstance(prompts, list) else '非列表'}。"
            )
            return [], []

        per_raw = result.get("per_shot_ref_keys")
        if not isinstance(per_raw, list):
            per_raw = []
        normalized_rows = _normalize_per_shot_ref_keys(per_raw, n, segments_with_meta, physical_anchors)
        return [str(p).strip() for p in prompts], normalized_rows
    except Exception as e:
        log_event(
            PHASE_STORYBOARD,
            f"phase3_visual_prompts/{beat.get('beat_id', '?')}",
            "llm_chat",
            ok=False,
            duration_ms=(time.perf_counter() - t_vis) * 1000,
            model=MODEL_WRITER,
            attempt=max(1, int(attempt or 1)),
            error=str(e),
            extra={"phase": "prompts"},
        )
        print(f"    ⚠️ [Prompts] 调用异常: {e}")
        return [], []


def _phase3_resolve_segments(
    beat: dict,
    text_anchors: dict,
    physical_anchors: dict,
    max_retries: int = MAX_VISION_LLM_RETRIES,
) -> list[str]:
    """
    Phase 3 第一波：仅打 <subshot> 标签 + 密度校验，产出最终 text_segments。
    （用于并行编排：先并行求各 Beat 镜数，再算全局 S_ 起始编号。）
    """
    beat_id = beat.get("beat_id", "unknown")
    beat_text = beat["text"]
    beat_summary = (beat.get("summary") or "").strip()
    beat_time = f"{beat.get('start_time', '?')}s ~ {beat.get('end_time', '?')}s"

    if not beat_summary:
        raise ValueError(
            f"Beat {beat_id} 缺少 summary，拒绝继续生成 visual_prompt。"
        )
    if not text_anchors and not physical_anchors:
        raise ValueError(
            "缺少角色锚点（text_anchors/physical_anchors 均为空），拒绝继续生成 visual_prompt。"
        )

    print(f"  🎬 [Vision] [{beat_id}] 分段标签: {beat_summary} ({beat_time})")

    last_fail_tag = ""

    for attempt in range(1, max_retries + 1):
        suffix = "继续重试" if attempt < max_retries else "已达上限，准备报错"
        print(f"    🔁 [{beat_id}] [segment try {attempt}/{max_retries}]")

        text_segments = _tag_subshots_only(beat, attempt=attempt)
        if not text_segments:
            last_fail_tag = f"第 {attempt} 次：_tag_subshots_only 返回空列表"
            print(f"    ❌ [{beat_id}] [Tagging] 第 {attempt} 次失败，{suffix}。")
            continue

        placeholder = ["__placeholder__"] * len(text_segments)
        enforced_segs, _ = _enforce_subshot_segment_density(
            beat_text, text_segments, placeholder
        )
        if "".join(enforced_segs) != beat_text:
            last_fail_tag = f"第 {attempt} 次：enforce 后拼接仍不一致"
            print(f"    ❌ [{beat_id}] [Enforce] 第 {attempt} 次失败，{suffix}。")
            continue

        return enforced_segs

    raise Phase3BeatError(
        beat_id=beat_id,
        stage="tagging",
        detail=last_fail_tag or f"连续 {max_retries} 次分段失败（无详细原因记录）",
        beat_time_range=beat_time,
    )


def _phase3_prompts_and_pack(
    beat: dict,
    text_segments: list[str],
    beat_start_subshot_id: int,
    prev_beat_summary: str,
    text_anchors: dict,
    physical_anchors: dict,
    stage_map: list,
    era_raw: str | None,
    cast_registry: dict | None,
    max_retries: int = MAX_VISION_LLM_RETRIES,
) -> list:
    """
    Phase 3 第二波：对已锁定的 text_segments 生成 visual_prompt，并组装 trigger_time 等。
    提示词阶段单独重试（分段已在第一波定稿）。
    """
    beat_id = beat.get("beat_id", "unknown")
    beat_time = f"{beat.get('start_time', '?')}s ~ {beat.get('end_time', '?')}s"
    last_fail_prompt = ""

    for attempt in range(1, max_retries + 1):
        suffix = "继续重试" if attempt < max_retries else "已达上限，准备报错"
        print(f"    🔁 [{beat_id}] [prompt try {attempt}/{max_retries}]")

        visual_prompts, per_shot_ref_keys = _generate_visual_prompts(
            text_segments=text_segments,
            beat=beat,
            attempt=attempt,
            prev_beat_summary=prev_beat_summary,
            text_anchors=text_anchors,
            physical_anchors=physical_anchors,
            stage_map=stage_map,
            beat_start_subshot_id=beat_start_subshot_id,
            era_raw=era_raw,
            cast_registry=cast_registry,
        )
        if not visual_prompts or len(visual_prompts) != len(text_segments):
            last_fail_prompt = (
                f"第 {attempt} 次：_generate_visual_prompts 返回 "
                f"{len(visual_prompts) if isinstance(visual_prompts, list) else '非列表'}，"
                f"期望 {len(text_segments)}"
            )
            print(f"    ❌ [{beat_id}] [Prompts] 第 {attempt} 次失败，{suffix}。")
            continue

        current_char_idx = 0
        subshots_with_time = []
        for i, t_segment in enumerate(text_segments):
            v_prompt = visual_prompts[i]
            subshot_id_num = beat_start_subshot_id + i
            stage_from_prompt = _infer_stage_from_visual_prompt(v_prompt)
            protagonist_stage = stage_from_prompt or _resolve_subshot_stage(subshot_id_num, stage_map)
            anchor_look = _pick_stage_anchor(protagonist_stage, physical_anchors)
            rk = per_shot_ref_keys[i] if i < len(per_shot_ref_keys) else []
            ref_image_paths = _ref_keys_to_paths(rk, physical_anchors)
            if not ref_image_paths and anchor_look:
                ref_image_paths = [str(anchor_look).strip()]
            t_trigger = calculate_trigger_time(current_char_idx, beat["cues"])
            subshots_with_time.append(
                {
                    "text_segment": t_segment,
                    "trigger_time": t_trigger,
                    "visual_prompt": v_prompt,
                    "protagonist_stage": protagonist_stage,
                    "anchor_look": anchor_look,
                    "ref_keys": rk,
                    "ref_image_paths": ref_image_paths,
                }
            )
            current_char_idx += len(t_segment)

        print(f"    ✅ [Vision] [{beat_id}] 完成，共 {len(subshots_with_time)} 个分镜。")
        return subshots_with_time

    raise Phase3BeatError(
        beat_id=beat_id,
        stage="prompts",
        detail=last_fail_prompt or f"连续 {max_retries} 次提示词失败（无详细原因记录）",
        beat_time_range=beat_time,
    )


def generate_visual_subshots(
    beat: dict,
    prev_beat_summary: str,
    text_anchors: dict,
    physical_anchors: dict,
    stage_map: list,
    beat_start_subshot_id: int,
    max_retries: int = MAX_VISION_LLM_RETRIES,
    era_raw: str | None = None,
    cast_registry: dict | None = None,
) -> list:
    """
    Phase 3 串行封装：先分段再生成提示词（供单测或其它调用方使用）。
    主流程 phase3 使用两波并行编排以缩短墙钟时间。
    """
    segments = _phase3_resolve_segments(
        beat, text_anchors, physical_anchors, max_retries=max_retries
    )
    return _phase3_prompts_and_pack(
        beat,
        segments,
        beat_start_subshot_id,
        prev_beat_summary,
        text_anchors,
        physical_anchors,
        stage_map,
        era_raw,
        cast_registry,
        max_retries=max_retries,
    )


# ==============================================================================
#  总控流
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="工业级电影叙事总线 - 时间轴锚定与分镜拆解")
    parser.add_argument("--phase", type=str, choices=["phase2", "phase3"], default="phase2", help="执行阶段")
    args = parser.parse_args()
    
    if args.phase == "phase2":
        print("\n=======================================================")
        print("🎬 [Phase 2] 绝对时钟底座与行号锚定 (生成 pseudo_srt.json)")
        print("=======================================================")
        
        if not FULL_STORY_V6_PATH.exists():
            print(f"❌ 找不到长文案 {FULL_STORY_V6_PATH}，请先执行阶段一。")
            sys.exit(1)
            
        story_data = json.loads(FULL_STORY_V6_PATH.read_text(encoding="utf-8"))
        narration = story_data.get("master_design", {}).get("full_narration", "")
        
        if not narration:
            print("❌ narration 为空，无法生成音频。")
            sys.exit(1)
            
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        master_audio_path = AUDIO_DIR / "master_voice.mp3"
        
        srt_data = generate_master_audio_and_srt(narration, master_audio_path)
        pseudo_srt_list = chunk_beats_by_llm(srt_data)
        
        output_data = {
            "metadata": story_data.get("metadata", {}),
            "pseudo_srt": pseudo_srt_list
        }
        
        PSEUDO_SRT_PATH.write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")
        vault_backup(PSEUDO_SRT_PATH, f"scripts/{PSEUDO_SRT_PATH.name}")
        
        print(f"\n🏆 阶段二完美落幕！产物: {PSEUDO_SRT_PATH}")
        
    elif args.phase == "phase3":
        print("\n=======================================================")
        print("🚀 [Phase 3] 插值定位与视觉 Prompt (生成 narrative_v6_final.json)")
        print("=======================================================")
        
        if not PSEUDO_SRT_PATH.exists() or not FULL_STORY_V6_PATH.exists():
            print("❌ 找不到前置数据，请确保已顺次执行 Phase 1 和 Phase 2。")
            sys.exit(1)
            
        pseudo_data = json.loads(PSEUDO_SRT_PATH.read_text(encoding="utf-8"))
        story_data = json.loads(FULL_STORY_V6_PATH.read_text(encoding="utf-8"))
        
        beats = pseudo_data.get("pseudo_srt", [])
        master_design = story_data.get("master_design", {})
        from_refs = _phase3_text_anchors_from_refs_prompt(REFS_PROMPT_PATH)
        if from_refs:
            text_anchors = from_refs
            print("  📎 [Phase3] 角色语义锚点：scripts/refs-prompt.json")
        elif master_design.get("character_anchors"):
            text_anchors = master_design.get("character_anchors") or {}
            print("  📎 [Phase3] 角色语义锚点：full_story.character_anchors（旧版兼容）")
        else:
            text_anchors = {}
        physical_anchors = master_design.get("physical_char_anchors", {})
        stage_map = master_design.get("stage_map", [])
        detected_stages = master_design.get("detected_life_stages", [])
        era_raw = (story_data.get("metadata") or {}).get("era") or (
            (pseudo_data.get("metadata") or {}).get("era")
        )

        if _is_stage_map_too_coarse(stage_map, beats):
            print("  ⚠️ [StageMap] 检测到阶段区间过粗，正在自动重建 stage_map...")
            stage_map = _auto_stage_map_by_llm(beats, detected_stages)
            master_design["stage_map"] = stage_map
            try:
                FULL_STORY_V6_PATH.write_text(json.dumps(story_data, ensure_ascii=False, indent=2), encoding="utf-8")
                vault_backup(FULL_STORY_V6_PATH, f"scripts/{FULL_STORY_V6_PATH.name}")
                print(f"  ✅ [StageMap] 已重建并回写: {stage_map}")
            except Exception as e:
                print(f"  ⚠️ [StageMap] 回写失败（仅本次运行生效）: {e}")

        cast_registry = master_design.get("cast_registry") or {}

        if not text_anchors and not physical_anchors:
            print(
                "❌ [Phase3] 未检测到任何角色锚点：scripts/refs-prompt.json（或旧版 master_design.character_anchors）"
                " 与 physical_char_anchors 均为空。"
            )
            print("   请先完成定妆流水线并成功回写 physical_char_anchors。")
            sys.exit(1)

        workers = _phase3_pool_workers(len(beats))
        print(
            f"  ⚙️ [Phase3] Beat 并行度: {workers} "
            f"（环境变量 PHASE3_MAX_WORKERS，默认 {PHASE3_MAX_WORKERS_DEFAULT}；设为 1 即串行）"
        )

        try:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                segment_lists = list(
                    ex.map(
                        lambda b: _phase3_resolve_segments(
                            b, text_anchors, physical_anchors, MAX_VISION_LLM_RETRIES
                        ),
                        beats,
                    )
                )

            beat_starts: list[int] = []
            cur_id = 1
            for bi in range(len(beats)):
                beat_starts.append(cur_id)
                cur_id += len(segment_lists[bi])

            def _wave2_one(i: int) -> list:
                beat = beats[i]
                prev_summary = beats[i - 1].get("summary", "") if i > 0 else ""
                return _phase3_prompts_and_pack(
                    beat,
                    segment_lists[i],
                    beat_starts[i],
                    prev_summary,
                    text_anchors,
                    physical_anchors,
                    stage_map,
                    era_raw,
                    cast_registry,
                    MAX_VISION_LLM_RETRIES,
                )

            with ThreadPoolExecutor(max_workers=workers) as ex:
                packed_lists = list(ex.map(_wave2_one, range(len(beats))))
        except Phase3BeatError as e:
            print(f"\n{'=' * 60}")
            print(f"❌ [Phase 3 FATAL] Beat 分镜生成失败，已中止 Phase 3。")
            print(f"   Beat ID   : {e.beat_id}")
            print(f"   时间范围  : {e.beat_time_range}")
            print(f"   失败阶段  : {e.stage}")
            print(f"   失败详情  : {e.detail}")
            print(f"   说明      : narrative_v6_final.json 未写盘（两波并行中任一 Beat 失败即中止）")
            print(f"{'=' * 60}")
            sys.exit(1)
        except ValueError as e:
            print(f"❌ [Phase3] 输入验收失败: {e}")
            sys.exit(1)

        final_narrative = []
        global_subshot_id = 1
        for i, beat in enumerate(beats):
            for s in packed_lists[i]:
                final_narrative.append(
                    {
                        "subshot_id": f"S_{global_subshot_id:03d}",
                        "beat_id": beat["beat_id"],
                        "trigger_time": s["trigger_time"],
                        "text_segment": s["text_segment"],
                        "visual_prompt": s["visual_prompt"],
                        "protagonist_stage": s.get("protagonist_stage", "middle"),
                        "anchor_look": s.get("anchor_look", ""),
                        "ref_keys": s.get("ref_keys", []),
                        "ref_image_paths": s.get("ref_image_paths", []),
                    }
                )
                global_subshot_id += 1

        output_data = {
            "metadata": pseudo_data.get("metadata", {}),
            "timeline": final_narrative
        }
        output_data["metadata"]["run_id"] = get_current_run_id()
        
        NARRATIVE_FINAL_PATH.write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")
        vault_backup(NARRATIVE_FINAL_PATH, f"scripts/{NARRATIVE_FINAL_PATH.name}")
        
        print(f"\n🏆 阶段三 (分镜插值与视觉蓝图) 成功完工！")
        print(f"📍 核心产物: {NARRATIVE_FINAL_PATH}")
        print(f"   共生成 {len(final_narrative)} 个毫秒级精准卡点分镜。")

if __name__ == "__main__":
    main()
