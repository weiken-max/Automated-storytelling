"""
🎞️ 剧情解构与物理时间轴底座 (src/step1_writer_v6.py)
==========================================================
阶段二 (Phase 2)：读取纯净长文案 -> 生成音频/SRT -> 临时行号切分 Beat -> 产出 pseudo_srt.json
阶段三 (Phase 3)：切分 text_segment -> 线性插值计算绝对 trigger_time -> 产出 narrative_v6_final.json
"""

import json
import os
import sys
import argparse
import subprocess
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# ── 路径与环境配置 ──
load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
DATA_DIR = BASE_DIR / "data"

from src.style_config import LLM_API_KEY, LLM_BASE_URL, MODEL_LLM, FULL_STORY_V6_PATH, SCRIPT_DIR
from src.project_vault import backup as vault_backup

MODEL_WRITER = MODEL_LLM

# 尝试获取 AUDIO_DIR，若无则默认
try:
    from src.style_config import AUDIO_DIR
except ImportError:
    AUDIO_DIR = DATA_DIR / "audio"

PSEUDO_SRT_PATH = SCRIPT_DIR / "pseudo_srt.json"
MASTER_SRT_PATH = AUDIO_DIR / "master_srt.json"
NARRATIVE_FINAL_PATH = SCRIPT_DIR / "narrative_v6_final.json"

def get_client():
    return OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

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

# ==============================================================================
#  [Phase 2] 生成音频底座与 Beat 划分
# ==============================================================================

def generate_master_audio_and_srt(text: str, audio_path: Path) -> list:
    """调用 edge-tts 生成音频并解析 VTT 为 JSON SRT，构建绝对物理时间轴"""
    print("  🔊 [TTS] 正在调用 Edge-TTS 生成主音频与物理字幕...")
    vtt_path = audio_path.with_suffix('.vtt')
    temp_txt = audio_path.with_suffix('.txt')
    temp_txt.write_text(text, encoding='utf-8')
    
    cmd = [
        "edge-tts",
        "-f", str(temp_txt),
        "--write-media", str(audio_path),
        "--write-subtitles", str(vtt_path),
        "--voice", "zh-CN-YunxiNeural",  
        "--rate", "+10%" 
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        print("❌ [FATAL] 找不到 edge-tts 命令。请在终端运行: pip install edge-tts")
        temp_txt.unlink(missing_ok=True)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"❌ [TTS] 音频生成失败: {e.stderr.decode('utf-8', errors='ignore')}")
        temp_txt.unlink(missing_ok=True)
        sys.exit(1)
        
    temp_txt.unlink(missing_ok=True)

    lines = vtt_path.read_text(encoding='utf-8').strip().split('\n')
    srt_data = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if '-->' in line:
            times = line.split('-->')
            start_time = parse_vtt_time(times[0].strip())
            end_time = parse_vtt_time(times[1].strip())
            
            if i + 1 < len(lines):
                text_content = lines[i+1].strip()
                j = i + 2
                while j < len(lines) and lines[j].strip() and '-->' not in lines[j]:
                    text_content += " " + lines[j].strip()
                    j += 1
                
                if len(text_content.replace(' ', '')) > 0:
                    srt_data.append({
                        "start_time": start_time,
                        "end_time": end_time,
                        "text": text_content
                    })
                i = j - 1
        i += 1
        
    MASTER_SRT_PATH.write_text(json.dumps(srt_data, ensure_ascii=False, indent=2), encoding='utf-8')
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
任务：将我提供的【带行号的连续旁白】，按照叙事起伏划分为 6-12 个连续的剧情节拍 (Beat)。

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
        response = client.chat.completions.create(
            model=MODEL_LLM,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"需要切分的行号文本：\n\n{text_payload}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.2
        )
        result = json.loads(response.choices[0].message.content)
        beats_plan = result.get("beats", [])
        
        pseudo_srt = []
        for b in beats_plan:
            s_idx = max(0, min(b["start_index"], len(srt_data)-1))
            e_idx = max(0, min(b["end_index"], len(srt_data)-1))
            
            cues = srt_data[s_idx:e_idx+1]
            beat_text = "".join([c["text"] for c in cues])
            
            pseudo_srt.append({
                "beat_id": b["beat_id"],
                "summary": b["summary"],
                "start_time": cues[0]["start_time"],
                "end_time": cues[-1]["end_time"],
                "text": beat_text,
                "cues": cues
            })
            
        print(f"  ✅ [LLM] Beat 拆解完毕，共切分为 {len(pseudo_srt)} 个节拍！临时行号已安全丢弃。")
        return pseudo_srt
    except Exception as e:
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

