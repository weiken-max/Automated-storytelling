"""
定妆审批相关 Action
"""
import os
import json

class ConfirmCharacterAction:
    """定妆确认通过，开始全量生产"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        topic = data.get("topic", "") or getattr(session, "topic", "")

        enqueue = context.get("enqueue_job")
        run_pipeline = context.get("run_project_pipeline")
        if enqueue and run_pipeline and callable(run_pipeline):
            enqueue(session.open_id, f"全量生产: {topic}", run_pipeline, topic, session.open_id)
            return {"toast": {"type": "success", "content": "收到！开始爆肝生产！"}}
        return {"toast": {"type": "error", "content": "缺少执行上下文"}}
