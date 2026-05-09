"""
全流程模拟检查脚本
验证重构后的飞书交互系统所有模块是否正常工作
"""
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "feishu"))

passed = 0
failed = 0
warnings = []

def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}  -- {detail}")
        warnings.append(f"{name}: {detail}")

print("=" * 60)
print("飞书交互系统 · 全流程模拟检查")
print("=" * 60)

# ── 1. Config 模块 ────────────────────────
print("\n📦 1. Config 模块")
from feishu.config import (
    STATUS, ACTION, ALLOWED_TRANSITIONS,
    APPROVE_PHRASES, CANCEL_PHRASES, REFRESH_PHRASES,
    STATUS_HUMAN, HELP_TEXT, get_system_prompt, STAGE_ALIAS,
)
check("STATUS 常量已定义", len(STATUS) >= 16, f"当前 {len(STATUS)} 个")
check("ACTION 常量已定义", len(ACTION) >= 25, f"当前 {len(ACTION)} 个")
check("APPROVE_PHRASES 非空", len(APPROVE_PHRASES) > 0)
check("CANCEL_PHRASES 非空", len(CANCEL_PHRASES) > 0)
check("REFRESH_PHRASES 非空", len(REFRESH_PHRASES) > 0)
check("HELP_TEXT 非空", len(HELP_TEXT) > 100)
check("STAGE_ALIAS 包含 old→elderly", STAGE_ALIAS.get("old") == "elderly")

# 状态转移表合法性
invalid = []
for src, targets in ALLOWED_TRANSITIONS.items():
    if src not in STATUS.values():
        invalid.append(f"源状态 '{src}' 不在 STATUS 中")
    for tgt in targets:
        if tgt not in STATUS.values():
            invalid.append(f"目标 '{tgt}' (来自 {src}) 不在 STATUS 中")
check("ALLOWED_TRANSITIONS 全部合法", len(invalid) == 0, "; ".join(invalid[:3]))

# System Prompt 生成
prompt = get_system_prompt("IDLE", "测试主题")
check("get_system_prompt 返回非空", len(prompt) > 50)
check("System prompt 包含主题", "测试主题" in prompt)

# ── 2. Session 模块 ────────────────────────
print("\n📦 2. Session 模块")
from feishu.session import Session, SessionStore

store = SessionStore()

# 创建 Session
rec = store.create_session("test_user_001", "末代铁匠的故事")
check("SessionStore.create_session 返回 dict", isinstance(rec, dict) and "session_id" in rec)

s = Session.from_dict(rec)
check("Session.from_dict 正常", s.session_id == rec["session_id"])
check("Session.topic 正确", s.topic == "末代铁匠的故事")
check("Session.status 初始 IDLE", s.status == STATUS["IDLE"])
check("Session.is_idle()", s.is_idle())

# 状态转移
check("IDLE→GENERATING_SYNOPSIS 合法", s.can_transition_to(STATUS["GENERATING_SYNOPSIS"]))
s.transition_to(STATUS["GENERATING_SYNOPSIS"])
check("转移后 status 正确", s.status == STATUS["GENERATING_SYNOPSIS"])

# 非法转移拦截
try:
    s.transition_to(STATUS["COMPLETED"])
    check("非法转移应被拦截", False, "GENERATING_SYNOPSIS→COMPLETED 不应被允许")
except ValueError:
    check("非法转移被正确拦截", True)

# 恢复到合法路径
s.status = STATUS["WAITING_SYNOPSIS_APPROVAL"]
check("WAITING_SYNOPSIS_APPROVAL→GENERATING_VISUALS", s.can_transition_to(STATUS["GENERATING_VISUALS"]))

# 持久化交互
store.update_status(s.session_id, s.status, s.topic)
check("store.update_status OK", True)
store.update_card_id(s.session_id, "msg_test_123", "synopsis")
check("store.update_card_id OK", True)

s2_dict = store.get_active_session("test_user_001")
check("store.get_active_session 可查询", s2_dict is not None and s2_dict.get("card_id") == "msg_test_123")

# 多用户隔离
rec2 = store.create_session("test_user_002", "煤矿工人的一生")
s_u2_dict = store.get_active_session("test_user_002")
check("多用户隔离（user_002 独立）", s_u2_dict is not None and s_u2_dict.get("topic") == "煤矿工人的一生")
store.delete_session(rec2["session_id"])

