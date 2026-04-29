# 🎬 Automated Storytelling Pipeline

这是一个“剧情驱动自动讲故事视频生成”项目，不是素材混剪项目。

当前主链路目标：
- A/B 两阶段分镜（A 产结构，B 产提示词）
- 主音轨连续化（DSP：trim + crossfade + loudness normalize）
- Step3 主音轨驱动时间轴执行
- 全链路统一 4:3

---

## 🚀 运行流程（必须按序）

### 1) 剧本规划（Planner）
运行：
- `python -m src.story_planner_v6`

产物：
- `data/scripts/full_story_v6.json`

---

### 2) 分镜结构 + 主音轨先行（Step1）
运行：
- `python -m src.step1_writer_v6`

功能：
- 先生成 `srt_like_timeline.json`（文案语义时间轴）
- 基于语义段做 TTS，合成为 `master_voice.mp3`，并产出真实 `line_timeline.json`
- A 阶段只产结构：`beat_id/subshot_count/subshot_id/role/continuity_lock`
- B 阶段按 A 结构产 prompt，并执行门禁（数量/ID/长度/重复率/连续性/语义相关）

核心产物：
- `data/scripts/srt_like_timeline.json`
- `data/audio/master_voice.mp3`
- `data/scripts/line_timeline.json`
- `data/scripts/narrative_v6.json`

---

### 3) 容器生图（Step2）
运行：
- `python -m src.step2_comic_generator_v6`

功能：
- 按 beat 强绑定容器策略生图（1/2/3-4 subshot）
- 容器请求直接走目标比例（不再固定 16:9）
- 分镜图统一归一到 4:3
- 校验 Step1 的主音轨与时间线存在后继续执行

核心产物：
- `data/storyboards/*.png`（单镜 4:3）

---

### 4) 视频合成（Step3）
运行：
- `python -m src.step3_assembler_v6`

功能：
- 读取 `master_voice.mp3 + line_timeline.json`
- 按主音轨时间轴切换镜头（仅告警，不改切点）
- 生成 4:3 成片

产物：
- `data/output/narrative_v6_final_epic.mp4`

---

## 📐 尺寸与容器策略（冻结）

- 最终成片：4:3
- 1 subshot：单图（4:3 @ 1K）
- 2 subshot：二宫格容器（2:3 @ 1K，上下切），切分后单镜仍归一为 4:3
- 3/4 subshot：四宫格（4:3 @ 2K）

---

## 🧾 错误与日志

统一错误模型字段：
- `task_id`
- `stage`
- `beat_id`
- `subshot_id`
- `error_code`
- `error_message`
- `raw_response_snippet`

日志目录：
- `data/logs/`

---

## 📦 最小可运行目录（建议保留）

- `src/`（核心代码）
- `feishu/`（飞书交互与状态管理）
- `data/scripts/`（运行时脚本与时间轴产物）
- `data/storyboards/`（分镜帧产物目录，可清空但建议保留目录）
- `data/audio/`（主音轨目录，可清空但建议保留目录）
- `data/output/`（成片目录，可清空但建议保留目录）
- `.env`（本地密钥配置，不提交到 git）
- `requirements.txt` / 启动脚本（如 `STARTUP_SILENT.bat`）

说明：
- 本项目主链路为：`Step1(主音轨+时间轴) -> Step2(仅生图) -> Step3(主音轨驱动合成)`。
- 历史日志、历史样片、迁移说明等文件不影响主链路运行，可按需清理。
