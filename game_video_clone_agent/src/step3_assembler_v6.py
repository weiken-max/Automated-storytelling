"""
🎬 绝对时钟组装台 (src/step3_assembler_v6.py)
完全舍弃按比例算时间的逻辑。直接吃 narrative_v6_final.json 里的 trigger_time，
用纯 ffmpeg 命令行完成低内存、严丝合缝的卡点组装。
"""
import json
import os
import sys
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# ── Windows GBK 终端编码修复 ──
if hasattr(sys.stdout, "buffer"):
    from io import TextIOWrapper
    sys.stdout = TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.api_audit import PHASE_ASSEMBLE, log_event
from src.run_context import get_paths, get_current_run_id
from src.style_config import FONT_PATH, SUBTITLE_SIZE, SUBTITLE_Y_FRAC
NARRATIVE_FINAL_PATH = None
STORYBOARDS_DIR = None
AUDIO_DIR = None
OUTPUT_DIR = None
LOGS_DIR = None
RUN_DIR = None
FPS = 24
FRAME_SIZE = "1280x720"
FRAME_W, FRAME_H = FRAME_SIZE.split("x")
# 首条 trigger 晚于 0 时，片头补镜；与音轨对齐容差（秒）
_HEAD_GAP_EPS = 0.05
_DURATION_ALIGN_EPS = 0.12
# Step3 主合成阶段保持 1.0，确保字幕与原始音轨严格对齐。
_DEFAULT_PLAYBACK_SPEED = 1.0
# 主合成完成后再做整片后置变速（默认 1.1x）。
_DEFAULT_POST_PLAYBACK_SPEED = 1.1
_SUBTITLE_TARGET_CHARS = 14
_SUBTITLE_MIN_SEG_SEC = 0.25
_SUBTITLE_SIZE_SCALE = 0.56
_SUBTITLE_MARGIN_V = 36
_SUBTITLE_TIME_EPS = 0.02


def _ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        return -1.0
    try:
        return float((proc.stdout or "0").strip() or "0")
    except ValueError:
        return -1.0


