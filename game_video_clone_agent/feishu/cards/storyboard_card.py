"""
分镜宫格审核卡片
展示所有批次的 16 宫格预览图，每批有独立的打回按钮。
V2：支持展开/收起批次提示词（英文原文），支持"使用修改后提示词打回"。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from feishu.cards.base_card import BaseCard
from feishu.config import ACTION, HEADER_TEMPLATES, PROMPT_VIEW_TEMPLATE


class StoryboardCard(BaseCard):
    card_type = "storyboard"
    header_template = HEADER_TEMPLATES["blue"]

    def __init__(self, session, mgr, grid_files: list[Path],
                 run_id: str = "", batch_states: dict[int, str] | None = None,
                 for_patch: bool = False):
        """
        grid_files:    已生成的宫格图路径列表
        batch_states:  {batch_index: "ok"|"failed"|"regening"} 每批次状态
        for_patch:     True 时只渲染文本变更（提示词展开/收起），跳过图片上传和渲染。
                       用于 PATCH 刷新，避免飞书客户端缓存旧 img_key 导致图片显示异常。
        """
        super().__init__(session, mgr)
        self.grid_files = grid_files
        self.run_id = run_id or getattr(session, "session_id", "unknown")
        self.topic = getattr(session, "topic", "")
        self.header_title = f"🎬 分镜宫格审核：{self.topic}"
        self.batch_states = batch_states or {}
        self._img_cache: dict[str, str] = {}
        self._for_patch = for_patch

        # ── V2：提示词展示状态（从 session 上下文读取）──
        self.expanded_batches: set[int] = set(
            session.get_context("expanded_batches") or []
        )
        self.translated_prompts: dict = (
            session.get_context("translated_prompts") or {}
        )

    def _has_revisions(self, batch_index: int) -> bool:
        """检查某个批次是否有待写回的提示词修改"""
        revised = self.session.get_context(f"revised_prompts_batch_{batch_index}")
        return bool(revised)

    def _upload_and_cache(self, img_path: str) -> str | None:
        if img_path in self._img_cache:
            return self._img_cache[img_path]
        key = self.mgr.upload_image(img_path)
        if key:
            self._img_cache[img_path] = key
        return key

    def body_elements(self) -> list[dict]:
        els = []
        total_batches = len(self.grid_files)

        # ── PATCH 模式：渲染完整卡片（含图片 + 提示词文本变更）──
        if self._for_patch:
            els.append(self.make_md(
                f"**Run-ID**：`{self.run_id}`\n"
                f"共 **{total_batches}** 个批次的 16 宫格预览图已生成。\n"
                "🆕 点击 **「查看提示词」** 可展开该批次所有子分镜的英文提示词（原文），"
                "修改意见请按模板发文字消息。"
            ))
            for i in range(1, total_batches + 1):
                batch_start = (i - 1) * 16 + 1
                batch_end = batch_start + 15
                is_expanded = i in self.expanded_batches
                has_rev = self._has_revisions(i)

                els.append(self.make_hr())
                els.append(self.make_md(
                    f"{'📋' if is_expanded else '✅'} **批次 {i}/{total_batches}**"
                    f"（分镜 S_{batch_start:03d}~S_{batch_end:03d}）"
                    f"{' ✏️已修改' if has_rev else ''}"
                ))

                # ── 宫格图（PATCH 模式也包含图片，保持卡片完整性）──
                if i <= len(self.grid_files):
                    gf = self.grid_files[i - 1]
                    abs_path = gf if isinstance(gf, Path) else Path(str(gf))
                    if abs_path.exists():
                        img_key = self._upload_and_cache(str(abs_path))
                        if img_key:
                            els.append(self.make_img(img_key, f"批次{i}"))
                        else:
                            els.append(self.make_md(f"⚠️ 批次 {i} 图片上传失败：`{abs_path}`"))
                    else:
                        els.append(self.make_md(f"⚠️ 批次 {i} 文件不存在：`{abs_path}`"))

                toggle_label = (
                    f"📋 收起提示词 | 批次 {i}"
                    if is_expanded
                    else f"📋 查看提示词 | 批次 {i}"
                )
                toggle_action = "hide" if is_expanded else "show"

                reject_label = (
                    f"❌ 打回批次 {i}（使用修改后提示词重画）"
                    if has_rev
                    else f"❌ 打回批次 {i}（重画）"
                )
                reject_action = (
                    ACTION["REJECT_BATCH_WITH_PROMPTS"]
                    if has_rev
                    else ACTION["REJECT_STORYBOARD_BATCH"]
                )

                els.append(self.make_action_row(
                    self.make_button(
                        toggle_label, ACTION["TOGGLE_BATCH_PROMPTS"], "default",
                        topic=self.topic, batch_index=i, action=toggle_action,
                    ),
                    self.make_button(
                        reject_label, reject_action, "danger",
                        topic=self.topic, batch_index=i,
                    ),
                ))

                if is_expanded:
                    prompts = self.translated_prompts.get(str(i), {})
                    if prompts:
                        revised = self.session.get_context(
                            f"revised_prompts_batch_{i}"
                        ) or {}
                        lines = [
                            f"📝 **批次 {i} 提示词**"
                            f"（点击「收起提示词」折叠）\n"
                        ]
                        for j in range(16):
                            sid = f"S_{batch_start + j:03d}"
                            cn_prompt = prompts.get(sid, "（暂无）")
                            marker = " ✏️已修改" if sid in revised else ""
                            lines.append(f"**批次 {i} {sid}{marker}**：{cn_prompt}\n")
                        lines.append("\n" + PROMPT_VIEW_TEMPLATE)
                        els.append(self.make_md("".join(lines)))
                    else:
                        els.append(self.make_md(
                            f"⏳ 批次 {i} 提示词加载中，请稍后重试..."
                        ))
            return els

        # ── 非 PATCH 模式：完整卡片（含宫格图）──
        els.append(self.make_md(
            f"**Run-ID**：`{self.run_id}`\n"
            f"共 **{total_batches}** 个批次的 16 宫格预览图已生成。\n"
            "🆕 点击 **「查看提示词」** 可展开该批次所有子分镜的英文提示词（原文），"
            "修改意见请按模板发文字消息。"
        ))

        state_emoji = {"ok": "✅", "failed": "❌", "regening": "🔄"}
        state_text = {"ok": "已就绪", "failed": "生成失败", "regening": "重画中..."}

        for i, gf in enumerate(self.grid_files, 1):
            batch_start = (i - 1) * 16 + 1
            batch_end = batch_start + 15
            st = self.batch_states.get(i, "ok")
            emoji = state_emoji.get(st, "✅")
            txt = state_text.get(st, "已就绪")

            els.append(self.make_hr())
            els.append(self.make_md(
                f"{emoji} **批次 {i}/{total_batches}**"
                f"（分镜 S_{batch_start:03d}~S_{batch_end:03d}）{txt}"
            ))

            # ── 宫格图 ──
            abs_path = gf if isinstance(gf, Path) else Path(str(gf))
            if abs_path.exists():
                img_key = self._upload_and_cache(str(abs_path))
                if img_key:
                    els.append(self.make_img(img_key, f"批次{i}"))
                else:
                    els.append(self.make_md(f"⚠️ 批次 {i} 图片上传失败：`{abs_path}`"))
            else:
                els.append(self.make_md(f"⚠️ 批次 {i} 文件不存在：`{abs_path}`"))

            # ── V2：查看/收起 提示词按钮 ──
            is_expanded = i in self.expanded_batches
            toggle_label = (
                f"📋 收起提示词 | 批次 {i}"
                if is_expanded
                else f"📋 查看提示词 | 批次 {i}"
            )
            toggle_action = "hide" if is_expanded else "show"

            # 打回按钮标签和动作
            has_rev = self._has_revisions(i)
            reject_label = (
                f"❌ 打回批次 {i}（使用修改后提示词重画）"
                if has_rev
                else f"❌ 打回批次 {i}（重画）"
            )
            reject_action = (
                ACTION["REJECT_BATCH_WITH_PROMPTS"]
                if has_rev
                else ACTION["REJECT_STORYBOARD_BATCH"]
            )

            els.append(self.make_action_row(
                self.make_button(
                    toggle_label,
                    ACTION["TOGGLE_BATCH_PROMPTS"],
                    "default",
                    topic=self.topic,
                    batch_index=i,
                    action=toggle_action,
                ),
                self.make_button(
                    reject_label,
                    reject_action,
                    "danger",
                    topic=self.topic,
                    batch_index=i,
                ),
            ))

            # ── V2：展开时显示提示词区域 ──
            if is_expanded:
                prompts = self.translated_prompts.get(str(i), {})
                if prompts:
                    # 检查哪些被修改过
                    revised = self.session.get_context(
                        f"revised_prompts_batch_{i}"
                    ) or {}

                    lines = [
                        f"📝 **批次 {i} 提示词**"
                        f"（点击「收起提示词」折叠）\n"
                    ]
                    for j in range(16):
                        sid = f"S_{batch_start + j:03d}"
                        cn_prompt = prompts.get(sid, "（暂无）")
                        marker = " ✏️已修改" if sid in revised else ""
                        lines.append(f"**批次 {i} {sid}{marker}**：{cn_prompt}\n")

                    lines.append("\n" + PROMPT_VIEW_TEMPLATE)
                    els.append(self.make_md("".join(lines)))
                else:
                    els.append(self.make_md(
                        f"⏳ 批次 {i} 提示词加载中，请稍后重试..."
                    ))

        return els

    def action_buttons(self) -> list[dict]:
        topic = self.topic
        rows = []

        rows.append(self.make_hr())
        rows.append(self.make_action_row(
            self.make_button(
                "✅ 全部通过，开始切分高清 + 视频合成",
                ACTION["APPROVE_STORYBOARDS"],
                "primary",
                topic=topic,
            )
        ))
        return rows