# 清理测试数据
store.delete_session(s.session_id)
check("Session 清理成功", store.get_active_session("test_user_001") is None)

# ── 3. Cards 模块 ────────────────────────
print("\n📦 3. Cards 模块")

# 需要一个 mock mgr 来测试卡片构建
from unittest.mock import MagicMock
mock_mgr = MagicMock()
mock_mgr.send_card.return_value = "mock_msg_id_001"
mock_mgr.update_card.return_value = True
mock_mgr.upload_image.return_value = "mock_img_key_001"

# 创建 mock session
mock_session = Session(
    session_id="test_ses_001",
    open_id="test_open_id",
    topic="测试主题",
    status=STATUS["IDLE"],
)

from feishu.cards import (
    IdleCard, SynopsisCard, CharacterCard,
    StoryboardCard, ProgressCard, CardFactory,
)

# IdleCard
idle_card = IdleCard(mock_session, mock_mgr, topics=["煤矿工人的一生", "末代铁匠的故事"])
idle_json = idle_card.build()
check("IdleCard.build() 返回 dict", isinstance(idle_json, dict))
check("IdleCard 有 header", "header" in idle_json)
check("IdleCard 有 elements", len(idle_json.get("elements", [])) > 0)

# SynopsisCard
synopsis_data = {
    "synopsis": "今天你要体验的人生副本是...",
    "era": "1980年代",
    "identity": "煤矿工人",
    "industry_rules": ["规则1", "规则2"],
}
mock_session.status = STATUS["WAITING_SYNOPSIS_APPROVAL"]
syn_card = SynopsisCard(mock_session, mock_mgr, synopsis_data, 360)
syn_json = syn_card.build()
check("SynopsisCard.build() OK", isinstance(syn_json, dict))
check("SynopsisCard 包含大纲文本", any("煤矿工人" in str(e) for e in syn_json.get("elements", [])))

# CharacterCard
mock_session.status = STATUS["WAITING_CHARACTER_APPROVAL"]
char_card = CharacterCard(mock_session, mock_mgr, ref_slots=[])
char_json = char_card.build()
check("CharacterCard.build() OK", isinstance(char_json, dict))

# StoryboardCard
mock_session.status = STATUS["WAITING_STORYBOARD_APPROVAL"]
fake_path = BASE_DIR / "data" / "runs" / "test" / "storyboards" / "grid_batch_001.png"
sb_card = StoryboardCard(mock_session, mock_mgr, grid_files=[fake_path])
sb_json = sb_card.build()
check("StoryboardCard.build() OK", isinstance(sb_json, dict))

# ProgressCard
mock_session.status = STATUS["STEP2_GENERATING"]
prog_card = ProgressCard(mock_session, mock_mgr, status_text="正在生图", current=3, total=8)
prog_json = prog_card.build()
check("ProgressCard.build() OK", isinstance(prog_json, dict))

# CardFactory
mock_session.status = STATUS["IDLE"]
card_cls = CardFactory.get_card_class(STATUS["IDLE"])
check("CardFactory: IDLE→IdleCard", card_cls is IdleCard)
card_cls2 = CardFactory.get_card_class(STATUS["STEP3_ASSEMBLING"])
check("CardFactory: STEP3_ASSEMBLING→ProgressCard", card_cls2 is ProgressCard)

# ── 4. Handlers 模块 ────────────────────────
print("\n📦 4. Handlers 模块")
from feishu.handlers import ActionRegistry

registry = ActionRegistry.ACTION_REGISTRY
total_reg = sum(1 for v in registry.values() if v is not None)
check(f"ActionRegistry: {total_reg} 个处理器已注册", total_reg >= 20)

# 检查关键 action 是否存在
key_actions = [
    "approve_synopsis", "approve_visuals", "approve_storyboards",
    "cancel_project", "reject_storyboard_batch",
    "ops_status", "ops_abort_run",
    "synopsis_duration_delta", "synopsis_duration_preset",
    "regen_stage", "regen_all_visuals_only", "regen_supporting",
]
for ka in key_actions:
    act_key = ACTION.get(ka.upper()) or ka
    check(f"  Action '{ka}' 已注册", act_key in registry, f"key={act_key}")