def generate_visual_subshots(
    beat: dict,
    text_anchors: dict,
    physical_anchors: dict,
    stage_map: list,
    beat_start_subshot_id: int
) -> list:
    """调用 LLM 打标并生成提示词，再计算插值绝对时间戳"""
    print(f"  🎬 [Vision] 正在解构 Beat 并计算插值: {beat['summary']} ...")
    beat_text = beat["text"]
    beat_summary = (beat.get("summary") or "").strip()
    if not beat_summary:
        raise ValueError(f"Beat {beat.get('beat_id', 'unknown')} 缺少 summary，拒绝继续生成 visual_prompt。")
    if not text_anchors and not physical_anchors:
        raise ValueError("缺少角色锚点（text_anchors/physical_anchors 均为空），拒绝继续生成 visual_prompt。")

    system_prompt = f"""你是一个顶级的电影分镜师和AI绘图专家。
任务：根据剧情节拍文本，先在文本中插入 <subshot> 标签标记分镜切换点，再为每个分镜生成 visual_prompt。

【文本定妆锚点（角色外观语义约束）】：
{json.dumps(text_anchors, ensure_ascii=False, indent=2)}

【物理定妆锚点（真实参考图路径）】：
{json.dumps(physical_anchors, ensure_ascii=False, indent=2)}

【切分与提示词规则】：
1. 必须输出 `tagged_text`：在原文中插入 `<subshot>` 作为分镜边界。除插入标签外，原文本内容不得改写、不得丢字。
2. 切换时机：在场景转换、人物动作变化或情绪转折处打标签。每个 Beat 建议切出 2-4 个分镜。
3. 必须输出 `visual_prompts` 数组，长度必须与分镜数量一致，顺序严格对应。
4. 视觉提示词 (visual_prompt)：
   - 必须保留画风控制：Cyanide and Happiness comic style, flat illustration, simple line art, pure 2D, solid colors.
   - 必须遵守用户给定的人生阶段提示（child/youth/middle/elderly），确保人物连戏。
   - 详细描述镜头景别、人物动作和背景。

输出严格 JSON 格式：
{{
  "tagged_text": "原文第一段<subshot>原文第二段<subshot>原文第三段",
  "visual_prompts": ["prompt1", "prompt2", "prompt3"]
}}"""

    client = get_client()
    try:
        response = client.chat.completions.create(
            model=MODEL_WRITER,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Beat故事概括(summary): {beat_summary}\n"
                        f"该 Beat 的起始 subshot_id: S_{beat_start_subshot_id:03d}\n"
                        f"分镜阶段判定规则(stage_map): {json.dumps(stage_map, ensure_ascii=False)}\n"
                        "请在生成每个 visual_prompt 时，按将来分镜顺序(从起始 subshot_id 开始依次+1)匹配对应阶段。\n"
                        f"需要打标并分镜的原文：\n{beat_text}"
                    ),
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.4
        )
        result = json.loads(response.choices[0].message.content)
        tagged_text = (result.get("tagged_text") or "").strip()
        visual_prompts = result.get("visual_prompts", [])
        text_segments = _extract_segments_from_tagged_text(tagged_text)

        # 回退兼容旧输出结构
        if (not text_segments or len(text_segments) != len(visual_prompts)) and isinstance(result.get("subshots"), list):
            legacy_subshots = result.get("subshots", [])
            text_segments = [s.get("text_segment", "").strip() for s in legacy_subshots if s.get("text_segment", "").strip()]
            visual_prompts = [s.get("visual_prompt", "").strip() for s in legacy_subshots if s.get("text_segment", "").strip()]

        if not text_segments or len(text_segments) != len(visual_prompts):
            print("❌ [Vision] LLM 返回的 <subshot> 标注结果不合法，无法对齐文本与提示词。")
            return []

        # --- 核心算法：触发时间绝对值映射 ---
        current_char_idx = 0
        subshots_with_time = []
        
        for i, t_segment in enumerate(text_segments):
            v_prompt = visual_prompts[i]
            subshot_id_num = beat_start_subshot_id + i
            protagonist_stage = _resolve_subshot_stage(subshot_id_num, stage_map)
            anchor_look = _pick_stage_anchor(protagonist_stage, physical_anchors)
            
            # 算法调用：计算此 subshot 第一个字的绝对爆发时间
            t_trigger = calculate_trigger_time(current_char_idx, beat["cues"])
            
            subshots_with_time.append({
                "text_segment": t_segment,
                "trigger_time": t_trigger,
                "visual_prompt": v_prompt,
                "protagonist_stage": protagonist_stage,
                "anchor_look": anchor_look
            })
            
            # 游标向前推进
            current_char_idx += len(t_segment)
            
        return subshots_with_time
    except Exception as e:
        print(f"❌ [Vision] Beat 分镜解析失败: {e}")
        return []

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
        master_audio_path = AUDIO_DIR / "master.mp3"
        
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
        text_anchors = master_design.get("character_anchors", {})
        physical_anchors = master_design.get("physical_char_anchors", {})
        stage_map = master_design.get("stage_map", [])

        if not text_anchors and not physical_anchors:
            print("❌ [Phase3] 未检测到任何角色锚点：character_anchors 与 physical_char_anchors 均为空。")
            print("   请先确保阶段一已成功生成并回写定妆锚点。")
            sys.exit(1)
        
        final_narrative = []
        global_subshot_id = 1
        
        for beat in beats:
            try:
                subshots = generate_visual_subshots(
                    beat=beat,
                    text_anchors=text_anchors,
                    physical_anchors=physical_anchors,
                    stage_map=stage_map,
                    beat_start_subshot_id=global_subshot_id
                )
            except ValueError as e:
                print(f"❌ [Phase3] 输入验收失败: {e}")
                sys.exit(1)
            
            # 装配并降维到 final_narrative 一维数组
            for s in subshots:
                final_narrative.append({
                    "subshot_id": f"S_{global_subshot_id:03d}",
                    "beat_id": beat["beat_id"],
                    "trigger_time": s["trigger_time"],
                    "text_segment": s["text_segment"],
                    "visual_prompt": s["visual_prompt"],
                    "protagonist_stage": s.get("protagonist_stage", "middle"),
                    "anchor_look": s.get("anchor_look", "")
                })
                global_subshot_id += 1
                
        output_data = {
            "metadata": pseudo_data.get("metadata", {}),
            "timeline": final_narrative
        }
        
        NARRATIVE_FINAL_PATH.write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")
        vault_backup(NARRATIVE_FINAL_PATH, f"scripts/{NARRATIVE_FINAL_PATH.name}")
        
        print(f"\n🏆 阶段三 (分镜插值与视觉蓝图) 成功完工！")
        print(f"📍 核心产物: {NARRATIVE_FINAL_PATH}")
        print(f"   共生成 {len(final_narrative)} 个毫秒级精准卡点分镜。")

if __name__ == "__main__":
    main()
