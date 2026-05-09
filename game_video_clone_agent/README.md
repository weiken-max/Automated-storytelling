# 🎬 Automated Storytelling Pipeline（game_video_clone_agent）

工业化「音频先行、物理时间轴锁死、16 宫格生图、绝对卡点装配」的叙事视频管线。**详细原理见** `项目运作原理与执行流程详解.md`；**飞书交互见** `飞书机器人系统说明.md`。

---

## 核心链路（与当前代码一致）

1. **剧本与定妆**：`story_planner_v6` → `full_story_v6.json`；`ref_generator` 生成定妆与锚点回写，并把梗概 Cast 的英文提示词写入 **`scripts/refs-prompt.json`**（Phase3 优先从此文件读「角色外观语义锚点」）。  
   - **定妆三视图**单独使用 `style_config.REF_STYLE_ANCHOR`（极简氰化物、扁平、弱阴影）；分镜/场景仍用 `STYLE_ANCHOR`。人物侧提示以 **身份 + 时代/气质** 为主，`refs/**/description.txt` 里的中文摘要默认 **不** 作为生图主 prompt（仅供人读）。
2. **主音轨 + Beat（Step1 / phase2）**：`step1_writer_v6 --phase phase2` → `master_voice.mp3`、`master_srt.json`、`pseudo_srt.json`。  
3. **分镜与 trigger_time（Step1 / phase3）**：`step1_writer_v6 --phase phase3` → `narrative_v6_final.json`（**每个 Beat 两次 LLM：先打 `<subshot>` 标签，再生成 `visual_prompt`**；带上一 Beat 摘要作前情；失败重试后仍失败则**进程退出**，不静默跳过 Beat）。  
4. **16 宫格生图（Step2）**：`step2_comic_generator_v6` → `storyboards/grid_batch_*.png`、`S_*.png` + `logs/step2_*.json(l)`。  
5. **合成（Step3）**：`step3_assembler_v6` → `output/narrative_v6_final_epic.mp4`（默认画面 **1280×720**，由 `step3_assembler_v6` 中 `FRAME_SIZE` 决定）。  

Step2 的 16 宫格图源请求为 **16:9、约 2K（如 2560×1440）**；Step3 将单镜缩放并 pad 到成片的固定画幅。

Step1 完成后系统进入 `STEP1_READY` 状态；Step2 若失败则置 `STEP2_FAILED` 并阻断合成，需运维重试 Step2。

---

## 🚀 运行流程（须按序；飞书侧通常已串联）

### Run-ID 隔离

- 每任务：`data/runs/Run_YYYYMMDD_HHMMSS_xxx/`
- 当前批次：`data/runs/current_run.json`
- 飞书：`/switch Run_...` 可切换批次后单步重跑

### 命令入口（开发/手工）

| 步骤 | 命令 | 主要产物 |
|------|------|----------|
| 规划 | `python -m src.story_planner_v6` | `scripts/full_story_v6.json` 等 |
| 定妆 | `python -m src.ref_generator` | `refs/`、锚点回写 |
| Step1-2 | `python -m src.step1_writer_v6 --phase phase2` | `audio/master_voice.mp3`, `audio/master_srt.json`, `scripts/pseudo_srt.json` |
| Step1-3 | `python -m src.step1_writer_v6 --phase phase3` | `scripts/narrative_v6_final.json` |
| Step2 | `python -m src.step2_comic_generator_v6` | `storyboards/`, `logs/step2_report.json` |
| Step3 | `python -m src.step3_assembler_v6` | `output/narrative_v6_final_epic.mp4` |

---

## 🧾 错误与日志

- Step2：`data/runs/<run_id>/logs/step2_failures.jsonl`、`step2_report.json`  
- 飞书：`feishu/hub.py` 在 Step2 **进程失败**或 **Step2 门禁未通过**时会推送明确告警，避免静默卡住。  
- Phase3：`step1_writer_v6` 某 Beat 多次失败后终端打印 `beat_id`、时间范围与阶段并 **非 0 退出**。
- Step2 宫格校验：`src/grid_validators.py` 默认使用“**全图寻峰 + 4×4 结构**”规则（先校验 16:9 与可四等分，再检查 3 条竖线/3 条横线、间距均匀与理论锚点偏差）；不合格批次会在 `step2_failures.jsonl` 记录 `GRID_LAYOUT_INVALID` 并触发重试。

---

## ⚙️ 生图相关环境变量（`.env`）

与 `src/image_engine.py` 一致（节选）：

- `IMAGE_GEN_MAX_CONCURRENCY`：最大并发，默认 `3`  
- **`IMAGE_GEN_TIMEOUT_SECONDS`：单次生图等待秒数，默认 `180`**（过短易在慢速 16 宫格上误触发重试、浪费配额）  
- `IMAGE_GEN_MAX_RETRIES`：单请求重试次数，默认 `3`  
- `IMAGE_GEN_RETRY_BASE_DELAY_SECONDS`：重试退避基数，默认 `1.5`  

与 `src/grid_validators.py` 相关（Step2 宫格准入）：

- `GRID_SPACING_MAX_CV`：分割线间距变异系数上限（默认 `0.50`，越小越严格）  
- `GRID_PEAK_ANCHOR_MAX_DEV_RATIO`：分割线相对理论四等分锚点的最大偏差比例（默认 `0.15`）  
- `GRID_VALIDATOR_LEGACY`：设为 `1/true/yes` 时切回旧版带状峰/贯通式校验（默认关闭）  

---

## 🛠 飞书运维（摘要）

- `/status` / `状态`、 `/switch Run_...`、`/retry step2`、`/retry step3`  
- 全局 FIFO 队列、状态卡原地刷新、按 Run-ID 精准中止  

全文见 `飞书机器人系统说明.md`。

---

## 📦 仓库中建议保留的目录

- `src/`、`feishu/`、`data/`（含 `runs/` 结构）、`requirements.txt`、启动脚本、`.env`（本地、勿提交）

其他说明见 `项目文件清单与用途说明.md`。