def _write_step3_progress(total: int, done: int) -> None:
    """逐段写入进度文件，供 Hub / 监控读取。"""
    if not LOGS_DIR:
        return
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        (LOGS_DIR / "step3_progress.json").write_text(
            json.dumps({"total": total, "done": done, "ts": time.time()}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def _clear_step3_progress() -> None:
    if not LOGS_DIR:
        return
    try:
        p = LOGS_DIR / "step3_progress.json"
        if p.exists():
            p.unlink(missing_ok=True)
    except Exception:
        pass


def _write_step3_error(msg: str) -> None:
    """失败时落盘错误摘要，供 Hub 读取后发飞书。"""
    if not LOGS_DIR:
        return
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        (LOGS_DIR / "step3_last_error.json").write_text(
            json.dumps({"error": msg[:3000], "ts": time.time()}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def _clear_step3_error() -> None:
    if not LOGS_DIR:
        return
    try:
        p = LOGS_DIR / "step3_last_error.json"
        if p.exists():
            p.unlink(missing_ok=True)
    except Exception:
        pass


def _require_ffmpeg():
    if not shutil.which("ffmpeg"):
        print("[ERROR] 系统中未检测到 ffmpeg。请先安装 ffmpeg 并加入 PATH。")
        sys.exit(1)


def _require_ffprobe():
    if not shutil.which("ffprobe"):
        print("[ERROR] 系统中未检测到 ffprobe。请先安装 ffmpeg 并加入 PATH。")
        sys.exit(1)


def setup_temp_env(output_dir: Path):
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    temp_dir = output_dir / f"tmp_segments_{run_id}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    concat_list_path = temp_dir / "concat.txt"
    silent_video_path = temp_dir / "silent_assembled.mp4"
    return temp_dir, concat_list_path, silent_video_path


def cleanup_temp_env(temp_dir: Path):
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"  [Cleanup] 已清理临时目录: {temp_dir}")


def _run_ffmpeg(cmd: list[str], stage: str):
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    ms = (time.perf_counter() - t0) * 1000
    ok = proc.returncode == 0
    try:
        log_event(
            PHASE_ASSEMBLE,
            stage,
            "ffmpeg_local",
            ok=ok,
            duration_ms=ms,
            extra={"returncode": proc.returncode, "argv0": cmd[0] if cmd else ""},
        )
    except Exception:
        pass
    if proc.returncode != 0:
        print(f"[ERROR] FFmpeg 执行失败: {stage}")
        print(f"[ERROR] 命令: {' '.join(cmd)}")
        detail = (proc.stderr or proc.stdout or "").strip()
        if detail:
            print(detail[-4000:])
        raise RuntimeError(f"{stage} 失败")


def _seconds_to_srt_timestamp(seconds: float) -> str:
    s = max(0.0, float(seconds))
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    ms = int(round((s - int(s)) * 1000))
    if ms >= 1000:
        ms -= 1000
        sec += 1
        if sec >= 60:
            sec = 0
            m += 1
            if m >= 60:
                m = 0
                h += 1
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def _write_temp_srt_from_master_json(master_srt_json_path: Path, out_srt_path: Path) -> None:
    """
    将 audio/master_srt.json（start_time/end_time/text）转换为标准 .srt。
    """
    if not master_srt_json_path.exists():
        raise FileNotFoundError(f"找不到字幕源文件: {master_srt_json_path}")
    payload = json.loads(master_srt_json_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"字幕源格式异常（期望 list）: {master_srt_json_path}")

    def _split_text_for_subtitles(text: str) -> list[str]:
        raw = (text or "").strip()
        if not raw:
            return []

        # 仅按标点断句：先句末标点，再次级停顿标点；不做按字数硬切，避免“代/理律师”被拆词。
        major_parts: list[str] = []
        start = 0
        for i, ch in enumerate(raw):
            if ch in "。！？；!?;":
                part = raw[start : i + 1].strip()
                if part:
                    major_parts.append(part)
                start = i + 1
        tail = raw[start:].strip()
        if tail:
            major_parts.append(tail)
        if not major_parts:
            major_parts = [raw]

        fine_parts: list[str] = []
        for part in major_parts:
            tmp = ""
            for ch in part:
                tmp += ch
                if ch in "，、,:：":
                    if len(tmp.strip()) >= 4:
                        fine_parts.append(tmp.strip())
                        tmp = ""
            if tmp.strip():
                fine_parts.append(tmp.strip())

        return [x for x in fine_parts if x]

    def _wrap_long_subtitle_line(text: str, max_chars: int = 22) -> str:
        """
        仅做显示换行，不改变时间轴与字幕条目数量。
        优先在中点附近的逗号类标点换行；找不到再在中点硬换行。
        """
        t = (text or "").strip()
        if len(t) <= max_chars:
            return t
        mid = len(t) // 2
        best = -1
        for i, ch in enumerate(t):
            if ch in "，、,:：":
                if best < 0 or abs(i - mid) < abs(best - mid):
                    best = i
        if best >= 0:
            return t[: best + 1].rstrip() + "\n" + t[best + 1 :].lstrip()
        return t[:mid].rstrip() + "\n" + t[mid:].lstrip()

    # 先做单调化修正，消除源字幕重叠，避免“前一句没说完就被下一句顶掉”。
    norm_rows: list[dict] = []
    prev_end = 0.0
    for row in payload:
        if not isinstance(row, dict):
            continue
        st = float(row.get("start_time", 0.0) or 0.0)
        et = float(row.get("end_time", st) or st)
        text = str(row.get("text", "") or "").strip()
        if not text:
            continue
        st = max(st, prev_end + _SUBTITLE_TIME_EPS)
        if et <= st:
            et = st + _SUBTITLE_MIN_SEG_SEC
        prev_end = et
        norm_rows.append({"start_time": st, "end_time": et, "text": text})

    lines: list[str] = []
    idx = 1
    for row in norm_rows:
        st = float(row["start_time"])
        et = float(row["end_time"])
        text = str(row["text"]).strip()

        chunks = _split_text_for_subtitles(text)
        if not chunks:
            continue

        # 断句后按字数权重分配时长，避免固定最小时长挤爆导致的“晚出现/提前消失”。
        total_span = max(_SUBTITLE_MIN_SEG_SEC, et - st)
        weights = [max(1, len(c.strip())) for c in chunks]
        weight_sum = max(1, sum(weights))
        dur_list = [total_span * (w / weight_sum) for w in weights]

        # 软下限：不足最小时长的段从“富余段”借时长，保证总时长不变。
        need = 0.0
        for i, d in enumerate(dur_list):
            if d < _SUBTITLE_MIN_SEG_SEC:
                need += (_SUBTITLE_MIN_SEG_SEC - d)
                dur_list[i] = _SUBTITLE_MIN_SEG_SEC
        if need > 1e-9:
            donors = [max(0.0, d - _SUBTITLE_MIN_SEG_SEC) for d in dur_list]
            donor_sum = sum(donors)
            if donor_sum > 1e-9:
                scale = min(1.0, need / donor_sum)
                for i in range(len(dur_list)):
                    if donors[i] > 0:
                        take = donors[i] * scale
                        dur_list[i] -= take
                        need -= take

        # 漂移修正：最后一段吃掉误差，确保总和严格等于原句时间窗。
        drift = total_span - sum(dur_list)
        dur_list[-1] = max(_SUBTITLE_MIN_SEG_SEC, dur_list[-1] + drift)

        cursor = st
        for i, chunk in enumerate(chunks):
            seg_st = cursor
            if i == len(chunks) - 1:
                seg_et = et
            else:
                seg_et = min(et, seg_st + dur_list[i])
            if seg_et <= seg_st:
                seg_et = seg_st + _SUBTITLE_MIN_SEG_SEC
            lines.append(str(idx))
            lines.append(f"{_seconds_to_srt_timestamp(seg_st)} --> {_seconds_to_srt_timestamp(seg_et)}")
            wrapped = _wrap_long_subtitle_line(chunk)
            lines.append(wrapped.replace("\r\n", "\n").replace("\r", "\n"))
            lines.append("")
            idx += 1
            cursor = seg_et

    if idx == 1:
        raise ValueError("master_srt.json 中没有可用字幕条目。")
    out_srt_path.write_text("\n".join(lines), encoding="utf-8")


def _escape_path_for_ffmpeg_subtitles(path: Path) -> str:
    """
    Windows 路径转义给 subtitles 滤镜：
    - 统一 / 分隔符
    - 盘符冒号转义（C\\:/...）
    - 转义单引号，避免破坏滤镜参数字符串
    """
    p = str(path.resolve()).replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        p = p[0] + "\\:" + p[2:]
    p = p.replace("'", "\\'")
    return p


def _build_subtitle_force_style() -> str:
    # 字号缩小到更接近剪映“小字”观感，并固定更贴底的 MarginV。
    font_size = max(16, int(round(float(SUBTITLE_SIZE) * _SUBTITLE_SIZE_SCALE)))
    margin_v = max(20, int(_SUBTITLE_MARGIN_V))
    # FONT_PATH 作为字体资产配置锚点；滤镜中字体名按需求固定为 Microsoft YaHei
    _ = FONT_PATH
    _ = SUBTITLE_Y_FRAC
    return (
        f"Fontname=Microsoft YaHei,"
        f"Fontsize={font_size},"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "BorderStyle=1,"
        "Outline=2,"
        "Shadow=0,"
        "Alignment=2,"
        f"MarginV={margin_v}"
    )


def _timeline_to_segments(timeline: list, total_audio_duration: float):
    """
    构建与主音轨等长的无声片段列表。
    若首条 trigger_time > 0：在片头插入一段「0 → 首卡」时长，画面用 S_001（与首镜一致），
    避免画面总长 = 音长 − 首卡偏移 导致 -shortest 吃掉尾部旁白。
    """
    segments: list[tuple[str, Path, float]] = []
    num_shots = len(timeline)
    if num_shots == 0:
        return segments

    first_t = float(timeline[0].get("trigger_time") or 0.0)
    head_gap = max(0.0, first_t)
    if head_gap > _HEAD_GAP_EPS:
        head_img = STORYBOARDS_DIR / "S_001.png"
        segments.append(("head", head_img, head_gap))
        print(f"  [Timeline] 片头补镜 {head_gap:.3f}s（对齐 0s→首条 trigger），画面 {head_img.name}")

    for i in range(num_shots):
        shot_data = timeline[i]
        start_t = float(shot_data["trigger_time"])
        if i < num_shots - 1:
            end_t = float(timeline[i + 1]["trigger_time"])
        else:
            end_t = float(total_audio_duration)

        duration = end_t - start_t
        if duration <= 0:
            duration = 0.1

        img_filename = f"S_{i+1:03d}.png"
        img_path = STORYBOARDS_DIR / img_filename
        segments.append((f"S_{i+1:03d}", img_path, duration))

    total_v = sum(s[2] for s in segments)
    drift = float(total_audio_duration) - total_v
    if abs(drift) > _DURATION_ALIGN_EPS and segments:
        label, path, dur = segments[-1]
        segments[-1] = (label, path, max(0.05, dur + drift))
        print(f"  [Timeline] 末段时长修正 {drift:+.3f}s，使无声轨总长与主音轨一致")

    total_v2 = sum(s[2] for s in segments)
    if abs(total_v2 - float(total_audio_duration)) > _DURATION_ALIGN_EPS:
        print(
            f"  [WARN] 无声轨总长 {total_v2:.3f}s 与主音轨 {total_audio_duration:.3f}s "
            f"仍相差 {abs(total_v2 - float(total_audio_duration)):.3f}s，成片可能仍有偏差。"
        )
    return segments


def generate_silent_clips_via_ffmpeg(segments: list, temp_dir: Path):
    clip_paths = []
    total_segs = len(segments)
    print("  [Video] 正在逐镜头生成无声片段...")

    for clip_i, (_label, img_path, duration) in enumerate(segments, start=1):
        clip_path = temp_dir / f"seg_{clip_i:04d}.mp4"

        if img_path.exists():
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-framerate", str(FPS),
                "-t", f"{duration:.6f}",
                "-i", str(img_path),
                "-vf", f"scale={FRAME_W}:{FRAME_H}:force_original_aspect_ratio=decrease,pad={FRAME_W}:{FRAME_H}:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p",
                "-r", str(FPS),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "veryfast",
                "-an",
                str(clip_path),
            ]
        else:
            print(f"  [WARN] 找不到画面文件 {img_path.name}，使用黑帧占位保持时间槽位。")
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c=black:s={FRAME_SIZE}:r={FPS}",
                "-t", f"{duration:.6f}",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "veryfast",
                "-an",
                str(clip_path),
            ]

        _run_ffmpeg(cmd, f"生成片段 seg_{clip_i:04d}")
        clip_paths.append(clip_path)

        # 每 10 段写一次进度文件，最后一段必写
        if clip_i % 10 == 0 or clip_i == total_segs:
            _write_step3_progress(total_segs, clip_i)

    return clip_paths


def _escape_for_concat(path: Path):
    normalized = path.resolve().as_posix()
    return normalized.replace("'", "'\\''")


def create_concat_list(clip_paths: list[Path], concat_list_path: Path):
    lines = [f"file '{_escape_for_concat(p)}'" for p in clip_paths]
    concat_content = "\n".join(lines) + "\n"
    concat_list_path.write_text(concat_content, encoding="utf-8")
    print("  [Concat] concat.txt 已生成，内容如下：")
    print(concat_content)


def assemble_final_video_ffmpeg(
    concat_list_path: Path,
    silent_video_path: Path,
    master_audio_path: Path,
    out_file: Path,
    expected_audio_duration: float,
    subtitle_srt_path: Path | None = None,
):
    print("  [Assemble] 正在无损拼接无声长视频...")
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list_path),
        "-c", "copy",
        str(silent_video_path),
    ]
    _run_ffmpeg(cmd_concat, "拼接无声长视频")

    v_dur = _ffprobe_duration(silent_video_path)
    if v_dur > 0 and abs(v_dur - expected_audio_duration) > _DURATION_ALIGN_EPS:
        print(
            f"  [WARN] 无声成片 {v_dur:.3f}s 与主音轨 {expected_audio_duration:.3f}s 相差 "
            f"{abs(v_dur - expected_audio_duration):.3f}s"
        )

    speed = float(os.getenv("STEP3_PLAYBACK_SPEED", str(_DEFAULT_PLAYBACK_SPEED)))
    if speed <= 0:
        speed = _DEFAULT_PLAYBACK_SPEED

    print(f"  [Render] 正在混音输出最终成片: {out_file.name} (请稍候...)")
    subtitle_filter = ""
    if subtitle_srt_path:
        escaped_sub_path = _escape_path_for_ffmpeg_subtitles(subtitle_srt_path)
        style = _build_subtitle_force_style()
        subtitle_filter = f"subtitles='{escaped_sub_path}':force_style='{style}'"

    if abs(speed - 1.0) < 1e-6:
        # 原速：有字幕则走 -vf 烧录（需重编码视频）；无字幕保持 copy 提速。
        cmd_mux = [
            "ffmpeg", "-y",
            "-i", str(silent_video_path),
            "-i", str(master_audio_path),
            "-t", f"{expected_audio_duration:.6f}",
        ]
        if subtitle_filter:
            cmd_mux.extend([
                "-vf", subtitle_filter,
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-pix_fmt", "yuv420p",
            ])
        else:
            cmd_mux.extend(["-c:v", "copy"])
        cmd_mux.extend(["-c:a", "aac", str(out_file)])
        _run_ffmpeg(cmd_mux, "混音导出最终成片")
    else:
        # 音画同比变速（如 1.1×）：setpts + atempo；若有字幕，拼入同一个 filter_complex。
        inv = 1.0 / speed
        if subtitle_filter:
            fc = (
                f"[0:v]{subtitle_filter},setpts=PTS*{inv}[v];"
                f"[1:a]atempo={speed}[a]"
            )
        else:
            fc = (
                f"[0:v]setpts=PTS*{inv}[v];"
                f"[1:a]atempo={speed}[a]"
            )
        print(f"  [Speed] 成片播放速率 ×{speed:.3f}（STEP3_PLAYBACK_SPEED）")
        cmd_mux = [
            "ffmpeg", "-y",
            "-i", str(silent_video_path),
            "-i", str(master_audio_path),
            "-filter_complex", fc,
            "-map", "[v]",
            "-map", "[a]",
            "-shortest",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(out_file),
        ]
        _run_ffmpeg(cmd_mux, "变速混音导出最终成片")


