"""
飞书 AI 监制机器人 · 主入口（重构版）
精简架构：Session → Cards → Handlers → Pipeline → Feishu
"""
import os
import sys
import json
import time
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "feishu"))

# ── 新架构模块 ──
from feishu.session import Session, SessionStore
from feishu.cards import CardFactory
from feishu.handlers import ActionRegistry
from feishu.handlers.message_router import MessageRouter
from feishu.pipeline import PipelineBridge

# ── 飞书 SDK ──
import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTrigger,
    P2CardActionTriggerResponse,
)

# ── 全局服务 ──
from feishu.feishu_mgr import FeishuManager

# ================================================================
# 初始化
# ================================================================
def _load_env(path=".env.feishu"):
    env = {}
    with open(BASE_DIR / path, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                key, val = line.strip().split("=", 1)
                env[key] = val
    return env


env_vars = _load_env()
mgr = FeishuManager(env_vars["FEISHU_APP_ID"], env_vars["FEISHU_APP_SECRET"])
store = SessionStore()
bridge = PipelineBridge()
router = MessageRouter()

PID_FILE = BASE_DIR / "feishu" / "hub.pid"

# 消息去重
PROCESSED_MSG_IDS: dict[str, bool] = {}


# ================================================================
# 构建 Action 上下文（提供给按钮处理器）
# ================================================================
def _make_action_context():
    return {
        "enqueue_job":                   bridge.enqueue_job,
        "run_project_pipeline":          bridge.run_project_pipeline,
        "run_synopsis_setup":            bridge.run_synopsis_setup,
        "run_visual_setup":              bridge.run_visual_setup,
        "retry_single_step":             bridge.retry_single_step,
        "run_storyboard_review":         bridge.run_storyboard_review,
        "regenerate_storyboard_batch":   bridge.regenerate_storyboard_batch,
        "continue_after_storyboard_approval": bridge.continue_after_storyboard_approval,
        "try_skip_step2_grid_to_review": bridge.try_skip_step2_grid_to_review,
        "send_status_card":              bridge.send_status_card,
        "get_current_run_id":            bridge.get_current_run_id,
        "get_current_state":            bridge.get_current_state,
        "load_last_error_context":       bridge.load_last_error_context,
        "set_status":                    bridge.set_status,
        "kill_by_run_id":                bridge.kill_by_run_id,
        "PIPELINE_STOP_FLAGS":           bridge.PIPELINE_STOP_FLAGS,
        "schedule_self_restart_notice":  bridge.schedule_self_restart_notice,
        "switch_active_run":             bridge.switch_active_run,
    }


# ================================================================
# 卡片按钮处理器
# ================================================================
def _normalize_action_value(raw_val):
    """容错解析卡片 action.value"""
    if raw_val is None:
        return {}
    if isinstance(raw_val, dict):
        return raw_val
    if isinstance(raw_val, str):
        try:
            val = json.loads(raw_val)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}
    return {}


