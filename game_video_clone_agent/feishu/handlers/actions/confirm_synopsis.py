"""
大纲审批相关 Action
"""

from feishu.synopsis_duration_sync import (
    persist_synopsis_duration_seconds,
    sync_session_duration_from_feishu_synopsis,
)


class ConfirmSynopsisAction:
    """确认大纲通过，开始生成定妆照"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        topic = data.get("topic", "") or getattr(session, "topic", "")

        sync_session_duration_from_feishu_synopsis(session)
        # 飞书卡片时长 → feishu/temp_synopsis.json + 当前 Run 的 scripts/temp_synopsis.json
        if hasattr(session, "get_duration_seconds"):
            persist_synopsis_duration_seconds(session.get_duration_seconds())

        # 入队定妆照生成（通过 context 里的 enqueue_job 函数）
        enqueue = context.get("enqueue_job")
        run_visual_setup = context.get("run_visual_setup")
        if enqueue and run_visual_setup and callable(run_visual_setup):
            enqueue(session.open_id, f"生成定妆照: {topic}", run_visual_setup, topic, session.open_id)
            return {"toast": {"type": "success", "content": "已写入成片时长，正在生成定妆照..."}}
        else:
            return {"toast": {"type": "error", "content": "缺少执行上下文，请重试。"}}


class RequestReviseSynopsisAction:
    """请求修改大纲（引导用户输入修改意见）"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        mgr.send_text(
            session.open_id, "open_id",
            "✏️ 请直接说出您的修改意见，我会立刻重新生成大纲。\n例如：开头太平淡，要有更强的悬念感"
        )
        return {"toast": {"type": "info", "content": "请在对话框输入修改意见"}}
