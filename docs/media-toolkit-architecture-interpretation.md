# Media Toolkit 架构师视角解读

> **如何打开**：完整副本也在 Media Toolkit 仓库内：`D:\media-main\media-main\docs\architecture-interpretation.md`。若资源管理器或编辑器打不开 D 盘路径，可直接在本窗口阅读本文件（内容一致）。文中提到的 `CLAUDE.md`、`README.md`、`自媒体sop.md` 位于该仓库根目录。

## 1. 系统定位与范式

这是一个 **"人机协作 + 以文件系统为契约" 的短视频生产线**，而不是传统意义上的单体 Web 应用。

- **编排方式**：由 [Claude Code](https://claude.ai/code) 的 **Skills（斜杠命令）** 驱动各阶段；每个 Skill 对应流水线中的一环，输入/输出主要是约定路径下的 Markdown、音频、图片和 Remotion 源码。
- **渲染范式**：成片依赖 **[Remotion](https://www.remotion.dev/)**（React 程序化视频），目标格式为 **抖音竖屏 1080×1920、30fps**，与"代码即时间轴"的工程模型一致。

本质上：**智能体负责调研、写作、转代码与质检；Remotion CLI 负责确定性渲染；发布可走自动化（若启用）或人工。**

---

## 2. 逻辑分层（概念架构）

```mermaid
flowchart LR
  subgraph human [人与创意]
    Idea[选题与方向]
  end
  subgraph cognition [认知与内容层]
    Research[联网调研]
    Script[分镜脚本 script.md]
    ReviewScript[脚本审核 review.md]
  end
  subgraph assets [资产层]
    Footage[实拍 footage]
    Images[图与封面 images]
    Audio[配音与音效 audio]
  end
  subgraph production [生产层]
    RemotionCode[Remotion 项目 TSX]
    ReviewVideo[视频代码审核]
    MP4[渲染 MP4]
  end
  subgraph distribution [分发层]
    Publish[各平台发布]
  end
  Idea --> Research --> Script --> ReviewScript
  ReviewScript --> assets
  assets --> RemotionCode --> ReviewVideo --> MP4 --> Publish
```

| 层次 | 职责 | 主要产物 / 技术 |
|------|------|-------------------|
| 认知与内容 | 调研、分镜、事实核查、口播提取 | `script.md`、`voiceover.md`、`research.md`、`review.md`；Tavily 等搜索 |
| 资产 | 实拍、AI 图/音、封面 | `projects/.../assets/**`；火山方舟图、TTS、可选 Python 脚本叠字 |
| 生产 | 把脚本落成可渲染组合 | `remotion/src/projects/<slug>/composition.tsx` + `shots/`；共享 `components/` |
| 质量门禁 | 脚本级事实与成片级规范 | `/script-review`、`/video-review`（含抖音安全区、字幕、时长一致性等） |
| 分发 | 导出与上架 | `npx remotion render`；README 中的 `/douyin-publish`（auto-douyin） |

---

## 3. 数据流与"契约"

流水线的心脏是 **项目目录约定**，而非集中数据库：

- **项目根**：Media Toolkit 仓库中的 `CLAUDE.md` / `README.md` 约定为 `projects/<YYYY-MM-DD-<slug>>/`，脚本、审核、素材、输出路径一致，便于 Skill 之间松耦合串联。
- **向下游传递**：`script.md`（及 `voiceover.md`）是 Remotion 生成与审核的主要依据；音频进入 `public/` 或项目 `assets` 后由组合引用。
- **Remotion 侧**：每个视频一个 **Composition**，镜头拆成 **`shots/ShotN.tsx`**，在 `remotion/src/root.tsx` 注册——这是 **"一个 repo、多套成片配置"** 的共享内核模式。

**架构取舍**：优点是可审计、可版本管理、易手改；缺点是跨项目一致性完全依赖 Skill 与规范，需要 strong convention（你们在 CLAUDE 里用表格固化了路径）。

---

## 4. 集成边界（外部系统）

| 能力 | 用途 | 配置 |
|------|------|------|
| Tavily | 联网调研 | `TAVILY_API_KEY` |
| 火山方舟 | 封面 / AI 背景图等 | `VOLCARK_API_KEY` |
| 火山 TTS | 配音 | `VOLC_TTS_API_KEY` |
| auto-douyin | 抖音发布（README） | Cookie 等 |

**要点**：密钥按需配置即可跑通子流程（例如只做脚本可只配搜索），属于 **可选能力插件式集成**，符合个人/小团队工具链的运维现实。

---

## 5. 与你方《自媒体sop》及主文档的对照

`自媒体sop.md` 描述了一条清晰的 **9 步 SOP**；与 `README.md` / `CLAUDE.md` 对应关系如下（均在 Media Toolkit 仓库根目录）：

- **一致**：选题 → 调研 → 脚本 → 脚本审核 → 素材 → Remotion 代码 → 视频审核 → 渲染 → 发布的主干一致；`/video-script`、`/script-review`、`/remotion-video`、`/video-review` 贯穿其中。
- **SOP 未单独写出但 README 已包含**：`/voiceover`、`/video-cover`、（以及 README 中的）`/douyin-publish`——建议在 SOP 中显式插入 **配音** 与 **封面** 步骤序号，与 README 流水线表对齐。
- **渲染时机**：SOP 写明 **第 6 步不渲 MP4**，第 8 步或 `/video-review --render` 再出片；这与"先 Studio 预览、后确定性导出"的工程顺序一致。README 里 `/remotion-video` 某处若写"直接渲染到 output"，则属于 **文档表述需统一** 的点（以 SOP 的分步为准更清晰）。
- **发布**：SOP 第 9 步标注 **publish skill 尚未开发、需手动**；README 则描述 **`/douyin-publish`**。架构上应视为 **"发布自动化为可选/演进中能力"**，避免读者误以为仓库状态与 SOP 完全一致。
- **路径笔误**：SOP 第 5 节有一处 `projects/<slug>/assets/` 与全文 `YYYY-MM-DD-<slug>` 不一致，属于文档一致性小问题。

---

## 6. 架构风险与演进建议（简要）

- **规范即接口**：Skill 提示词或模板变更可能导致旧项目目录与新约定不兼容，建议对 `script.md` 的 frontmatter 或版本字段做 **轻量版本化**（若尚未有）。
- **审核双闸门**：脚本审核（事实）与视频审核（像素与代码）分离合理；长期可考虑 **单一 manifest**（JSON）描述镜头时长、资源路径，减少 Markdown 与 TSX 双写漂移。
- **多平台**：当前设计与组件（如 `SafeArea`、竖屏假设）明显偏抖音；若扩展横屏平台，需要在布局 primitive 层抽象 **画幅配置** 而非散落魔法数字。

---

## 7. 小结一句话

**Media Toolkit = Claude Skills 编排的内容与质检流水线 + 以项目目录为存储后端 + Remotion 作为唯一成片渲染引擎 + 火山/Tavily 等可插拔 API**；架构强项在 **可重复、可审计的流水线**；需留意 **SOP 与 README 在发布、配音/封面步骤上的同步**，以及 **Markdown 与代码 dual-source 的一致性维护成本**。