# 模拟 dispatch（不需要真实执行）
result = ActionRegistry.dispatch(
    "approve_synopsis",
    mock_session,
    {"topic": "测试", "action_type": "approve_synopsis"},
    mock_mgr,
    enqueue_job=lambda *a, **kw: None,
    run_visual_setup=lambda *a, **kw: None,
)
check("dispatch approve_synopsis 返回 dict", isinstance(result, dict))
check("dispatch 返回 toast", "toast" in result)

# 未知 action
result_unknown = ActionRegistry.dispatch("nonexistent_action", mock_session, {}, mock_mgr)
check("dispatch 未知 action 返回错误", "error" in str(result_unknown.get("toast", {}).get("type", "")))

# ── 5. MessageRouter ────────────────────────
print("\n📦 5. MessageRouter 模块")
from feishu.handlers.message_router import MessageRouter

router = MessageRouter()

# 测试关键词匹配（不发送消息）
def mock_state_getter():
    return {"topic": "测试", "status": STATUS["IDLE"]}

def mock_noop(*a, **k): pass

# 只测不会发消息的方法
batch = router._parse_storyboard_reject("打回第 3 批")
check("解析「打回第3批」→ 3", batch == 3)

batch2 = router._parse_storyboard_reject("第 5 批重画")
check("解析「第5批重画」→ 5", batch2 == 5)

batch3 = router._parse_storyboard_reject("你好")
check("解析「你好」→ None（非打回）", batch3 is None)

# ── 6. PipelineBridge ────────────────────────
print("\n📦 6. PipelineBridge 模块")
from feishu.pipeline import PipelineBridge

bridge = PipelineBridge()
check("bridge.mgr 可访问", bridge.mgr is not None)
check("bridge.state 可访问", bridge.state is not None)
check("bridge.TASK_QUEUE 可访问", bridge.TASK_QUEUE is not None)
check("bridge.run_project_pipeline 可调用", callable(bridge.run_project_pipeline))
check("bridge.run_synopsis_setup 可调用", callable(bridge.run_synopsis_setup))
check("bridge.run_visual_setup 可调用", callable(bridge.run_visual_setup))
check("bridge.retry_single_step 可调用", callable(bridge.retry_single_step))
check("bridge.resend_storyboard_review_card 可调用", callable(bridge.resend_storyboard_review_card))
check("bridge.enqueue_job 可调用", callable(bridge.enqueue_job))
check("bridge.send_status_card 可调用", callable(bridge.send_status_card))
check("bridge.kill_by_run_id 可调用", callable(bridge.kill_by_run_id))

# ── 7. 新 hub.py 结构检查 ──────────────────
print("\n📦 7. 新 hub.py 结构检查")
from feishu.hub import (
    store as hub_store,
    bridge as hub_bridge,
    router as hub_router,
    mgr as hub_mgr,
    do_card_action,
    do_message_receive,
    event_handler,
)

check("新 hub.py: store 是 SessionStore", isinstance(hub_store, SessionStore))
check("新 hub.py: bridge 是 PipelineBridge", isinstance(hub_bridge, PipelineBridge))
check("新 hub.py: router 是 MessageRouter", isinstance(hub_router, MessageRouter))
check("新 hub.py: do_card_action 可调用", callable(do_card_action))
check("新 hub.py: do_message_receive 可调用", callable(do_message_receive))
check("新 hub.py: event_handler 已构建", event_handler is not None)

# ── 8. 旧 hub_old.py 备份确认 ──────────────
print("\n📦 8. 旧 hub_old.py 备份确认")
hub_old_path = BASE_DIR / "feishu" / "hub_old.py"
check("hub_old.py 存在（备份）", hub_old_path.exists())
if hub_old_path.exists():
    old_size = hub_old_path.stat().st_size
    check(f"hub_old.py 大小正常 ({old_size:,} bytes)", old_size > 10000)

# ── 9. 端到端模拟：完整审批流程 ──────────────
print("\n📦 9. 端到端流程模拟")

# 模拟从选题到完成的完整状态转移
flow_session = Session(
    session_id="flow_test_001",
    open_id="flow_user",
    topic="模拟测试主题",
)

