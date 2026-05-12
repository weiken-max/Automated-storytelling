"""
管线桥接模块
包装旧 hub.py 中的核心生产函数，为新的薄入口提供统一接口。

过渡策略：
- 当前阶段：从 feishu.hub 导入（旧文件仍在）
- 切换后：从 feishu.hub_old 导入（旧文件已改名）
- 未来的理想状态：所有函数直接实现在 pipeline/ 下
"""
import sys
import os
import threading
import time
import json
import queue
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

# 尝试导入旧 hub 模块（先找重命名后的 hub_old，再找未重命名的 hub）
_hub_old = None
for _mod_name in ["feishu.hub_old", "feishu.hub"]:
    try:
        _hub_old = __import__(_mod_name, fromlist=["*"])
        break
    except ImportError:
        continue


class PipelineBridge:
    """
    管线桥接：提供对旧 hub.py 生产函数的访问。
    在完全迁移前，新 hub.py 通过此类调用旧逻辑。
    """

    def __init__(self):
        self._hub = _hub_old
        if self._hub is None:
            raise RuntimeError(
                "无法导入旧 hub 模块。请确保 feishu/hub.py 或 feishu/hub_old.py 存在。"
            )

    # ── 属性代理：暴露旧模块的全局变量 ──

    @property
    def mgr(self):
        return self._hub.mgr

    @property
    def state(self):
        return self._hub.state

    @property
    def TASK_QUEUE(self):
        return self._hub.TASK_QUEUE

    @property
    def PIPELINE_STOP_FLAGS(self):
        return self._hub.PIPELINE_STOP_FLAGS

    @property
    def CURRENT_TASK_INFO(self):
        return self._hub.CURRENT_TASK_INFO

    @property
    def RUN_LOCK(self):
        return self._hub.RUN_LOCK

    @property
    def BASE_DIR(self):
        return self._hub.BASE_DIR

    @property
    def PYTHON_BIN(self):
        return self._hub.PYTHON_BIN

    # ── 核心生产函数 ──

    def run_project_pipeline(self, topic: str, receive_id: str):
        """全自动 Step1→Step2→Step3"""
        return self._hub.run_project_pipeline(topic, receive_id)

    def run_synopsis_setup(self, topic: str, receive_id: str, feedback: str = "", duration: float | None = None, **kwargs):
        """生成大纲并推送审批卡（kwargs 可含 raw_script= 投喂剧本）"""
        if duration is None:
            from feishu.config import DEFAULT_SYNOPSIS_DURATION_MINUTES

            duration = DEFAULT_SYNOPSIS_DURATION_MINUTES
        return self._hub.run_synopsis_setup(topic, receive_id, feedback, duration, **kwargs)

    def run_visual_setup(self, topic: str, receive_id: str, regen_stage: str = None,
                         regen_supporting_role_id: str = None):
        """生成定妆照并推送审批卡"""
        return self._hub.run_visual_setup(topic, receive_id, regen_stage, regen_supporting_role_id)

    def retry_single_step(self, step_name: str, open_id: str):
        """断点续传 Step1/2/3"""
        return self._hub.retry_single_step(step_name, open_id)

    def run_storyboard_review(self, topic: str, receive_id: str):
        """推送分镜审核卡"""
        return self._hub.run_storyboard_review(topic, receive_id)

    def resend_storyboard_review_card(self, open_id: str):
        """宫格已在磁盘但飞书未收到审核卡时，仅补推审核卡（见 hub_old.resend_storyboard_review_card）"""
        return self._hub.resend_storyboard_review_card(open_id)

    def try_skip_step2_grid_to_review(self, topic: str, receive_id: str):
        """错误恢复：已有部分宫格时跳过剩余生图并推送审核卡"""
        return self._hub._try_skip_step2_grid_to_review(topic, receive_id)

    def regenerate_storyboard_batch(self, topic: str, receive_id: str, batch_index: int):
        """单批次重画"""
        return self._hub.regenerate_storyboard_batch(topic, receive_id, batch_index)

    def continue_after_storyboard_approval(self, topic: str, receive_id: str):
        """分镜通过后继续 Step2-B + Step3"""
        return self._hub.continue_after_storyboard_approval(topic, receive_id)

    # ── 队列管理 ──

    def enqueue_job(self, open_id: str, description: str, fn, *args,
                    send_ack: bool = True, **kwargs):
        """入队任务"""
        return self._hub.enqueue_job(open_id, description, fn, *args,
                                      send_ack=send_ack, **kwargs)

    # ── 辅助函数 ──

    def send_status_card(self, open_id, topic, status):
        return self._hub.send_status_card(open_id, topic, status)

    def get_current_run_id(self):
        return self._hub.get_current_run_id() or ""

    def get_current_state(self):
        return self._hub.state.get_current_state()

    def set_status(self, status: str, topic: str = None):
        return self._hub.state.set_status(status, topic)

    def switch_active_run(self, target_run_id: str):
        return self._hub.switch_active_run(target_run_id)

    def kill_by_run_id(self, run_id: str) -> int:
        return self._hub._kill_by_run_id(run_id)

    def save_last_error_context(self, topic, stage, detail):
        return self._hub.save_last_error_context(topic, stage, detail)

    def clear_last_error_context(self):
        return self._hub.clear_last_error_context()

    def load_last_error_context(self) -> dict:
        return self._hub.load_last_error_context()

    def schedule_self_restart_notice(self, open_id: str, reason: str = "manual"):
        return self._hub.schedule_self_restart_notice(open_id, reason)

    def flush_pending_restart_notice(self):
        return self._hub.flush_pending_restart_notice()

    def write_pid(self):
        return self._hub.write_pid()

    def preflight_story_ready(self, expected_topic: str = ""):
        return self._hub.preflight_story_ready(expected_topic)

    def _active_asset_paths(self):
        return self._hub._active_asset_paths()

    def _run_assets_status(self):
        return self._hub._run_assets_status()

    def _step3_orphan_recovery_needed(self):
        return self._hub._step3_orphan_recovery_needed()

    def _recover_step3_if_orphaned(self, open_id, *, wait_for_lock=False):
        return self._hub._recover_step3_if_orphaned(open_id, wait_for_lock=wait_for_lock)

    def generate_progress_bar(self, current: int, total: int, length: int = 20) -> str:
        return self._hub.generate_progress_bar(current, total, length)

    def _build_progress_card(self, topic, run_id, status_text, current, total, detail=""):
        return self._hub._build_progress_card(topic, run_id, status_text, current, total, detail)

    def _send_or_patch_progress_card(self, open_id, card, holder):
        return self._hub._send_or_patch_progress_card(open_id, card, holder)

    def write_pid(self):
        return self._hub.write_pid()

    def flush_pending_restart_notice(self):
        return self._hub.flush_pending_restart_notice()

    def _should_offer_resume_after_reconnect(self):
        return self._hub._should_offer_resume_after_reconnect()

    def send_resume_prompt_card(self, open_id, info):
        return self._hub.send_resume_prompt_card(open_id, info)
