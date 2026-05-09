"""
重写/重画相关 Action
"""
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

class RejectVisualsAction:
    """重写剧本并全部重画"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        topic = data.get("topic", "") or getattr(session, "topic", "")

        # 清空旧素材
        for clean_dir in [
            BASE_DIR / "data" / "storyboards",
            BASE_DIR / "data" / "audio",
            BASE_DIR / "data" / "output",
        ]:
            if clean_dir.exists():
                shutil.rmtree(clean_dir)
            clean_dir.mkdir(parents=True, exist_ok=True)

        enqueue = context.get("enqueue_job")
        run_visual = context.get("run_visual_setup")
        if enqueue and run_visual:
            enqueue(session.open_id, f"重写剧本并重画: {topic}", run_visual, topic, session.open_id)
            return {"toast": {"type": "info", "content": "收到，正在打回重写大纲并全部重画..."}}
        return {"toast": {"type": "error", "content": "缺少执行上下文"}}


class RegenStageAction:
    """单阶段重画"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        topic = data.get("topic", "") or getattr(session, "topic", "")
        stage = data.get("stage", "")

        enqueue = context.get("enqueue_job")
        run_visual = context.get("run_visual_setup")
        if enqueue and run_visual:
            enqueue(session.open_id, f"重画阶段 {stage}: {topic}", run_visual, topic, session.open_id, stage)
            return {"toast": {"type": "info", "content": f"收到，正在单独重画：{stage}"}}
        return {"toast": {"type": "error", "content": "缺少执行上下文"}}


class RegenAllVisualsAction:
    """保留剧本，重画全部"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        topic = data.get("topic", "") or getattr(session, "topic", "")

        enqueue = context.get("enqueue_job")
        run_visual = context.get("run_visual_setup")
        if enqueue and run_visual:
            enqueue(session.open_id, f"重画全部定妆照: {topic}", run_visual, topic, session.open_id, "__all__")
            return {"toast": {"type": "info", "content": "保留剧本，正在重画全部定妆照..."}}
        return {"toast": {"type": "error", "content": "缺少执行上下文"}}


class RegenSupportingAction:
    """重画配角"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        topic = data.get("topic", "") or getattr(session, "topic", "")
        rid = str(data.get("supporting_role_id", "")).strip()
        if not rid:
            return {"toast": {"type": "error", "content": "缺少配角标识。"}}

        enqueue = context.get("enqueue_job")
        run_visual = context.get("run_visual_setup")
        if enqueue and run_visual:
            enqueue(
                session.open_id, f"重画配角 {rid}: {topic}",
                run_visual, topic, session.open_id, None,
                regen_supporting_role_id=rid,
            )
            return {"toast": {"type": "info", "content": f"收到，正在单独重绘配角：{rid}"}}
        return {"toast": {"type": "error", "content": "缺少执行上下文"}}