flow_steps = [
    ("选题", STATUS["IDLE"], STATUS["GENERATING_SYNOPSIS"]),
    ("大纲生成完成", STATUS["GENERATING_SYNOPSIS"], STATUS["WAITING_SYNOPSIS_APPROVAL"]),
    ("用户确认大纲", STATUS["WAITING_SYNOPSIS_APPROVAL"], STATUS["GENERATING_VISUALS"]),
    ("定妆照生成完成", STATUS["GENERATING_VISUALS"], STATUS["WAITING_CHARACTER_APPROVAL"]),
    ("用户确认定妆", STATUS["WAITING_CHARACTER_APPROVAL"], STATUS["STEP1_WRITING"]),
    ("Step1 完成", STATUS["STEP1_WRITING"], STATUS["STEP1_READY"]),
    ("开始 Step2", STATUS["STEP1_READY"], STATUS["STEP2_GENERATING"]),
    ("Step2-A 宫格", STATUS["STEP2_GENERATING"], STATUS["WAITING_STORYBOARD_APPROVAL"]),
    ("用户确认分镜", STATUS["WAITING_STORYBOARD_APPROVAL"], STATUS["STEP2_GENERATING"]),
    ("Step2 完成", STATUS["STEP2_GENERATING"], STATUS["STEP2_SUCCESS"]),
    ("Step3 完成", STATUS["STEP2_SUCCESS"], STATUS["STEP3_ASSEMBLING"]),
    ("交付", STATUS["STEP3_ASSEMBLING"], STATUS["COMPLETED"]),
]

flow_ok = True
for step_name, src, tgt in flow_steps:
    flow_session.status = src
    if not flow_session.can_transition_to(tgt):
        print(f"  ❌ 流程卡在: {step_name} ({src} → {tgt})")
        flow_ok = False
        break
    flow_session.transition_to(tgt)

check("完整审批流程通过", flow_ok)

# 测试暂停恢复
flow_session.status = STATUS["STEP2_GENERATING"]
check("STEP2_GENERATING→PAUSED", flow_session.can_transition_to(STATUS["PAUSED"]))
flow_session.transition_to(STATUS["PAUSED"])
check("PAUSED→STEP2_GENERATING", flow_session.can_transition_to(STATUS["STEP2_GENERATING"]))

# ── 10. 新文件完整性检查 ──────────────────
print("\n📦 10. 新文件完整性检查")
expected_files = [
    "feishu/config.py",
    "feishu/session/__init__.py",
    "feishu/session/session.py",
    "feishu/session/session_store.py",
    "feishu/cards/__init__.py",
    "feishu/cards/base_card.py",
    "feishu/cards/idle_card.py",
    "feishu/cards/synopsis_card.py",
    "feishu/cards/character_card.py",
    "feishu/cards/storyboard_card.py",
    "feishu/cards/progress_card.py",
    "feishu/cards/factory.py",
    "feishu/handlers/__init__.py",
    "feishu/handlers/registry.py",
    "feishu/handlers/message_router.py",
    "feishu/handlers/actions/__init__.py",
    "feishu/handlers/actions/confirm_synopsis.py",
    "feishu/handlers/actions/confirm_character.py",
    "feishu/handlers/actions/confirm_storyboard.py",
    "feishu/handlers/actions/cancel_project.py",
    "feishu/handlers/actions/pause_resume.py",
    "feishu/handlers/actions/refresh_topics.py",
    "feishu/handlers/actions/duration.py",
    "feishu/handlers/actions/revision.py",
    "feishu/handlers/actions/ops.py",
    "feishu/handlers/actions/misc.py",
    "feishu/pipeline/__init__.py",
    "feishu/pipeline/bridge.py",
    "feishu/hub.py",            # 新入口
    "feishu/hub_old.py",        # 旧备份
]
for ef in expected_files:
    fp = BASE_DIR / ef
    check(f"  文件存在: {ef}", fp.exists(), "文件缺失")

# ================================================================
# 总结
# ================================================================
print("\n" + "=" * 60)
print(f"检查完成: ✅ {passed} 项通过, ❌ {failed} 项失败")
if warnings:
    print("\n⚠️ 警告/失败细节:")
    for w in warnings:
        print(f"  - {w}")

if failed == 0:
    print("\n🎉 全流程模拟检查通过！系统重构成功。")
else:
    print(f"\n⚠️ 有 {failed} 项检查未通过，请修复后再启动。")

print("=" * 60)
