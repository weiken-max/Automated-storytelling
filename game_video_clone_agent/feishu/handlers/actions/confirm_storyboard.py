"""
分镜审批相关 Action
"""

class ConfirmStoryboardAction:
    """分镜全部通过，开始裁切高清 + 视频合成"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        topic = data.get("topic", "") or getattr(session, "topic", "")

        enqueue = context.get("enqueue_job")
        continue_fn = context.get("continue_after_storyboard_approval")
        if enqueue and continue_fn and callable(continue_fn):
            enqueue(session.open_id, f"切分高清+合成: {topic}", continue_fn, topic, session.open_id)
            return {"toast": {"type": "success", "content": "审核通过，开始裁切高清与视频合成！"}}
        return {"toast": {"type": "error", "content": "缺少执行上下文"}}


class RejectStoryboardBatchAction:
    """打回指定批次重画"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        topic = data.get("topic", "") or getattr(session, "topic", "")
        try:
            batch_index = int(data.get("batch_index", 0))
        except (TypeError, ValueError):
            return {"toast": {"type": "error", "content": "批次号无效。"}}
        if batch_index < 1:
            return {"toast": {"type": "error", "content": "批次号无效。"}}

        enqueue = context.get("enqueue_job")
        regen_fn = context.get("regenerate_storyboard_batch")
        if enqueue and regen_fn and callable(regen_fn):
            enqueue(
                session.open_id,
                f"重画分镜批次 {batch_index}: {topic}",
                regen_fn, topic, session.open_id, batch_index,
            )
            return {"toast": {"type": "info", "content": f"收到，正在重新生成第 {batch_index} 批次宫格图..."}}
        return {"toast": {"type": "error", "content": "缺少执行上下文"}}