def do_card_action(data: P2CardActionTrigger) -> P2CardActionTriggerResponse:
    """处理卡片按钮点击"""
    try:
        open_id = data.event.operator.open_id
        action_val = _normalize_action_value(data.event.action.value)
        action_type = action_val.get("action_type", "")
        topic = action_val.get("topic", "")

        # 获取或创建 Session
        session_dict = store.get_active_session(open_id)
        if not session_dict:
            # 首次交互或历史已清理：创建新 Session
            session_dict = store.create_session(open_id, topic, bridge.get_current_state().get("status", "IDLE"))
        session = Session.from_dict(session_dict)

        # 记录交互
        _remember_operator_open_id(open_id)

        # 分发
        ctx = _make_action_context()
        result = ActionRegistry.dispatch(action_type, session, action_val, mgr, **ctx)

        # 持久化状态变更（以 state_mgr 的实际状态为准，同步 session）
        real_state = bridge.get_current_state()
        session.status = real_state.get("status", session.status)
        session.topic = real_state.get("topic", session.topic)
        store.update_status(session.session_id, session.status, session.topic)
        if session.card_id:
            store.update_card_id(session.session_id, session.card_id, getattr(session, "card_type", ""))

        return P2CardActionTriggerResponse(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return P2CardActionTriggerResponse({
            "toast": {"type": "error", "content": f"处理失败: {e}"}
        })


# ================================================================
# 文字消息处理器
# ================================================================
def do_message_receive(data: P2ImMessageReceiveV1) -> None:
    """处理常规聊天消息"""
    msg_id = data.event.message.message_id

    # 去重
    if msg_id in PROCESSED_MSG_IDS:
        return
    PROCESSED_MSG_IDS[msg_id] = True
    if len(PROCESSED_MSG_IDS) > 2000:
        for k in list(PROCESSED_MSG_IDS.keys())[:1000]:
            del PROCESSED_MSG_IDS[k]

    # 异步处理（秒回飞书）
    threading.Thread(target=_handle_message_async, args=(data,), daemon=True).start()


def _handle_message_async(data):
    """异步消息处理"""
    open_id = data.event.sender.sender_id.open_id
    msg_raw = data.event.message.content
    try:
        parsed = json.loads(msg_raw)
        msg = parsed.get("text", "")
        if not msg:
            msg = str(parsed)
    except Exception:
        msg = msg_raw

    # 获取或创建 Session
    session_dict = store.get_active_session(open_id)
    if not session_dict:
        session_dict = store.create_session(open_id)
    session = Session.from_dict(session_dict)

    # 路由消息
    try:
        import ideator as _ideator
    except ImportError:
        _ideator = None

    router.route(
        msg, open_id, session, mgr,
        state_getter=lambda: bridge.get_current_state(),
        enqueue_job=bridge.enqueue_job,
        send_status_card=bridge.send_status_card,
        kill_by_run_id=bridge.kill_by_run_id,
        get_current_run_id=bridge.get_current_run_id,
        schedule_restart=bridge.schedule_self_restart_notice,
        ideator_module=_ideator,
        pip_stop_flags=bridge.PIPELINE_STOP_FLAGS,
        set_status=bridge.set_status,
        run_synopsis_setup=bridge.run_synopsis_setup,
        run_visual_setup=bridge.run_visual_setup,
        run_project_pipeline=bridge.run_project_pipeline,
        continue_after_storyboard_approval=bridge.continue_after_storyboard_approval,
        regenerate_storyboard_batch=bridge.regenerate_storyboard_batch,
        retry_single_step=bridge.retry_single_step,
        resend_storyboard_review_card=bridge.resend_storyboard_review_card,
    )

    # 持久化状态（以 state_mgr 的实际状态为准，同步 session）
    real_state = bridge.get_current_state()
    session.status = real_state.get("status", session.status)
    session.topic = real_state.get("topic", session.topic)
    store.update_status(session.session_id, session.status, session.topic)


# ================================================================
# 运维辅助
# ================================================================
LAST_OPERATOR_OPEN_ID_FILE = BASE_DIR / "feishu" / "last_operator_open_id.json"


def _remember_operator_open_id(open_id: str) -> None:
    oid = (open_id or "").strip()
    if not oid:
        return
    try:
        LAST_OPERATOR_OPEN_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        LAST_OPERATOR_OPEN_ID_FILE.write_text(
            json.dumps({"open_id": oid, "ts": time.time()}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def _load_last_operator() -> str:
    try:
        if LAST_OPERATOR_OPEN_ID_FILE.exists():
            return json.loads(LAST_OPERATOR_OPEN_ID_FILE.read_text(encoding="utf-8")).get("open_id", "").strip()
    except Exception:
        pass
    return ""


# ================================================================
# 启动总线
# ================================================================
event_handler = lark.EventDispatcherHandler.builder("", "") \
    .register_p2_card_action_trigger(do_card_action) \
    .register_p2_im_message_receive_v1(do_message_receive) \
    .build()

cli = lark.ws.Client(
    app_id=env_vars["FEISHU_APP_ID"],
    app_secret=env_vars["FEISHU_APP_SECRET"],
    event_handler=event_handler,
    log_level=lark.LogLevel.INFO,
)

if __name__ == "__main__":
    # 写入 PID
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    # 发送重启回执
    bridge.flush_pending_restart_notice()

    # 启动恢复检测
    def _startup_recovery():
        time.sleep(12)
        try:
            # 孤儿自愈
            need, _, _ = bridge._step3_orphan_recovery_needed()
            if need:
                print("[HUB] 检测到孤儿 Step3，自动补跑...")
                bridge._recover_step3_if_orphaned(None)
        except Exception as ex:
            print(f"[HUB] 启动恢复异常: {ex}")

        # 推送未完成项目提醒
        try:
            should, info = bridge._should_offer_resume_after_reconnect()
            if should:
                oid = _load_last_operator()
                if oid:
                    bridge.send_resume_prompt_card(oid, info)
        except Exception as ex:
            print(f"[HUB] 恢复提醒推送异常: {ex}")

    threading.Thread(target=_startup_recovery, daemon=True).start()

    # 启动飞书连接
    while True:
        try:
            ts = time.strftime('%Y-%m-%d %H:%M:%S')
            sys.stdout.buffer.write(f"[{ts}] [START] Connected to Feishu\n".encode('utf-8'))
            sys.stdout.buffer.flush()
            cli.start()
        except Exception as e:
            ts = time.strftime('%Y-%m-%d %H:%M:%S')
            sys.stdout.buffer.write(f"[{ts}] [RECONNECT] {e}, retrying in 10s...\n".encode('utf-8'))
            sys.stdout.buffer.flush()
            time.sleep(10)
