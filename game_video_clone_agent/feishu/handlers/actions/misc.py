"""
杂项 Action（重启、确认新项目、恢复旧项目、启动恢复关闭）
"""

class RestartBackendAction:
    """强制重启后台"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        open_id = getattr(session, "open_id", "")
        schedule_restart = context.get("schedule_self_restart_notice")
        if schedule_restart:
            schedule_restart(open_id, reason="card_button")
        mgr.send_text(open_id, "open_id", "🔄 已收到重启请求：后台即将重启，约 10-20 秒恢复。")
        return {"toast": {"type": "info", "content": "即将杀死后台进程并冷启动..."}}


class ConfirmNewProjectAction:
    """确认新建项目（放弃旧项目）"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        new_topic = data.get("topic", "")
        open_id = data.get("open_id", "") or getattr(session, "open_id", "")
        run_id = context.get("get_current_run_id", lambda: "")()
        set_status = context.get("set_status")
        kill_fn = context.get("kill_by_run_id")
        enqueue = context.get("enqueue_job")
        run_synopsis = context.get("run_synopsis_setup")

        pip_stop = context.get("PIPELINE_STOP_FLAGS", {})
        pip_stop.setdefault(run_id, threading.Event()).set()
        if kill_fn and run_id:
            kill_fn(run_id)

        if set_status:
            set_status("IDLE", "")

        if new_topic and enqueue and run_synopsis:
            from feishu.config import DEFAULT_SYNOPSIS_DURATION_MINUTES

            enqueue(
                open_id,
                f"新项目大纲: {new_topic}",
                run_synopsis,
                new_topic,
                open_id,
                "",
                DEFAULT_SYNOPSIS_DURATION_MINUTES,
            )

        return {"toast": {"type": "success", "content": f"已放弃旧项目，正在为「{new_topic}」生成大纲..."}}


class ResumeOldProjectAction:
    """继续上一个项目"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        topic = getattr(session, "topic", "")
        open_id = getattr(session, "open_id", "")
        mgr.send_text(open_id, "open_id", f"▶️ 好的，继续推进【{topic}】。发送「状态」可查看当前进度。")
        return {"toast": {"type": "info", "content": "继续上一个项目。"}}


class StartupResumeDismissAction:
    """关闭启动恢复提示"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        return {"toast": {"type": "info", "content": "好的。随时发送「状态」或 /status 可打开运维面板。"}}


class DoNothingAction:
    """占位"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        return {"toast": {"type": "info", "content": "收到，请耐心等待。"}}