def _apply_post_playback_speed(out_file: Path, speed: float) -> None:
    """
    在主合成完成后做整片后置变速，避免影响前序字幕轴分配逻辑。
    """
    if speed <= 0 or abs(speed - 1.0) < 1e-6:
        return
    inv = 1.0 / speed
    tmp_out = out_file.with_name(f"{out_file.stem}.speedtmp{out_file.suffix}")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(out_file),
        "-filter_complex", f"[0:v]setpts=PTS*{inv}[v];[0:a]atempo={speed}[a]",
        "-map", "[v]",
        "-map", "[a]",
        "-shortest",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(tmp_out),
    ]
    print(f"  [PostSpeed] 主合成完成，开始后置变速 ×{speed:.3f}...")
    _run_ffmpeg(cmd, "后置整片变速")
    os.replace(tmp_out, out_file)
    print(f"  [PostSpeed] 后置变速完成：{out_file.name}")

def main():
    global NARRATIVE_FINAL_PATH, STORYBOARDS_DIR, AUDIO_DIR, OUTPUT_DIR, LOGS_DIR, RUN_DIR
    paths = get_paths(create_if_missing=False)
    if not paths:
        print("[ERROR] 未检测到当前 Run-ID。请先执行 story_planner/step1 初始化运行批次。")
        sys.exit(1)
    NARRATIVE_FINAL_PATH = paths["scripts_dir"] / "narrative_v6_final.json"
    STORYBOARDS_DIR = paths["storyboards_dir"]
    AUDIO_DIR = paths["audio_dir"]
    OUTPUT_DIR = paths["output_dir"]
    LOGS_DIR = paths["logs_dir"]
    RUN_DIR = paths["run_dir"]

    print("\n=======================================================")
    print("[Phase 4-B] 绝对时间轴视频装配台")
    print(f"[Run] 当前批次: {get_current_run_id()}")
    print("=======================================================")
    _require_ffmpeg()
    _require_ffprobe()

    if not NARRATIVE_FINAL_PATH.exists():
        err = "找不到 narrative_v6_final.json"
        print(f"[ERROR] {err}")
        _write_step3_error(err)
        sys.exit(1)

    master_audio_path = AUDIO_DIR / "master_voice.mp3"
    if not master_audio_path.exists():
        err = "找不到主音轨 master_voice.mp3"
        print(f"[ERROR] {err}")
        _write_step3_error(err)
        sys.exit(1)

    data = json.loads(NARRATIVE_FINAL_PATH.read_text(encoding="utf-8"))
    timeline = data.get("timeline", [])

    if not timeline:
        err = "时间轴 timeline 为空"
        print(f"[ERROR] {err}")
        _write_step3_error(err)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUTPUT_DIR / "narrative_v6_final_epic.mp4"

    # 清除上次遗留的错误和进度文件
    _clear_step3_error()
    _write_step3_progress(0, 0)

    temp_dir, concat_list_path, silent_video_path = setup_temp_env(OUTPUT_DIR)
    temp_subs_srt_path = RUN_DIR / "temp_subs.srt"
    try:
        master_srt_json_path = AUDIO_DIR / "master_srt.json"
        _write_temp_srt_from_master_json(master_srt_json_path, temp_subs_srt_path)
        print(f"  [Subtitle] 已生成临时字幕文件: {temp_subs_srt_path}")

        print("  [Audio] 正在读取主音轨长度...")
        probe_cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(master_audio_path),
        ]
        probe = subprocess.run(probe_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if probe.returncode != 0:
            err = f"无法读取主音轨时长，ffprobe 返回非零。\n{(probe.stderr or '')[-500:]}"
            print(f"[ERROR] {err}")
            _write_step3_error(err)
            sys.exit(1)
        total_audio_duration = float((probe.stdout or "0").strip() or "0")
        if total_audio_duration <= 0:
            err = "主音轨时长异常（<=0），终止合成。"
            print(f"[ERROR] {err}")
            _write_step3_error(err)
            sys.exit(1)

        segments = _timeline_to_segments(timeline, total_audio_duration)
        if not segments:
            err = "没有有效视频片段，装配失败。"
            print(f"[ERROR] {err}")
            _write_step3_error(err)
            sys.exit(1)

        clip_paths = generate_silent_clips_via_ffmpeg(segments, temp_dir)
        create_concat_list(clip_paths, concat_list_path)
        assemble_final_video_ffmpeg(
            concat_list_path,
            silent_video_path,
            master_audio_path,
            out_file,
            total_audio_duration,
            subtitle_srt_path=temp_subs_srt_path,
        )
        post_speed = float(
            os.getenv("STEP3_POST_PLAYBACK_SPEED", str(_DEFAULT_POST_PLAYBACK_SPEED))
        )
        _apply_post_playback_speed(out_file, post_speed)
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        print(f"[ERROR] Step3 异常终止: {err_msg}")
        _write_step3_error(err_msg)
        raise
    finally:
        try:
            if temp_subs_srt_path.exists():
                temp_subs_srt_path.unlink(missing_ok=True)
                print(f"  [Cleanup] 已清理临时字幕: {temp_subs_srt_path}")
        except Exception as sub_clean_err:
            print(f"  [WARN] 清理临时字幕失败: {sub_clean_err}")
        cleanup_temp_env(temp_dir)
        _clear_step3_progress()

    _clear_step3_error()
    print("\n[SUCCESS] 管线重构圆满结束！")
    print(f"  [OK] 完美卡点成片已输出至: {out_file.resolve()}")

if __name__ == "__main__":
    main()
