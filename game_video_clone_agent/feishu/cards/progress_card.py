"""
生产进度卡片（运维控制台）
生产进行中 / 暂停 / 错误态 使用，支持原地刷新进度条
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from feishu.cards.base_card import BaseCard
from feishu.config import ACTION, HEADER_TEMPLATES, STATUS


class ProgressCard(BaseCard):
    card_type = "progress"
    header_title = "🛠️ 运维控制台（原地刷新）"
    header_template = HEADER_TEMPLATES["blue"]

    def __init__(self, session, mgr,
                 status_text: str = "",
                 current: int = 0, total: int = 100,
                 detail: str = "",
                 run_id: str = "",
                 assets_info: dict | None = None,
                 queue_info: dict | None = None,
                 error_context: str = ""):
        super().__init__(session, mgr)
        self.status_text = status_text
        self.current = current
        self.total = max(1, total)
        self.detail = detail
        self.run_id = run_id or getattr(session, "session_id", "unknown")
        self.topic = getattr(session, "topic", "")
        self.assets_info = assets_info or {}
        self.queue_info = queue_info or {}
        self.error_context = error_context
        self._status = getattr(session, "status", STATUS["IDLE"])

    @staticmethod
    def _progress_bar(current: int, total: int, length: int = 20) -> str:
        filled = int(length * current / max(1, total))
        bar = "█" * filled + "░" * (length - filled)
        pct = int((current / max(1, total)) * 100)
        return f"[{bar}] {pct}%"

    def body_elements(self) -> list[dict]:
        content = (
            f"**🎬 项目**：{self.topic or '未命名'}\n"
            f"**🧪 Run-ID**：`{self.run_id or '未初始化'}`\n"
            f"**📍状态**：{self.status_text}\n"
            f"**📊进度**：{self._progress_bar(self.current, self.total)}"
        )
        if self.detail:
            content += f"\n\n{self.detail}"

        # 错误上下文
        if self.error_context:
            short_err = self.error_context[-320:] if len(self.error_context) > 320 else self.error_context
            content += f"\n\n**🧩 错误详情**：\n`{short_err}`"

        # 资产探针
        if self.assets_info:
            a = self.assets_info
            content += (
                f"\n\n**运行探针**\n"
                f"📦 剧本：{'✅' if a.get('full_story') else '⏳'}  "
                f"🎵 主音轨：{'✅' if a.get('master_voice') else '⏳'}\n"
                f"🧩 蓝图：{'✅' if a.get('narrative') else '⏳'}  "
                f"🖼️ 分镜：{a.get('s_count', 0)} 张\n"
                f"🎬 成片：{'✅' if a.get('final_mp4') else '⏳'}"
            )

        # 队列信息
        q = self.queue_info
        if q:
            if q.get("running"):
                content += f"\n\n🚦 队列：正在运行 [{q.get('running_desc', '')}] | 排队: {q.get('queue_len', 0)} 个"
            else:
                content += "\n\n🚦 队列：🟢 空闲"

        els = [self.make_md(content)]
        return els

    def action_buttons(self) -> list[dict]:
        topic = self.topic
        run_id = self.run_id
        rows = []

        if self._status == STATUS["ERROR"]:
            rows.append(self.make_action_row(
                self.make_button("🔁 重试失败环节", ACTION["RETRY_FAILED_STAGE"], "primary", topic=topic),
                self.make_button("🔄 强制重启后台", ACTION["RESTART_BACKEND"], "default"),
            ))
        elif self._status == STATUS["PAUSED"]:
            rows.append(self.make_action_row(
                self.make_button("▶️ 恢复生产", ACTION["RESUME_PRODUCTION"], "primary", topic=topic),
            ))

        rows.append(self.make_hr())
        rows.append(self.make_action_row(
            self.make_button("查看最新进度", ACTION["OPS_STATUS"], "default"),
            self.make_button("重跑 Step 1 (分镜/音轨)", ACTION["OPS_RETRY_STEP1"], "primary", run_id=run_id),
            self.make_button("重跑 Step 2 (生图)", ACTION["OPS_RETRY_STEP2"], "default", run_id=run_id),
        ))
        rows.append(self.make_action_row(
            self.make_button("重跑 Step 3 (合成)", ACTION["OPS_RETRY_STEP3"], "default", run_id=run_id),
            self.make_button("紧急中止该任务", ACTION["OPS_ABORT_RUN"], "danger", run_id=run_id),
        ))

        return rows
