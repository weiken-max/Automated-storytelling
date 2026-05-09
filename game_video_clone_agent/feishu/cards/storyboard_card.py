"""
分镜宫格审核卡片
展示所有批次的 16 宫格预览图，每批有独立的打回按钮
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from feishu.cards.base_card import BaseCard
from feishu.config import ACTION, HEADER_TEMPLATES


class StoryboardCard(BaseCard):
    card_type = "storyboard"
    header_template = HEADER_TEMPLATES["blue"]

    def __init__(self, session, mgr, grid_files: list[Path],
                 run_id: str = "", batch_states: dict[int, str] | None = None):
        """
        grid_files:    已生成的宫格图路径列表
        batch_states:  {batch_index: "ok"|"failed"|"regening"} 每批次状态
        """
        super().__init__(session, mgr)
        self.grid_files = grid_files
        self.run_id = run_id or getattr(session, "session_id", "unknown")
        self.topic = getattr(session, "topic", "")
        self.header_title = f"🎬 分镜宫格审核：{self.topic}"
        self.batch_states = batch_states or {}
        self._img_cache: dict[str, str] = {}

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
        els.append(self.make_md(
            f"**Run-ID**：`{self.run_id}`\n"
            f"共 **{total_batches}** 个批次的 16 宫格预览图已生成。"
            "请逐张审核尺寸/布局是否正确，有问题请点按钮打回重画。"
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
                f"{emoji} **批次 {i}/{total_batches}**（分镜 S_{batch_start:03d}~S_{batch_end:03d}）{txt}"
            ))

            abs_path = gf if isinstance(gf, Path) else Path(str(gf))
            if abs_path.exists():
                img_key = self._upload_and_cache(str(abs_path))
                if img_key:
                    els.append(self.make_img(img_key, f"批次{i}"))
                else:
                    els.append(self.make_md(f"⚠️ 批次 {i} 图片上传失败：`{abs_path}`"))
            else:
                els.append(self.make_md(f"⚠️ 批次 {i} 文件不存在：`{abs_path}`"))

        return els

    def action_buttons(self) -> list[dict]:
        topic = self.topic
        rows = []

        # 每个批次一个打回按钮
        for i in range(1, len(self.grid_files) + 1):
            rows.append(self.make_action_row(
                self.make_button(
                    f"❌ 打回批次 {i}（重画）",
                    ACTION["REJECT_STORYBOARD_BATCH"],
                    "danger",
                    topic=topic,
                    batch_index=i,
                )
            ))

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
