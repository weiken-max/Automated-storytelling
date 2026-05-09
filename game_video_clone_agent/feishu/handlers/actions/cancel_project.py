"""
取消项目 Action
"""
import threading
from feishu.config import STATUS


class CancelProjectAction:
    """取消当前项目并重置"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        topic = data.get("topic", "") or getattr(session, "topic", "")
        open_id = getattr(session, "open_id", "")
        run_id = context.get("get_current_run_id", lambda: "")()
        kill_fn = context.get("kill_by_run_id")
        set_status = context.get("set_status")

        killed = 0
        if kill_fn and run_id:
            pip_stop = context.get("PIPELINE_STOP_FLAGS", {})
            pip_stop.setdefault(run_id, threading.Event()).set()
            killed = kill_fn(run_id)

        if set_status:
            set_status(STATUS["IDLE"], "")

        mgr.send_text(open_id, "open_id",
                      f"🗑️ 已取消项目【{topic}】并重置系统（终止 {killed} 个进程）。\n发送「换一批」可重新获取主题。")
        return {"toast": {"type": "success", "content": "项目已取消，系统已重置。"}}
