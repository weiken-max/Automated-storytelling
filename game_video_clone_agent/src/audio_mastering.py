import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict
from src.pipeline_errors import PipelineStageError


def _run_checked(cmd: List[str], stage: str, task_id: str):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip()[-500:]
        raise PipelineStageError(
            task_id=task_id,
            stage="DSP",
            error_code="DSP_FFMPEG_FAILED",
            error_message=f"{stage} 执行失败: {tail}",
        )
    return result


def _probe_duration_seconds(audio_path: Path, task_id: str) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    result = _run_checked(cmd, stage=f"ffprobe({audio_path.name})", task_id=task_id)
    try:
        return float((result.stdout or "").strip())
    except ValueError as exc:
        raise PipelineStageError(
            task_id=task_id,
            stage="DSP",
            error_code="DSP_DURATION_PARSE_FAILED",
            error_message=f"无法解析音频时长: {audio_path}",
        ) from exc


def _trim_clip(
    input_path: Path,
    output_path: Path,
    trim_threshold_db: float,
    min_silence_sec: float,
    task_id: str,
):
    # 先正向去前导静音，再反向去尾部静音，避免句首句尾断裂冗余。
    af = (
        f"silenceremove=start_periods=1:start_duration={min_silence_sec}:start_threshold={trim_threshold_db}dB,"
        f"areverse,"
        f"silenceremove=start_periods=1:start_duration={min_silence_sec}:start_threshold={trim_threshold_db}dB,"
        f"areverse"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-af",
        af,
        "-ar",
        "44100",
        "-ac",
        "2",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "192k",
        str(output_path),
    ]
    _run_checked(cmd, stage=f"trim({input_path.name})", task_id=task_id)


def _crossfade_chain(input_paths: List[Path], output_path: Path, crossfade_sec: float, task_id: str):
    if len(input_paths) == 1:
        shutil.copyfile(input_paths[0], output_path)
        return

    cmd = ["ffmpeg", "-y"]
    for p in input_paths:
        cmd.extend(["-i", str(p)])

    filter_parts = []
    for idx in range(len(input_paths)):
        filter_parts.append(f"[{idx}:a]asetpts=PTS-STARTPTS[a{idx}]")

    current = "a0"
    for idx in range(1, len(input_paths)):
        out_label = f"xf{idx}"
        filter_parts.append(
            f"[{current}][a{idx}]acrossfade=d={crossfade_sec}:c1=tri:c2=tri[{out_label}]"
        )
        current = out_label

    filter_complex = ";".join(filter_parts)
    cmd.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            f"[{current}]",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "192k",
            str(output_path),
        ]
    )
    _run_checked(cmd, stage="crossfade", task_id=task_id)


def _normalize_loudness(input_path: Path, output_path: Path, target_lufs: float, task_id: str):
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-af",
        f"loudnorm=I={target_lufs}:LRA=11:TP=-1.5",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "192k",
        str(output_path),
    ]
    _run_checked(cmd, stage="loudness_normalize", task_id=task_id)


def _collect_ordered_shots(narrative_data: dict) -> List[dict]:
    shots: List[dict] = []
    for chapter in narrative_data.get("director_chapters", []):
        shots.extend(chapter.get("shots", []))
    shots.sort(key=lambda x: int(x.get("shot_id", 0)))
    return shots


def _collect_narratable_units(shots: List[dict]) -> List[dict]:
    """
    收集需要参与主音轨拼接的语音单元。
    多 subshot/beat 时，仅首 subshot（有 narration 文本）参与音频链路。
    """
    units = []
    for s in shots:
        txt = (s.get("narration") or "").strip()
        if not txt:
            continue
        units.append(s)
    units.sort(key=lambda x: int(x.get("shot_id", 0)))
    return units


