"""
暂停/恢复 Action
"""

from feishu.config import STATUS
import threading


class PauseProjectAction:
    """暂停当前生产"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        open_id = getattr(session, "open_id", "")
        run_id = context.get("get_current_run_id", lambda: "")()
        set_status = context.get("set_status")
        topic = getattr(session, "topic", "")

        pip_stop = context.get("PIPELINE_STOP_FLAGS", {})
        if run_id:
            pip_stop.setdefault(run_id, threading.Event()).set()

        if set_status:
            set_status(STATUS["PAUSED"], topic)

        mgr.send_text(open_id, "open_id", "⏸️ 生产已暂停。点击「恢复生产」继续。")
        return {"toast": {"type": "info", "content": "生产已暂停。"}}


class ResumeProjectAction:
    """恢复暂停的生产"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        topic = getattr(session, "topic", "")
        open_id = getattr(session, "open_id", "")
        run_id = context.get("get_current_run_id", lambda: "")()
        set_status = context.get("set_status")

        pip_stop = context.get("PIPELINE_STOP_FLAGS", {})
        pip_stop.pop(run_id, None)

        if set_status:
            set_status(STATUS["STEP2_GENERATING"], topic)

        enqueue = context.get("enqueue_job")
        run_pipeline = context.get("run_project_pipeline")
        if enqueue and run_pipeline:
            enqueue(open_id, f"恢复生产: {topic}", run_pipeline, topic, open_id)
            return {"toast": {"type": "success", "content": "正在恢复生产..."}}
        return {"toast": {"type": "error", "content": "缺少执行上下文"}}
