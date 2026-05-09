"""
Action 注册表（字典分发，替代 hub.py 中 400 行的 if/elif 链）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from feishu.config import ACTION
from feishu.handlers.actions.confirm_synopsis import ConfirmSynopsisAction, RequestReviseSynopsisAction
from feishu.handlers.actions.confirm_character import ConfirmCharacterAction
from feishu.handlers.actions.confirm_storyboard import ConfirmStoryboardAction, RejectStoryboardBatchAction
from feishu.handlers.actions.cancel_project import CancelProjectAction
from feishu.handlers.actions.pause_resume import PauseProjectAction, ResumeProjectAction
from feishu.handlers.actions.refresh_topics import RefreshTopicsAction, RequestIdeasAction
from feishu.handlers.actions.revision import RejectVisualsAction, RegenStageAction, RegenAllVisualsAction, RegenSupportingAction
from feishu.handlers.actions.ops import (
    OpsStatusAction,
    OpsRetryStepAction,
    OpsAbortRunAction,
    RetryFailedStageAction,
    SkipTtsDisabledAction,
    SkipStageAction,
)
from feishu.handlers.actions.duration import SynopsisDurationDeltaAction, SynopsisDurationPresetAction
from feishu.handlers.actions.misc import RestartBackendAction, ConfirmNewProjectAction, ResumeOldProjectAction, StartupResumeDismissAction, DoNothingAction


# action_type → 处理器实例 映射
ACTION_REGISTRY = {
    # 选题与立项
    ACTION["SELECT_TOPIC"]:             None,
    ACTION["REQUEST_IDEAS"]:            RequestIdeasAction(),
    ACTION["REFRESH_TOPICS"]:           RefreshTopicsAction(),
    ACTION["CONFIRM_NEW_PROJECT"]:      ConfirmNewProjectAction(),
    ACTION["RESUME_PROJECT"]:           ResumeOldProjectAction(),
    # 大纲审批
    ACTION["APPROVE_SYNOPSIS"]:         ConfirmSynopsisAction(),
    ACTION["REQUEST_REVISE_SYNOPSIS"]:  RequestReviseSynopsisAction(),
    ACTION["SYNOPSIS_DURATION_DELTA"]:  SynopsisDurationDeltaAction(),
    ACTION["SYNOPSIS_DURATION_PRESET"]: SynopsisDurationPresetAction(),
    # 定妆审批
    ACTION["APPROVE_VISUALS"]:          ConfirmCharacterAction(),
    ACTION["REJECT_VISUALS"]:           RejectVisualsAction(),
    ACTION["REGEN_STAGE"]:              RegenStageAction(),
    ACTION["REGEN_ALL_VISUALS_ONLY"]:   RegenAllVisualsAction(),
    ACTION["REGEN_SUPPORTING"]:         RegenSupportingAction(),
    # 分镜审批
    ACTION["APPROVE_STORYBOARDS"]:      ConfirmStoryboardAction(),
    ACTION["REJECT_STORYBOARD_BATCH"]:  RejectStoryboardBatchAction(),
    # 项目控制
    ACTION["CANCEL_PROJECT"]:           CancelProjectAction(),
    ACTION["PAUSE_PROJECT"]:            PauseProjectAction(),
    ACTION["RESUME_PRODUCTION"]:        ResumeProjectAction(),
    # 运维
    ACTION["OPS_STATUS"]:               OpsStatusAction(),
    ACTION["OPS_RETRY_STEP1"]:          OpsRetryStepAction("step1"),
    ACTION["OPS_RETRY_STEP2"]:          OpsRetryStepAction("step2"),
    ACTION["OPS_RETRY_STEP3"]:          OpsRetryStepAction("step3"),
    ACTION["OPS_ABORT_RUN"]:            OpsAbortRunAction(),
    ACTION["RETRY_FAILED_STAGE"]:       RetryFailedStageAction(),
    ACTION["RETRY_FAILED_STEP"]:         RetryFailedStageAction(),
    ACTION["SKIP_TTS_CONTINUE"]:        SkipTtsDisabledAction(),
    ACTION["SKIP_STAGE"]:               SkipStageAction(),
    ACTION["RESTART_BACKEND"]:          RestartBackendAction(),
    # 启动恢复
    ACTION["STARTUP_RESUME_DISMISS"]:   StartupResumeDismissAction(),
    # 占位
    ACTION["DO_NOTHING"]:               DoNothingAction(),
}


class ActionRegistry:
    """统一分发入口"""

    ACTION_REGISTRY = ACTION_REGISTRY

    @staticmethod
    def dispatch(action_type: str, session, data: dict, mgr, **context) -> dict:
        """
        分发按钮动作。
        返回 toast 响应 dict（兼容飞书 P2CardActionTriggerResponse）。
        """
        action = ACTION_REGISTRY.get(action_type)
        if action is None:
            if action_type == ACTION["SELECT_TOPIC"]:
                return {"toast": {"type": "info", "content": "请通过文字消息选择主题"}}
            return {"toast": {"type": "error", "content": f"未知操作: {action_type}"}}

        try:
            return action.execute(session, data, mgr, **context)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"toast": {"type": "error", "content": f"执行失败: {e}"}}
