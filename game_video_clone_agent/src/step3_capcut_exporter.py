"""
🎬 剪映草稿快速导出台 (src/step3_capcut_exporter.py)
自动读取当前运行批次（Run-ID）的 timeline 和音频，
直接在本地剪映草稿箱（C:\\Users\\...\\com.lveditor.draft）中生成一个完美的工程文件夹。
包含：音频轨道（master_voice.mp3）、分镜图片轨道（S_XXX.png）、以及基于 master_srt.json 对齐的字幕轨道。
"""
import json
import os
import sys
import shutil
import uuid
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pyJianYingDraft as draft
from src.run_context import get_paths, get_current_run_id

def get_jianying_draft_dir() -> Path:
    """自动获取 Windows 系统下剪映草稿文件夹位置"""
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        path = Path(local_appdata) / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft"
        if path.exists():
            return path
            
    user_profile = os.getenv("USERPROFILE")
    if user_profile:
        path = Path(user_profile) / "AppData" / "Local" / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft"
        if path.exists():
            return path
            
    # 兜底硬编码路径
    hardcoded = Path(r"C:\Users\86198\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft")
    if hardcoded.exists():
        return hardcoded
        
    return None

def split_subtitles(master_srt_json_path: Path):
    """
    按照 step3_assembler_v6.py 的完全一致逻辑，将 master_srt.json 拆分为短字幕切片
    """
    if not master_srt_json_path.exists():
        return []
    try:
        payload = json.loads(master_srt_json_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [ERROR] 读取字幕源失败: {e}")
        return []
        
    if not isinstance(payload, list):
        return []

    def _split_text_for_subtitles(text: str) -> list[str]:
        raw = (text or "").strip()
        if not raw:
            return []
        major_parts = []
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

        fine_parts = []
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

    _SUBTITLE_TIME_EPS = 0.02
    _SUBTITLE_MIN_SEG_SEC = 0.25

    norm_rows = []
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

    subtitle_segments = []
    for row in norm_rows:
        st = float(row["start_time"])
        et = float(row["end_time"])
        text = str(row["text"]).strip()

        chunks = _split_text_for_subtitles(text)
        if not chunks:
            continue

        total_span = max(_SUBTITLE_MIN_SEG_SEC, et - st)
        weights = [max(1, len(c.strip())) for c in chunks]
        weight_sum = max(1, sum(weights))
        dur_list = [total_span * (w / weight_sum) for w in weights]

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
            subtitle_segments.append({
                "start": seg_st,
                "end": seg_et,
                "text": chunk
            })
            cursor = seg_et

    return subtitle_segments

def export_draft_to_capcut():
    """读取当前 Run 的数据并写入到剪映草稿目录中"""
    print("\n=======================================================")
    print("[CapCut Exporter] 正在初始化剪映草稿箱导出流程...")
    
    # 1. 确认当前 Run 批次路径
    paths = get_paths(create_if_missing=False)
    if not paths:
        print("[ERROR] 未检测到当前活跃的 Run-ID，无法导出草稿！")
        return False
        
    run_id = get_current_run_id()
    print(f"  [Run] 当前批次: {run_id}")
    
    narrative_final_path = paths["scripts_dir"] / "narrative_v6_final.json"
    storyboards_dir = paths["storyboards_dir"]
    audio_dir = paths["audio_dir"]
    output_dir = paths["output_dir"]
    
    master_voice_path = audio_dir / "master_voice.mp3"
    master_srt_json_path = audio_dir / "master_srt.json"
    
    if not narrative_final_path.exists():
        print(f"  [ERROR] 找不到分镜脚本: {narrative_final_path}")
        return False
    if not master_voice_path.exists():
        print(f"  [ERROR] 找不到主音频: {master_voice_path}")
        return False
        
    # 2. 定位剪映草稿文件夹
    draft_root = get_jianying_draft_dir()
    if not draft_root:
        print("  [WARN] 找不到本机剪映草稿文件夹！将使用当前运行批次 output 文件夹作为输出。")
        draft_root = output_dir
    else:
        print(f"  [JianYing] 本地草稿库定位成功: {draft_root}")
        
    # 3. 确定草稿项目名称
    try:
        data = json.loads(narrative_final_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [ERROR] 解析分镜脚本失败: {e}")
        return False

    # 读取第一句话作为草稿名称，如果不存在则使用 topic
    draft_name = ""
    timeline = data.get("timeline", []) or data.get("shots", [])
    if timeline and timeline[0].get("text_segment"):
        first_sentence = timeline[0].get("text_segment").strip()
        invalid_chars = '\\/:*?"<>|'
        clean_title = "".join([c for c in first_sentence if c not in invalid_chars]).strip()
        clean_title = clean_title.replace("\n", " ").replace("\r", "").replace("\t", " ")
        if clean_title:
            draft_name = clean_title

    if not draft_name:
        topic_name = data.get("metadata", {}).get("topic", "自动生成故事")
        clean_topic = "".join([c for c in topic_name if c.isalnum() or c in ("_", "-")]).strip()
        if not clean_topic:
            clean_topic = "AutoStory"
        draft_name = f"自动故事_{clean_topic}_{run_id}"

    # 限制长度以避免 Windows 路径超长
    if len(draft_name) > 60:
        draft_name = draft_name[:60]

    project_dir = draft_root / draft_name

    # 4. 若已有同名草稿，尝试删除。如果删除失败，重命名为带时间戳的新名字
    if project_dir.exists():
        print(f"  [Info] 已存在同名草稿: {draft_name}，尝试删除以重新创建。")
        try:
            shutil.rmtree(project_dir)
            import time as _time; _time.sleep(0.5)  # 等待文件系统刷新
        except Exception as e:
            suffix = time.strftime("%Y%m%d_%H%M%S")
            draft_name = f"{draft_name}_{suffix}"
            project_dir = draft_root / draft_name
            print(f"  [Warn] 同名草稿删除失败（可能被剪映占用），已重命名为: {draft_name}")

    # 5. 初始化 pyJianYingDraft 并创建新草稿（每次都重新实例化 DraftFolder 避免缓存）
    folder = draft.DraftFolder(str(draft_root))
    try:
        script = folder.create_draft(draft_name, 1280, 720)
    except FileExistsError:
        # 若库内部缓存仍认为存在，且目录存在则强制删除，若仍失败则再次重命名
        if project_dir.exists():
            try:
                shutil.rmtree(project_dir)
            except Exception:
                suffix = time.strftime("%Y%m%d_%H%M%S")
                draft_name = f"{draft_name}_fallback_{suffix}"
        folder = draft.DraftFolder(str(draft_root))
        script = folder.create_draft(draft_name, 1280, 720)
        
    # 6. 添加音视频与字幕轨道
    video_track = script.add_track(draft.TrackType.video)
    audio_track = script.add_track(draft.TrackType.audio)
    text_track = script.add_track(draft.TrackType.text)
    
    # 7. 写入音频片段
    try:
        audio_material = draft.AudioMaterial(str(master_voice_path))
        audio_dur_us = audio_material.duration # 微秒
        audio_segment = draft.AudioSegment(
            audio_material,
            target_timerange=draft.Timerange(0, audio_dur_us)
        )
        script.add_segment(audio_segment)
        print(f"  [Audio] 音频导入成功，长度 {audio_dur_us / draft.SEC:.2f} 秒")
    except Exception as e:
        print(f"  [ERROR] 音频导入草稿失败: {e}")
        return False
        
    # 8. 写入图片片段（分镜）
    timeline = data.get("timeline", []) or data.get("shots", [])
    total_audio_duration_sec = audio_dur_us / draft.SEC
    num_shots = len(timeline)
    imported_images = 0
    
    for i in range(num_shots):
        shot = timeline[i]
        subshot_id = shot.get("subshot_id")
        trigger_time = float(shot.get("trigger_time", 0.0))
        
        start_t = trigger_time
        if i < num_shots - 1:
            end_t = float(timeline[i + 1].get("trigger_time", total_audio_duration_sec))
        else:
            end_t = total_audio_duration_sec
            
        duration = end_t - start_t
        if duration <= 0:
            duration = 0.1
            
        start_us = int(start_t * draft.SEC)
        duration_us = int(duration * draft.SEC)
        
        # 寻找对应的 png 图像文件
        img_name = f"{subshot_id}.png"
        img_path = storyboards_dir / img_name
        if not img_path.exists():
            # 兼容 shots 键中的 S_001.png
            img_name = f"S_{i+1:03d}.png"
            img_path = storyboards_dir / img_name
            
        if not img_path.exists():
            print(f"  [WARN] 找不到分镜大底片画面: {img_name}，跳过导入本帧。")
            continue
            
        try:
            img_material = draft.VideoMaterial(str(img_path))
            img_segment = draft.VideoSegment(
                img_material,
                target_timerange=draft.Timerange(start_us, duration_us)
            )
            script.add_segment(img_segment)
            imported_images += 1
        except Exception as e:
            print(f"  [WARN] 导入图片 {img_name} 失败: {e}")
            
    print(f"  [Storyboard] 成功在视频轨导入了 {imported_images} 张分镜大图")
    
    # 9. 导入字幕片段（基于 master_srt.json 的高精度句子拆分）
    imported_subtitles = 0
    sub_items = []
    if master_srt_json_path.exists():
        sub_items = split_subtitles(master_srt_json_path)
        for sub in sub_items:
            start_us = int(sub["start"] * draft.SEC)
            dur_us = int((sub["end"] - sub["start"]) * draft.SEC)
            text_str = sub["text"].strip()
            
            if text_str:
                try:
                    text_segment = draft.TextSegment(
                        text_str,
                        timerange=draft.Timerange(start_us, dur_us)
                    )
                    script.add_segment(text_segment)
                    imported_subtitles += 1
                except Exception as e:
                    print(f"  [WARN] 导入字幕「{text_str}」失败: {e}")
                    
        print(f"  [Subtitle] 字幕轨导入成功！基于语音对齐生成了 {imported_subtitles} 个独立字幕段")
    else:
        print("  [WARN] 找不到配音真实歌词轴 master_srt.json，将无法在草稿中创建字幕轨。")

    # 9b. 将字幕数据导出为标准 .srt 文件（先保存草稿，再写入，方便剪映素材面板识别）
    srt_path = None
    if sub_items:
        try:
            srt_lines = []
            for idx, sub in enumerate(sub_items, start=1):
                def _fmt_ts(sec: float) -> str:
                    h = int(sec // 3600)
                    m = int((sec % 3600) // 60)
                    s = int(sec % 60)
                    ms = int(round((sec - int(sec)) * 1000))
                    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
                srt_lines.append(str(idx))
                srt_lines.append(f"{_fmt_ts(sub['start'])} --> {_fmt_ts(sub['end'])}")
                srt_lines.append(sub['text'].strip())
                srt_lines.append("")
            srt_content = "\n".join(srt_lines)
            srt_filename = f"{draft_name[:40]}_字幕.srt"
            # SRT 先暂存于 output_dir，稍后在草稿文件夹建好后复制进去
            srt_temp_path = output_dir / srt_filename
            srt_temp_path.write_text(srt_content, encoding="utf-8-sig")
            srt_path = srt_temp_path
            print(f"  [SRT] 已生成字幕文件: {srt_filename}")
        except Exception as e:
            print(f"  [WARN] 生成 SRT 文件失败: {e}")
        
    # 10. 保存草稿
    try:
        draft_uuid = str(uuid.uuid4()).upper()
        script.content["id"] = draft_uuid
        
        script.save()
        print(f"  [Done] 剪映工程草稿创建成功！草稿位置: {project_dir}")

        # 10b. 将 SRT 文件复制到草稿文件夹内，并注入 draft_content.json 素材列表
        if srt_path and srt_path.exists():
            try:
                srt_in_draft = project_dir / srt_path.name
                shutil.copy2(str(srt_path), str(srt_in_draft))
                # 读取 draft_content.json 并向 materials.texts 或顶层 materials 注入 SRT 条目
                draft_content_path = project_dir / "draft_content.json"
                if draft_content_path.exists():
                    dc = json.loads(draft_content_path.read_text(encoding="utf-8"))
                    srt_material = {
                        "category_id": "",
                        "category_name": "local",
                        "duration": int(audio_dur_us),
                        "extra_info": "",
                        "file_Path": str(srt_in_draft).replace("\\", "/"),
                        "height": 0,
                        "id": str(uuid.uuid4()).upper(),
                        "import_time": int(time.time()),
                        "import_time_ms": int(time.time() * 1000),
                        "item_source": 1,
                        "md5": "",
                        "metetype": "subtitle",
                        "roughcut_time_offset": -1,
                        "sub_time_mapping": {},
                        "team_concurrency_setting": {},
                        "type": "subtitle",
                        "width": 0
                    }
                    # 写入 materials.subtitles（若不存在则创建）
                    if "materials" not in dc:
                        dc["materials"] = {}
                    if "subtitles" not in dc["materials"]:
                        dc["materials"]["subtitles"] = []
                    dc["materials"]["subtitles"].append(srt_material)
                    draft_content_path.write_text(json.dumps(dc, ensure_ascii=False), encoding="utf-8")
                    print(f"  [SRT] 已将字幕文件注入草稿素材面板: {srt_path.name}")
            except Exception as e:
                print(f"  [WARN] SRT 注入素材面板失败: {e}")
        
        # 写入/修改 draft_meta_info.json
        meta_path = project_dir / "draft_meta_info.json"
        meta_data = {}
        if meta_path.exists():
            try:
                meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        
        duration_us = script.duration
        current_time_us = int(time.time() * 1000000)
        
        meta_data.update({
            "draft_id": draft_uuid,
            "draft_fold_path": str(project_dir).replace("\\", "/"),
            "draft_name": draft_name,
            "draft_root_path": str(draft_root).replace("\\", "/"),
            "tm_duration": duration_us,
            "tm_draft_create": current_time_us,
            "tm_draft_modified": current_time_us,
            "draft_new_version": "164.0.0"
        })
        
        meta_path.write_text(json.dumps(meta_data, ensure_ascii=False), encoding="utf-8")
        
        # 写入/修改 root_meta_info.json
        root_meta_path = draft_root / "root_meta_info.json"
        if root_meta_path.exists():
            try:
                root_meta = json.loads(root_meta_path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  [WARN] 读取 root_meta_info.json 失败: {e}")
                root_meta = None

            if root_meta and "all_draft_store" in root_meta:
                store = root_meta["all_draft_store"]
                existing_idx = -1
                target_path_normalized = str(project_dir).replace("\\", "/").lower()
                for idx, entry in enumerate(store):
                    entry_path = str(entry.get("draft_fold_path", "")).replace("\\", "/").lower()
                    if entry_path == target_path_normalized:
                        existing_idx = idx
                        break
                
                new_entry = {
                    "cloud_draft_cover": False,
                    "cloud_draft_sync": False,
                    "draft_cloud_last_action_download": False,
                    "draft_cloud_purchase_info": "",
                    "draft_cloud_template_id": "",
                    "draft_cloud_tutorial_info": "",
                    "draft_cloud_videocut_purchase_info": "",
                    "draft_cover": str(project_dir / "draft_cover.jpg").replace("\\", "/"),
                    "draft_fold_path": str(project_dir).replace("\\", "/"),
                    "draft_id": draft_uuid,
                    "draft_is_ai_shorts": False,
                    "draft_is_cloud_temp_draft": False,
                    "draft_is_invisible": False,
                    "draft_is_web_article_video": False,
                    "draft_json_file": str(project_dir / "draft_content.json").replace("\\", "/"),
                    "draft_name": draft_name,
                    "draft_new_version": "164.0.0",
                    "draft_root_path": str(draft_root).replace("\\", "/"),
                    "draft_timeline_materials_size": os.path.getsize(project_dir / "draft_content.json") if (project_dir / "draft_content.json").exists() else 0,
                    "draft_type": "",
                    "draft_web_article_video_enter_from": "",
                    "streaming_edit_draft_ready": True,
                    "tm_draft_cloud_completed": "",
                    "tm_draft_cloud_entry_id": -1,
                    "tm_draft_cloud_modified": 0,
                    "tm_draft_cloud_parent_entry_id": -1,
                    "tm_draft_cloud_space_id": -1,
                    "tm_draft_cloud_user_id": -1,
                    "tm_draft_create": current_time_us,
                    "tm_draft_modified": current_time_us,
                    "tm_draft_removed": 0,
                    "tm_duration": duration_us
                }
                
                if existing_idx != -1:
                    store[existing_idx] = new_entry
                else:
                    store.append(new_entry)
                    if "draft_ids" in root_meta:
                        try:
                            root_meta["draft_ids"] = int(root_meta["draft_ids"]) + 1
                        except Exception:
                            pass
                
                try:
                    root_meta_path.write_text(json.dumps(root_meta, ensure_ascii=False), encoding="utf-8")
                    print(f"  [JianYing] 成功更新本地剪映草稿总索引注册表 (root_meta_info.json)")
                except Exception as e:
                    print(f"  [ERROR] 写入 root_meta_info.json 失败: {e}")
                    
        # 检查剪映是否正在运行
        try:
            import psutil
            jianying_running = False
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] and 'JianyingPro' in proc.info['name']:
                    jianying_running = True
                    break
            if jianying_running:
                print("  [WARN] 检测到剪映专业版正在后台运行。部分情况下，新导入的草稿需要【重启剪映】后方能正常在草稿箱中显示。")
        except Exception:
            pass

    except Exception as e:
        print(f"  [ERROR] 保存草稿或生成元数据失败: {e}")
        return False

    # 11. 在当前批次 output 文件夹中归档备份该草稿
    try:
        backup_project_dir = output_dir / f"Jianying_Draft_{run_id}"
        if backup_project_dir.exists():
            shutil.rmtree(backup_project_dir, ignore_errors=True)
            
        shutil.copytree(project_dir, backup_project_dir)
        print(f"  [Backup] 成功在当前批次 output 中备份了此草稿文件夹")
    except Exception as e:
        print(f"  [WARN] 归档备份草稿失败: {e}")
        
    print("=======================================================\n")
    return True

if __name__ == "__main__":
    export_draft_to_capcut()
