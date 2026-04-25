import json
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

# ── 路径配置（必须在 from src.xxx 之前） ──
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# ── Windows GBK 终端编码修复 ──
if hasattr(sys.stdout, "buffer"):
    from io import TextIOWrapper
    sys.stdout = TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, VideoFileClip, ColorClip
from src.project_vault import backup as vault_backup  # 🔒 导入金库备份接口
DATA_DIR = BASE_DIR / "data"
STORYBOARD_DIR = DATA_DIR / "storyboards"
AUDIO_DIR = DATA_DIR / "audio"
OUTPUT_DIR = DATA_DIR / "output"
CACHE_DIR = OUTPUT_DIR / "atomic_cache"

# ── 超参数 ──
OUTPUT_FPS = 24
FINAL_NAME = "narrative_v6_final_epic.mp4"

def ensure_dirs():
    for d in [OUTPUT_DIR, CACHE_DIR]:
        if not d.exists(): d.mkdir(parents=True)

def render_atomic_shot(sid, img_file, audio_file, out_file):
    """
    [原子化渲染逻辑]：只渲染一个由于物理镜头，确保内存零溢出。
    """
    print(f"🎬 [Atomic Render] Rendering Shot {sid}...")
    try:
        audio_clip = AudioFileClip(str(audio_file))
        # 🛡️ 强制把任何 AI 画出来的图压入 1280x720，否则 ffmpeg 后期 -c copy 会直接崩溃或花屏！
        img_clip = ImageClip(str(img_file)).resize(newsize=(1280, 720)).set_duration(audio_clip.duration)
        img_clip = img_clip.set_audio(audio_clip)
        
        # 极低负载压制：libx264 + ultrafast
        img_clip.write_videofile(
            str(out_file), 
            codec="libx264", 
            preset="ultrafast", 
            fps=OUTPUT_FPS, 
            logger=None,
            threads=4
        )
        # 释放内存
        audio_clip.close()
        img_clip.close()
        return True
    except Exception as e:
        print(f"  ⚠️ Shot {sid} 渲染物理失败: {e}")
        return False

def estimate_silent_duration(narration: str, min_seconds: float = 2.0) -> float:
    """
    根据旁白字数估算应有的镜头时长（剥除 [CUT_XXXX] 标签后按 ~5 字/秒折算）。
    用于：当真实 TTS 音频缺失时，生成等长静音占位以保全总时长不缩水。
    """
    if not narration:
        return min_seconds
    text = re.sub(r"\[CUT_\d+\]", "", narration).strip()
    if not text:
        return min_seconds
    return max(min_seconds, len(text) / 5.0)


