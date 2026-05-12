"""
投喂剧本入口（双轨制）
"""


from feishu.config import STATUS
from feishu.state_mgr import FeishuStateMgr


class RequestScriptFeedAction:
    """进入等待粘贴剧本状态"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        open_id = getattr(session, "open_id", "")
        sm = FeishuStateMgr()
        st = sm.get_current_state().get("status", STATUS["IDLE"])
        if st not in (
            STATUS["IDLE"],
            STATUS["WAITING_TOPIC"],
            STATUS["COMPLETED"],
        ):
            return {
                "toast": {
                    "type": "warning",
                    "content": "后台正在处理任务，请等待完成或发送「取消」后再投喂剧本。",
                }
            }
        sm.set_status(STATUS["WAITING_SCRIPT_FEED"], "")
        mgr.send_text(
            open_id,
            "open_id",
            "📝 老板请发送您的原始剧本、梗概或故事片段（建议千字以内）。\n"
            "可直接在下一条消息粘贴全文，也可上传 .txt / .md / .docx；发出后我会确认并开始润色。",
        )
        return {"toast": {"type": "success", "content": "请发送剧本（粘贴或上传文本文件）"}}
