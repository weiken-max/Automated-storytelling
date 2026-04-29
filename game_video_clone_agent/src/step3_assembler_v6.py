"""
🎬 绝对时钟组装台 (src/step3_assembler_v6.py)
完全舍弃按比例算时间的逻辑。直接吃 narrative_v6_final.json 里的 trigger_time，
用 moviepy 完成极速、严丝合缝的卡点组装。
"""
import json
import sys
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
DATA_DIR = BASE_DIR / "data"

try:
    from moviepy.editor import ImageClip, AudioFileClip, ColorClip, concatenate_videoclips
except ImportError:
    print("[ERROR] 缺少 moviepy，请在终端执行: pip install moviepy==1.0.3")
    sys.exit(1)

from src.style_config import SCRIPT_DIR
NARRATIVE_FINAL_PATH = SCRIPT_DIR / "narrative_v6_final.json"
STORYBOARDS_DIR = DATA_DIR / "storyboards"
AUDIO_DIR = DATA_DIR / "audio"
OUTPUT_DIR = DATA_DIR / "output"

def main():
    print("\n=======================================================")
    print("[Phase 4-B] 绝对时间轴视频装配台")
    print("=======================================================")
    
    if not NARRATIVE_FINAL_PATH.exists():
        print("[ERROR] 找不到 narrative_v6_final.json")
        sys.exit(1)
        
    master_audio_path = AUDIO_DIR / "master_voice.mp3"
    if not master_audio_path.exists():
        print("[ERROR] 找不到主音轨 master_voice.mp3")
        sys.exit(1)
        
    data = json.loads(NARRATIVE_FINAL_PATH.read_text(encoding="utf-8"))
    timeline = data.get("timeline", [])
    
    if not timeline:
        print("[ERROR] 时间轴 timeline 为空")
        sys.exit(1)
        
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("  [Audio] 正在读取主音轨长度...")
    master_audio = AudioFileClip(str(master_audio_path))
    total_audio_duration = master_audio.duration
    
    clips = []
    num_shots = len(timeline)
    
    print("  [Video] 正在根据 trigger_time 装配绝对时间轴...")
    
    for i in range(num_shots):
        shot_data = timeline[i]
        start_t = shot_data["trigger_time"]
        
        # 计算该画面的持续时间 = 下一个画面的触发时间 - 当前触发时间
        if i < num_shots - 1:
            end_t = timeline[i+1]["trigger_time"]
        else:
            # 最后一个画面持续到音频结束
            end_t = total_audio_duration
            
        duration = end_t - start_t
        
        # 容错：防止极端情况下浮点数精度导致 duration < 0
        if duration <= 0:
            duration = 0.1
            
        img_filename = f"S_{i+1:03d}.png"
        img_path = STORYBOARDS_DIR / img_filename
        
        if not img_path.exists():
            print(f"  [WARN] 找不到画面文件 {img_filename}，使用黑帧占位保持时间槽位。")
            clip = ColorClip(size=(1024, 768), color=(0, 0, 0)).set_duration(duration)
        else:
            clip = ImageClip(str(img_path)).set_duration(duration)
        clips.append(clip)
        
    if not clips:
        print("[ERROR] 没有有效视频片段，装配失败。")
        sys.exit(1)
        
    # 拼接全片
    final_video = concatenate_videoclips(clips, method="compose")
    final_video = final_video.set_audio(master_audio)
    
    out_file = OUTPUT_DIR / "narrative_v6_final_epic.mp4"
    print(f"  [Render] 正在渲染最终成片: {out_file.name} (请稍候...)")
    
    final_video.write_videofile(
        str(out_file),
        fps=24,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        logger=None # 避免打印过多干扰信息
    )
    
    print("\n[SUCCESS] 管线重构圆满结束！")
    print(f"  [OK] 完美卡点成片已输出至: {out_file.resolve()}")

if __name__ == "__main__":
    main()