def generate_silent_mp3(out_path: Path, duration: float) -> bool:
    """
    使用 ffmpeg 生成指定时长的静音 mp3（采样率 44100 / 双声道 / libmp3lame），
    与 Step2 的 Edge TTS 输出格式保持一致，确保后续 -c copy 合拢不报错。
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", f"{duration:.3f}",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ⚠️ 静音 mp3 生成失败: {result.stderr[:300]}")
        return False
    return out_path.exists() and out_path.stat().st_size > 0


def render_atomic_shot_fallback(sid, audio_file, out_file):
    """
    [原子化渲染：黑场保全模式]：如果图像缺失，采用黑屏进行物理占位以保全世界时间轴。
    """
    print(f"🎬 [Atomic Render] Rendering Shot {sid} with Blank Fallback...")
    try:
        audio_clip = AudioFileClip(str(audio_file))
        img_clip = ColorClip(size=(1280, 720), color=(0,0,0)).set_duration(audio_clip.duration)
        img_clip = img_clip.set_audio(audio_clip)
        
        img_clip.write_videofile(
            str(out_file), 
            codec="libx264", 
            preset="ultrafast", 
            fps=OUTPUT_FPS, 
            logger=None,
            threads=4
        )
        audio_clip.close()
        img_clip.close()
        return True
    except Exception as e:
        print(f"  ⚠️ Shot {sid} 黑场占位渲染物理失败: {e}")
        return False

def main():
    ensure_dirs()
    json_path = DATA_DIR / "scripts/narrative_v6.json"
    
    if not json_path.exists():
        raise RuntimeError(f"Step3 前置缺失：导演剧本不存在 -> {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 汇集所有章节中的分镜进行无缝全量合拢
    chapters = data.get('director_chapters', [])
    if not chapters:
        raise RuntimeError("Step3 输入异常：director_chapters 为空，无法合成视频")

    all_shots = []
    for chap in chapters:
        all_shots.extend(chap.get('shots', []))
    shot_mp4s = []
    
    print(f"🚀 [V12.1 Atomic Engine] 开始总线装配，共 {len(all_shots)} 镜...")

    for i, s in enumerate(all_shots):
        sid = s['shot_id']
        id_str = f"{int(sid):04d}"
        img_file = STORYBOARD_DIR / f"{id_str}.png"
        audio_file = AUDIO_DIR / f"shot_{id_str}.mp3"
        out_file = CACHE_DIR / f"atomic_{i:04d}.mp4" # 保持严格时序
        
        if out_file.exists() and out_file.stat().st_size > 10000:
            print(f"  ⏩ Shot {sid} 已同步物理跳过 (Cache Hit)")
            shot_mp4s.append(str(out_file))
            continue

        # 🔇 音频缺失保全：不再静默跳过；改为按旁白字数估算时长生成静音占位，
        #    避免 Step2 偶发 TTS 失败导致最终视频整段缩水。
        effective_audio = audio_file
        if not audio_file.exists():
            est_duration = estimate_silent_duration(s.get("narration", ""))
            silent_audio = CACHE_DIR / f"silent_{id_str}.mp3"
            print(
                f"  ⚠️ Shot {sid} 音频缺失，启用静音占位 ({est_duration:.1f}s) 以保全时间轴。"
            )
            if not generate_silent_mp3(silent_audio, est_duration):
                print(f"  ❌ Shot {sid} 静音占位生成失败，本镜放弃（请重跑 Step2 补齐音频）。")
                continue
            effective_audio = silent_audio

        if not img_file.exists():
            print(f"  ⚠️ Shot {sid} 连带图像缺失，强制启用黑场占位帧以保全时间同步！")
            success = render_atomic_shot_fallback(sid, effective_audio, out_file)
        else:
            success = render_atomic_shot(sid, img_file, effective_audio, out_file)

        if success:
            shot_mp4s.append(str(out_file))

    # 🔗 FFmpeg 链式物理合拢
    if not shot_mp4s:
        raise RuntimeError("Step3 输入异常：没有可合拢的分镜片段")

    list_path = CACHE_DIR / "filelist.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for m in shot_mp4s:
            p = str(m).replace("\\", "/")
            f.write(f"file '{p}'\n")
    
    final_out = OUTPUT_DIR / FINAL_NAME
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", 
        "-i", str(list_path), "-c", "copy", str(final_out)
    ]
    
    print(f"\n🔗 [Final Link] 正在执行全量由于物理由于由于无损合位...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"\n🏆 [GREAT SUCCESS] 电影已成功出炉: {final_out}")
        # 🔒 物理金库合拢：即便 data/ 区域被刷干净，金库里永远有这一份
        vault_backup(final_out, f"output/{final_out.name}")
        print(f"📂 缓存由于已物理由于由于由于保留在 atomic_cache 文件夹下，以备后续由于修正。")
    else:
        print(f"\n❌ [CRITICAL] FFmpeg 合拢失败。")
        if result.stderr:
            print(f"[FFMPEG STDERR]\n{result.stderr.strip()}")
        if result.stdout:
            print(f"[FFMPEG STDOUT]\n{result.stdout.strip()}")
        raise RuntimeError("FFmpeg concat failed")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n🚨 [STEP3 FATAL] 未捕获异常: {e}")
        print(traceback.format_exc())
        raise