def build_master_voice_and_timeline(
    narrative_data: dict,
    audio_dir: Path,
    master_voice_path: Path,
    timeline_path: Path,
    trim_threshold_db: float,
    min_silence_sec: float,
    crossfade_sec: float,
    target_lufs: float,
    task_id: str = "step2_dsp",
) -> Dict[str, object]:
    shots = _collect_ordered_shots(narrative_data)
    if not shots:
        raise PipelineStageError(
            task_id=task_id,
            stage="DSP",
            error_code="DSP_EMPTY_INPUT",
            error_message="DSP 输入为空：没有可用 shot。",
        )

    narr_units = _collect_narratable_units(shots)
    if not narr_units:
        raise PipelineStageError(
            task_id=task_id,
            stage="DSP",
            error_code="DSP_EMPTY_NARRATION",
            error_message="DSP 输入异常：没有可配音的 narration 单元。",
        )

    missing = []
    ordered_audio_paths: List[Path] = []
    ordered_units: List[dict] = []
    for shot in narr_units:
        sid = int(shot.get("shot_id", 0))
        p = audio_dir / f"shot_{sid:04d}.mp3"
        if not p.exists() or p.stat().st_size <= 0:
            beat_id = (shot.get("beat_id") or f"B{sid:03d}").strip()
            subshot_id = (shot.get("subshot_id") or f"{beat_id}_S01").strip()
            missing.append(
                {
                    "shot_id": f"{sid:04d}",
                    "beat_id": beat_id,
                    "subshot_id": subshot_id,
                }
            )
        else:
            ordered_audio_paths.append(p)
            ordered_units.append(shot)

    if missing:
        preview = ", ".join(
            f"{m['shot_id']}({m['subshot_id']})" for m in missing[:10]
        )
        suffix = "..." if len(missing) > 10 else ""
        first = missing[0]
        raise PipelineStageError(
            task_id=task_id,
            stage="DSP",
            beat_id=first["beat_id"],
            subshot_id=first["subshot_id"],
            error_code="DSP_INPUT_MISSING",
            error_message=f"以下 shot 音频不存在或为空 -> {preview}{suffix}",
        )

    tmp_dir = audio_dir / "_master_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        trimmed_paths: List[Path] = []
        trimmed_durations: List[float] = []
        for idx, src_path in enumerate(ordered_audio_paths):
            trimmed = tmp_dir / f"trim_{idx:04d}.mp3"
            _trim_clip(
                src_path,
                trimmed,
                trim_threshold_db=trim_threshold_db,
                min_silence_sec=min_silence_sec,
                task_id=task_id,
            )
            duration = max(0.0, _probe_duration_seconds(trimmed, task_id=task_id))
            trimmed_paths.append(trimmed)
            trimmed_durations.append(duration)

        merged_path = tmp_dir / "merged_crossfade.mp3"
        _crossfade_chain(trimmed_paths, merged_path, crossfade_sec=crossfade_sec, task_id=task_id)

        master_voice_path.parent.mkdir(parents=True, exist_ok=True)
        _normalize_loudness(merged_path, master_voice_path, target_lufs=target_lufs, task_id=task_id)

        # 时间线按 trim 后时长 + crossfade 重叠推导，与主音轨拼接规则一致。
        lines = []
        cursor = 0.0
        overlap = max(0.0, crossfade_sec)
        for idx, (shot, dur) in enumerate(zip(ordered_units, trimmed_durations), start=1):
            start_sec = max(0.0, cursor)
            end_sec = max(start_sec, start_sec + dur)
            beat_id = (shot.get("beat_id") or f"B{int(shot.get('shot_id', 0)):03d}").strip()
            lines.append(
                {
                    "line_index": idx,
                    "shot_id": f"{int(shot.get('shot_id', 0)):04d}",
                    "beat_id": beat_id,
                    "start_sec": round(start_sec, 3),
                    "end_sec": round(end_sec, 3),
                    "trimmed_duration_sec": round(dur, 3),
                    "text": (shot.get("narration") or "").strip(),
                }
            )
            cursor = end_sec - overlap
            if cursor < 0:
                cursor = 0.0

        timeline = {
            "master_voice": str(master_voice_path).replace("\\", "/"),
            "dsp": {
                "trim_threshold_db": trim_threshold_db,
                "min_silence_sec": min_silence_sec,
                "crossfade_sec": crossfade_sec,
                "target_lufs": target_lufs,
            },
            "line_count": len(lines),
            "total_duration_sec": round(_probe_duration_seconds(master_voice_path, task_id=task_id), 3),
            "lines": lines,
        }

        timeline_path.parent.mkdir(parents=True, exist_ok=True)
        with open(timeline_path, "w", encoding="utf-8") as f:
            json.dump(timeline, f, ensure_ascii=False, indent=2)

        return {
            "master_voice_path": str(master_voice_path),
            "timeline_path": str(timeline_path),
            "line_count": len(lines),
            "total_duration_sec": timeline["total_duration_sec"],
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)