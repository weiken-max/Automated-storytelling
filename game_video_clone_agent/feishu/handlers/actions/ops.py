"""
运维 Action（状态查看、重试、中止、重启）
"""
import threading

class OpsStatusAction:
    """查看最新进度"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        enqueue = context.get("enqueue_job")
        send_status = context.get("send_status_card")
        open_id = getattr(session, "open_id", "")
        topic = getattr(session, "topic", "暂无")
        status = getattr(session, "status", "IDLE")
        if enqueue and send_status:
            enqueue(open_id, "刷新状态看板", send_status, open_id, topic, status, send_ack=False)
            return {"toast": {"type": "info", "content": "已刷新最新进度。"}}
        return {"toast": {"type": "error", "content": "缺少执行上下文"}}


class OpsRetryStepAction:
    """断点续传 Step 1/2/3"""

    def __init__(self, step: str):
        self.step = step

    def execute(self, session, data: dict, mgr, **context) -> dict:
        enqueue = context.get("enqueue_job")
        retry_fn = context.get("retry_single_step")
        open_id = getattr(session, "open_id", "")
        if enqueue and retry_fn:
            enqueue(open_id, f"断点续传 {self.step}", retry_fn, self.step, open_id, send_ack=False)
            return {"toast": {"type": "success", "content": f"Step {self.step[-1]} 已加入队列。"}}
        return {"toast": {"type": "error", "content": "缺少执行上下文"}}


class OpsAbortRunAction:
    """紧急中止"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        open_id = getattr(session, "open_id", "")
        run_id = data.get("run_id", "").strip() or context.get("get_current_run_id", lambda: "")()
        if not run_id:
            return {"toast": {"type": "error", "content": "未提供可中止的 Run-ID。"}}

        pip_stop = context.get("PIPELINE_STOP_FLAGS", {})
        pip_stop.setdefault(run_id, threading.Event()).set()
        kill_fn = context.get("kill_by_run_id")
        killed = kill_fn(run_id) if kill_fn else 0

        mgr.send_text(open_id, "open_id", f"🛑 已执行紧急中止：{run_id}（终止 {killed} 个进程）。")
        return {"toast": {"type": "warning", "content": f"已中止 {run_id}"}}


class RetryFailedStageAction:
    """从错误态重试（与 hub_old 一致：读 last_error_context.json）"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        open_id = getattr(session, "open_id", "")
        topic = (data.get("topic", "") or "").strip() or getattr(session, "topic", "")
        enqueue = context.get("enqueue_job")
        get_state = context.get("get_current_state")
        load_err = context.get("load_last_error_context")
        run_synopsis = context.get("run_synopsis_setup")
        run_visual = context.get("run_visual_setup")
        run_pipeline = context.get("run_project_pipeline")
        continue_after = context.get("continue_after_storyboard_approval")
        retry_step = context.get("retry_single_step")

        if not enqueue or not get_state or not load_err:
            return {"toast": {"type": "error", "content": "缺少执行上下文"}}

        curr = get_state() or {}
        if curr.get("status") != "ERROR":
            return {"toast": {"type": "warning", "content": "当前不在错误态，无需重试。"}}

        err_ctx = load_err() or {}
        retry_topic = (topic or err_ctx.get("topic") or curr.get("topic", "")).strip()
        failed_stage = (err_ctx.get("failed_stage") or "UNKNOWN").strip()
        if not retry_topic:
            return {"toast": {"type": "error", "content": "缺少项目主题，请重新发起项目。"}}

        if failed_stage in ["GENERATING_SYNOPSIS", "WAITING_SYNOPSIS_APPROVAL"]:
            from feishu.config import DEFAULT_SYNOPSIS_DURATION_MINUTES

            enqueue(
                open_id,
                f"重试大纲: {retry_topic}",
                run_synopsis,
                retry_topic,
                open_id,
                "",
                DEFAULT_SYNOPSIS_DURATION_MINUTES,
            )
        elif failed_stage in ["GENERATING_VISUALS", "WAITING_CHARACTER_APPROVAL"]:
            enqueue(open_id, f"重试定妆照: {retry_topic}", run_visual, retry_topic, open_id)
        elif failed_stage in ["POST_APPROVAL_SLICE", "POST_APPROVAL_STEP3"]:
            enqueue(
                open_id,
                f"重试切分/合成: {retry_topic}",
                continue_after,
                retry_topic,
                open_id,
            )
        elif failed_stage == "STEP1_WRITING" and retry_step and callable(retry_step):
            enqueue(open_id, f"重试 Step1: {retry_topic}", retry_step, "step1", open_id)
        elif failed_stage in ("STEP2_GENERATING", "STEP2_FAILED") and retry_step and callable(retry_step):
            enqueue(open_id, f"重试 Step2: {retry_topic}", retry_step, "step2", open_id)
        elif failed_stage == "STEP3_ASSEMBLING" and retry_step and callable(retry_step):
            enqueue(open_id, f"重试 Step3: {retry_topic}", retry_step, "step3", open_id)
        elif failed_stage in ["STEP1_WRITING", "STEP2_GENERATING", "STEP2_FAILED", "STEP3_ASSEMBLING"]:
            enqueue(open_id, f"重试全量生产: {retry_topic}", run_pipeline, retry_topic, open_id)
        else:
            enqueue(open_id, f"重试全量生产: {retry_topic}", run_pipeline, retry_topic, open_id)

        return {"toast": {"type": "success", "content": f"收到，正在重试（{failed_stage}）…"}}


class SkipTtsDisabledAction:
    """旧卡片「跳过音频」入口已关闭：仅保留 TTS 重试路径。"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        return {
            "toast": {
                "type": "info",
                "content": "「跳过音频」已关闭。请点恢复卡上的「重试 Step1」或运维卡「重跑 Step1」。",
            }
        }


class SkipStageAction:
    """Step2 宫格失败但已有部分宫格时，跳过剩余生图并推送审核卡"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        open_id = getattr(session, "open_id", "")
        topic = (data.get("topic", "") or "").strip() or getattr(session, "topic", "")
        enqueue = context.get("enqueue_job")
        get_state = context.get("get_current_state")
        load_err = context.get("load_last_error_context")
        try_skip = context.get("try_skip_step2_grid_to_review")

        if not enqueue or not get_state or not load_err or not try_skip:
            return {"toast": {"type": "error", "content": "缺少执行上下文"}}

        curr = get_state() or {}
        if curr.get("status") != "ERROR":
            return {"toast": {"type": "warning", "content": "当前不在错误态。"}}

        err_ctx = load_err() or {}
        retry_topic = (topic or err_ctx.get("topic") or curr.get("topic", "")).strip()
        failed_stage = (err_ctx.get("failed_stage") or "").strip()
        if failed_stage not in ("STEP2_GENERATING", "STEP2_FAILED"):
            return {
                "toast": {
                    "type": "warning",
                    "content": "仅适用于 Step2 宫格生图阶段失败，且磁盘上已有部分宫格时。",
                }
            }
        if not retry_topic:
            return {"toast": {"type": "error", "content": "缺少项目主题。"}}

        enqueue(open_id, f"跳过分镜生图(已有宫格): {retry_topic}", try_skip, retry_topic, open_id)
        return {"toast": {"type": "success", "content": "已排队：尝试用现有宫格推送审核卡。"}}
