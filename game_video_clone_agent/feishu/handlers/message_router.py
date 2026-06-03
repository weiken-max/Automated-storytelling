"""
消息路由器
处理飞书文字消息：关键词快速通道 + LLM 对话兜底
"""
import json
import re
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
import sys
sys.path.insert(0, str(BASE_DIR))

from feishu.config import (
    DEFAULT_SYNOPSIS_DURATION_MINUTES,
    STATUS,
    APPROVE_PHRASES,
    AMBIGUOUS_APPROVE_PHRASES,
    CANCEL_PHRASES,
    REFRESH_PHRASES,
    IDEAS_PHRASES,
    HELP_PHRASES,
    STATUS_PHRASES,
    RESET_PHRASES,
    RESTART_PHRASES,
    CHITCHAT_PHRASES,
    BUSY_OR_ERROR_STATES,
    INTERCEPT_WHITELIST,
    STORYBOARD_APPROVE_EXTRAS,
    STORYBOARD_REJECT_PATTERNS,
    HELP_TEXT,
    ERROR_TIPS,
    get_system_prompt,
)


class MessageRouter:
    """文字消息路由（替代旧的 _handle_message_logic_async）"""

    def __init__(self):
        pass

    def route(self, msg: str, open_id: str,
              session, mgr,
              state_getter,           # callable → {"topic": str, "status": str}
              enqueue_job,            # callable
              send_status_card,       # callable
              kill_by_run_id,         # callable
              get_current_run_id,     # callable
              schedule_restart,       # callable
              ideator_module=None,    # ideator 模块引用
              pip_stop_flags=None,    # PIPELINE_STOP_FLAGS dict
              set_status=None,        # callable (status, topic) → 重置状态机
              **pipeline_funcs,       # run_synopsis_setup / run_visual_setup / ...
              ) -> None:
        """
        路由文字消息到合适的处理器。
        返回 None（异步处理，副作用通过 mgr 发消息）。
        """
        msg_clean = msg.strip()
        s = state_getter()
        current_status = s.get("status", STATUS["IDLE"])
        current_topic = s.get("topic", "")

        # ── 1. 状态/进度查询 ──
        if msg_clean in STATUS_PHRASES:
            # 先检查孤儿自愈
            self._try_orphan_recovery(open_id, session, context={
                "enqueue_job": enqueue_job,
                "get_current_run_id": get_current_run_id,
            })
            send_status_card(open_id, current_topic, current_status)
            return

        # ── 2. 切换 Run-ID ──
        m_switch = re.match(r"^/(?:switch)\s+([A-Za-z0-9_\-]+)\s*$", msg_clean, flags=re.IGNORECASE)
        if not m_switch:
            m_switch = re.match(r"^切换\s+([A-Za-z0-9_\-]+)\s*$", msg_clean, flags=re.IGNORECASE)
        if m_switch:
            target_run_id = m_switch.group(1).strip()
            self._handle_switch(open_id, target_run_id, mgr)
            return

        # ── 3. 断点续传指令 ──
        m_retry = re.match(r"^/(?:retry)\s+(step1|step2|step3)\s*$", msg_clean, flags=re.IGNORECASE)
        if not m_retry:
            m_retry = re.match(r"^重试\s+(step1|step2|step3)\s*$", msg_clean, flags=re.IGNORECASE)
        if m_retry:
            step_name = m_retry.group(1).lower()
            retry_fn = pipeline_funcs.get("retry_single_step")
            if retry_fn and callable(retry_fn):
                enqueue_job(open_id, f"断点续传 {step_name}", retry_fn, step_name, open_id)
            else:
                mgr.send_text(
                    open_id, "open_id",
                    "❌ 断点续传未接入后台，请重启 Hub 或联系维护者检查 `retry_single_step` 配置。",
                )
            return

        m_resend_sb = re.match(r"^/(?:resend)\s+storyboard\s*$", msg_clean, flags=re.IGNORECASE)
        if not m_resend_sb:
            m_resend_sb = msg_clean in (
                "补发分镜审核卡",
                "补发分镜卡",
                "推送分镜审核",
                "发分镜审核",
                "补发分镜",
            )
        if m_resend_sb:
            rs_fn = pipeline_funcs.get("resend_storyboard_review_card")
            if rs_fn and callable(rs_fn):
                rs_fn(open_id)
            else:
                mgr.send_text(
                    open_id, "open_id",
                    "❌ 补发分镜未接入后台，请重启 Hub 或升级 `hub.py` 的 `resend_storyboard_review_card` 注入。",
                )
                return

        # ── 3.5 投喂剧本：等待粘贴 ──
        if current_status == STATUS["WAITING_SCRIPT_FEED"]:
            if msg_clean in RESET_PHRASES:
                if set_status:
                    set_status(STATUS["IDLE"], "")
                mgr.send_text(open_id, "open_id", "🔄 已取消投喂，返回空闲。")
                return
            if any(p in msg_clean for p in REFRESH_PHRASES) or any(p in msg_clean for p in IDEAS_PHRASES):
                if set_status:
                    set_status(STATUS["IDLE"], "")
                self._refresh_topics(open_id, ideator_module)
                return
            if len(msg_clean) < 12:
                mgr.send_text(
                    open_id,
                    "open_id",
                    "请粘贴完整一些的剧本或梗概（建议不少于十几个字），或发送「重置」退出投喂模式。",
                )
                return
            run_synopsis_setup = pipeline_funcs.get("run_synopsis_setup")
            if not run_synopsis_setup:
                mgr.send_text(open_id, "open_id", "❌ 大纲管线未接入，请检查 Hub。")
                return
            mgr.send_text(open_id, "open_id", "✅ 收到您的剧本，马上开始润色并生成大纲卡片…")
            raw_text = (msg or "").strip()
            enqueue_job(
                open_id,
                "投喂剧本润色",
                run_synopsis_setup,
                "用户投喂剧本",
                open_id,
                "",
                DEFAULT_SYNOPSIS_DURATION_MINUTES,
                raw_script=raw_text,
            )
            return

        # ── 4. 忙碌态拦截 ──
        if msg_clean == "你好":
            if ideator_module:
                threading.Thread(
                    target=ideator_module.send_welcome_portal,
                    args=(open_id,),
                ).start()
            return

        is_asking_status = msg_clean in CHITCHAT_PHRASES and msg_clean != "你好"
        is_whitelisted = any(w in msg_clean for w in INTERCEPT_WHITELIST)
        is_busy_blocked = current_status in BUSY_OR_ERROR_STATES and not is_whitelisted
        if is_asking_status or is_busy_blocked:
            send_status_card(open_id, current_topic, current_status)
            return

        # ── 5. 帮助 ──
        if msg_clean in HELP_PHRASES:
            mgr.send_text(open_id, "open_id", HELP_TEXT)
            return

        # ── 6. 重置 ──
        if msg_clean in RESET_PHRASES:
            if set_status:
                set_status(STATUS["IDLE"], "")
            mgr.send_text(open_id, "open_id", "🔄 已强行重置后台状态机为【空闲状态/IDLE】，您可以重新开始盲盒流程了。")
            return

        # ── 7. 取消项目 ──
        if any(p in msg_clean for p in CANCEL_PHRASES) and current_status not in ["IDLE", "WAITING_TOPIC", "COMPLETED"]:
            rid = get_current_run_id() or ""
            if pip_stop_flags is not None:
                pip_stop_flags.setdefault(rid, threading.Event()).set()
            killed = kill_by_run_id(rid) if kill_by_run_id and rid else 0
            if set_status:
                set_status(STATUS["IDLE"], "")
            mgr.send_text(open_id, "open_id",
                          f"🗑️ 已取消项目【{current_topic}】并重置系统（终止 {killed} 个进程）。\n发送「换一批」可重新获取主题。")
            return

        # ── 8. 重启 ──
        if msg_clean in RESTART_PHRASES:
            mgr.send_text(open_id, "open_id", "🚀 收到！后台开始冷重启，约 10-20 秒恢复。")
            schedule_restart(open_id, reason="text_command")
            return

        # ── 9. 审批快速通道（审批态下绕开 LLM）──
        if current_status in ["WAITING_SYNOPSIS_APPROVAL", "WAITING_CHARACTER_APPROVAL"]:
            if msg_clean in AMBIGUOUS_APPROVE_PHRASES:
                mgr.send_text(open_id, "open_id",
                              "⚠️ 为避免误触发，请点击卡片按钮确认；或回复「下一步/确认通过」再继续。")
                return

        # 投喂梗概：大纲审批态下直接按修改意见重新润色（不经闲聊 LLM）
        if current_status == STATUS["WAITING_SYNOPSIS_APPROVAL"]:
            tsp = BASE_DIR / "feishu" / "temp_synopsis.json"
            if tsp.exists():
                try:
                    syn_doc = json.loads(tsp.read_text(encoding="utf-8"))
                except Exception:
                    syn_doc = {}
                if syn_doc.get("story_source") == "user_script" and len(msg_clean) >= 6:
                    quick_approve = (
                        msg_clean in APPROVE_PHRASES
                        or any(
                            msg_clean.startswith(p) or msg_clean.endswith(p)
                            for p in ["下一步", "进行下一步", "开始吹", "可以，进", "好了，"]
                        )
                        or (
                            len(msg_clean) <= 10
                            and any(p in msg_clean for p in ["下一步", "进行", "开始吹"])
                        )
                    )
                    if not quick_approve:
                        run_synopsis_setup = pipeline_funcs.get("run_synopsis_setup")
                        if run_synopsis_setup:
                            mgr.send_text(open_id, "open_id", "🔄 收到您的修改意见，正在重新润色大纲…")
                            enqueue_job(
                                open_id,
                                f"润色修订: {current_topic}",
                                run_synopsis_setup,
                                current_topic,
                                open_id,
                                msg_clean,
                                DEFAULT_SYNOPSIS_DURATION_MINUTES,
                            )
                            return

        is_approval = (
            msg_clean in APPROVE_PHRASES
            or any(msg_clean.startswith(p) or msg_clean.endswith(p)
                   for p in ["下一步", "进行下一步", "开始吹", "可以，进", "好了，"])  # pyright: ignore[reportAny]
            or (len(msg_clean) <= 10 and any(p in msg_clean for p in ["下一步", "进行", "开始吹"]))
        )
        if is_approval:
            self._handle_approval(msg_clean, current_status, current_topic, open_id,
                                  enqueue_job, mgr, get_current_run_id)
            return

        # 分镜审批态补充短语
        if current_status == "WAITING_STORYBOARD_APPROVAL":
            if any(p in msg_clean for p in STORYBOARD_APPROVE_EXTRAS):
                mgr.send_text(open_id, "open_id", "✅ 分镜审核通过！开始切分高清 + 视频合成，请耐心等待...")
                enqueue_job(open_id, f"切分高清+合成: {current_topic}",
                            self._noop, current_topic, open_id)  # 实际调用在 confirm_storyboard handler
                return

        # ── 9.5 分镜审批态：提示词修改消息 ──
        if current_status == "WAITING_STORYBOARD_APPROVAL":
            parsed = self._parse_prompt_revision(msg_clean)
            if parsed is not None:
                self._handle_prompt_revision(
                    parsed, open_id, session, mgr,
                    current_topic, enqueue_job, get_current_run_id,
                    pipeline_funcs,
                )
                return

        # 分镜打回快速通道
        batch_rej = self._parse_storyboard_reject(msg_clean)
        if batch_rej is not None:
            if current_status == "WAITING_STORYBOARD_APPROVAL":
                mgr.send_text(open_id, "open_id", f"🔄 收到！正在重新生成第 {batch_rej} 批次宫格图...")
                enqueue_job(open_id, f"重画分镜批次 {batch_rej}: {current_topic}",
                            self._noop, current_topic, open_id, batch_rej)
            else:
                mgr.send_text(open_id, "open_id", "⚠️ 当前不在分镜审核阶段，打回指令无效。")
            return

        # ── 9.6 定妆审批态：角色修改意见（以「· 主角 ·」等前缀触发直接重画）──
        if current_status == "WAITING_CHARACTER_APPROVAL":
            from feishu.config import CHARACTER_REVISION_KEYWORDS
            if any(kw in msg_clean for kw in CHARACTER_REVISION_KEYWORDS):
                parsed = self._parse_character_revision(msg_clean)
                if parsed is not None:
                    self._handle_character_revision(
                        parsed, open_id, session, mgr,
                        current_topic, enqueue_job,
                        pipeline_funcs,
                    )
                    return

        # ── 10. 换一批 / 刷选题 ──
        if any(p in msg_clean for p in REFRESH_PHRASES):
            self._refresh_topics(open_id, ideator_module)
            return

        # ── 11. 主动要选题 ──
        if any(p in msg_clean for p in IDEAS_PHRASES):
            self._refresh_topics(open_id, ideator_module)
            return

        # ── 12. LLM 对话兜底 ──
        self._llm_chat(msg, open_id, current_topic, current_status,
                       enqueue_job, mgr, state_getter,
                       kill_by_run_id, get_current_run_id, pip_stop_flags,
                       set_status, pipeline_funcs)

    # ── 私有辅助方法 ──

    @staticmethod
    def _noop(*args, **kwargs):
        pass

    def _refresh_topics(self, open_id, ideator_module):
        """在独立线程中生成新一批选题"""
        if ideator_module:
            threading.Thread(target=ideator_module.send_morning_topics, args=(open_id,)).start()

    def _parse_storyboard_reject(self, msg_clean: str) -> int | None:
        """解析「打回/重画第 N 批」中的批次号"""
        for pat in STORYBOARD_REJECT_PATTERNS:
            m = re.search(pat, msg_clean)
            if m:
                try:
                    return int(m.group(1))
                except (ValueError, IndexError):
                    continue
        return None

    # ── V3：定妆照修改意见解析与处理 ─────────────────────────────

    @staticmethod
    def _parse_character_revision(msg: str) -> dict | None:
        """
        解析定妆照修改意见消息，返回结构化数据或 None。
        支持三种格式：
          1. 主角：Lang · 主角 · 青年期（youth）...反馈...
          2. 配角：王总 · 配角 · sr_001 ...反馈...
          3. 视觉元素：黑洞 · 视觉元素 · black_hole ...反馈...
        """
        from feishu.config import (
            CHARACTER_REVISION_PROTAGONIST,
            CHARACTER_REVISION_SUPPORTING,
            CHARACTER_REVISION_ELEMENT,
        )
        msg_clean = msg.strip()

        # 1. 主角
        m = CHARACTER_REVISION_PROTAGONIST.match(msg_clean)
        if m:
            return {
                "type": "protagonist",
                "name_en": m.group(1).strip(),
                "stage_name_cn": m.group(2).strip(),
                "stage_key": m.group(3).strip(),
                "feedback": m.group(4).strip(),
            }

        # 2. 配角
        m = CHARACTER_REVISION_SUPPORTING.match(msg_clean)
        if m:
            return {
                "type": "supporting",
                "name_en": m.group(1).strip(),
                "role_id": m.group(2).strip(),
                "feedback": m.group(3).strip(),
            }

        # 3. 视觉元素（科普模式）
        m = CHARACTER_REVISION_ELEMENT.match(msg_clean)
        if m:
            return {
                "type": "element",
                "name_en": m.group(1).strip(),
                "element_key": m.group(2).strip(),
                "feedback": m.group(3).strip(),
            }

        return None

    @staticmethod
    def _handle_character_revision(
        parsed: dict,
        open_id: str,
        session,
        mgr,
        topic: str,
        enqueue_job,
        pipeline_funcs: dict,
    ):
        """处理定妆照修改意见：直接入队重画（无中间文本审查），完成后推送新卡片。"""
        rev_type = parsed["type"]
        feedback = parsed["feedback"]
        run_visual_setup = pipeline_funcs.get("run_visual_setup")
        if not run_visual_setup:
            mgr.send_text(open_id, "open_id", "❌ 系统未就绪，请稍后重试。")
            return

        if rev_type == "protagonist":
            stage_key = parsed["stage_key"]
            stage_name = parsed.get("stage_name_cn", stage_key)
            mgr.send_text(
                open_id, "open_id",
                f"🔄 收到！正在根据「{feedback}」重新生成{stage_name}定妆照，请稍候..."
            )
            enqueue_job(
                open_id, f"重画定妆照 {stage_key}: {topic}",
                run_visual_setup,
                topic, open_id,
                regen_stage=stage_key, feedback=feedback,
            )

        elif rev_type == "supporting":
            role_id = parsed["role_id"]
            name = parsed.get("name_en", role_id)
            mgr.send_text(
                open_id, "open_id",
                f"🔄 收到！正在根据「{feedback}」重新生成配角{name}的定妆照，请稍候..."
            )
            enqueue_job(
                open_id, f"重画配角定妆照 {role_id}: {topic}",
                run_visual_setup,
                topic, open_id,
                regen_supporting_role_id=role_id, feedback=feedback,
            )

        elif rev_type == "element":
            element_key = parsed["element_key"]
            name = parsed.get("name_en", element_key)
            mgr.send_text(
                open_id, "open_id",
                f"🔄 收到！正在根据「{feedback}」重新生成视觉元素{name}，请稍候..."
            )
            enqueue_job(
                open_id, f"重画视觉元素 {element_key}: {topic}",
                run_visual_setup,
                topic, open_id,
                regen_element_key=element_key, feedback=feedback,
            )

    def _handle_approval(self, msg_clean, current_status, current_topic, open_id,
                         enqueue_job, mgr, get_run_id):
        """审批快速通道"""
        if current_status == "WAITING_SYNOPSIS_APPROVAL":
            if (BASE_DIR / "feishu" / "temp_synopsis.json").exists():
                mgr.send_text(open_id, "open_id", "✅ 收到！大纲已确认，正在启动定妆照生成流程...")
            else:
                mgr.send_text(open_id, "open_id", "⚠️ 无待审批的剧情数据，请先运行选题或重置。")
        elif current_status == "WAITING_CHARACTER_APPROVAL":
            mgr.send_text(open_id, "open_id", "✅ 定妆照已确认！开始推入剧本生产流水线！")
        elif current_status == "WAITING_STORYBOARD_APPROVAL":
            mgr.send_text(open_id, "open_id", "✅ 分镜审核通过！开始切分高清 + 视频合成，请耐心等待...")

    def _handle_switch(self, open_id, target_run_id, mgr):
        """切换 Run-ID"""
        try:
            from feishu.hub import switch_active_run
            ok, reason = switch_active_run(target_run_id)
            if ok:
                mgr.send_text(open_id, "open_id",
                              f"✅ 已切换至历史工作区：{target_run_id}。\n接下来执行的任何单步操作，都将基于此批次的数据覆盖运行。")
            else:
                mgr.send_text(open_id, "open_id", f"❌ 切换失败：{reason}")
        except Exception as e:
            mgr.send_text(open_id, "open_id", f"❌ 切换异常：{e}")

    def _try_orphan_recovery(self, open_id, session, context):
        """尝试孤儿自愈（从 hub 导入函数执行）"""
        try:
            from feishu.hub import _step3_orphan_recovery_needed, _recover_step3_if_orphaned
            need, _, _ = _step3_orphan_recovery_needed()
            if need:
                threading.Thread(
                    target=_recover_step3_if_orphaned,
                    args=(open_id,),
                    kwargs={"wait_for_lock": True},
                    daemon=True,
                ).start()
        except Exception:
            pass

    def _llm_chat(self, msg, open_id, current_topic, current_status,
                  enqueue_job, mgr, state_getter,
                  kill_by_run_id, get_current_run_id, pip_stop_flags,
                  set_status, pipeline_funcs):
        """LLM 对话兜底（聊天 + TRIGGER 指令解析）"""
        try:
            from openai import OpenAI
            from src.api_audit import PHASE_FEISHU_BOT, log_llm_chat
            from src.style_config import LLM_API_KEY, LLM_BASE_URL, MODEL_LLM

            client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
            system_prompt = get_system_prompt(current_status, current_topic)

            # 简易内存对话历史（不再使用 hub.py 的全局 CHAT_HISTORY）
            messages = [{"role": "system", "content": system_prompt},
                        {"role": "user", "content": msg}]

            completion = log_llm_chat(
                PHASE_FEISHU_BOT,
                "message_router_chat",
                MODEL_LLM,
                lambda m=messages: client.chat.completions.create(
                    model=MODEL_LLM,
                    messages=m,
                    temperature=0.8,
                ),
            )
            chat_reply = completion.choices[0].message.content.strip()

            # 清理并发送回复
            clean_reply = re.sub(r"\[TRIGGER_.*?\]", "", chat_reply).strip()
            if clean_reply:
                mgr.send_text(open_id, "open_id", clean_reply)

            # 解析 TRIGGER 指令（兼容旧逻辑）
            self._dispatch_trigger(chat_reply, open_id, current_status, current_topic,
                                   enqueue_job, mgr, state_getter,
                                   kill_by_run_id, get_current_run_id, pip_stop_flags,
                                   set_status, pipeline_funcs)

        except Exception as e:
            import traceback
            traceback.print_exc()
            s = ERROR_TIPS.get(current_status, "可以发送「状态」查看当前进度。")
            mgr.send_text(open_id, "open_id",
                          f"🚨 大脑连线失败，请检查网络或 API Key: {e}\n\n▶️ {s}")

    def _dispatch_trigger(self, chat_reply, open_id, current_status, current_topic,
                          enqueue_job, mgr, state_getter,
                          kill_by_run_id, get_current_run_id, pip_stop_flags,
                          set_status, pipeline_funcs):
        """解析 LLM 返回的 [TRIGGER_XXX] 指令（完整版，兼容旧 hub_old.py 全部触发器）"""

        run_synopsis_setup = pipeline_funcs.get("run_synopsis_setup")
        run_visual_setup = pipeline_funcs.get("run_visual_setup")
        run_project_pipeline = pipeline_funcs.get("run_project_pipeline")
        continue_after_storyboard_approval = pipeline_funcs.get("continue_after_storyboard_approval")
        regenerate_storyboard_batch = pipeline_funcs.get("regenerate_storyboard_batch")

        # ── 忙碌态检查（启动新项目前必须确认空闲）──
        def _check_busy() -> bool:
            s2 = state_getter() if state_getter else {}
            st = s2.get("status", "IDLE")
            if st not in ["IDLE", "WAITING_TOPIC", "COMPLETED"]:
                mgr.send_text(
                    open_id, "open_id",
                    f"🚫 **系统正在专心处理上一个项目！**\n🔖 **在建任务**：【{s2.get('topic', '')}】\n⚠️ 必须等它完成，或发送【取消】、【重置】指令终止它后，才能开启新项目。"
                )
                return True
            return False

        # ── TRIGGER_STOP：紧急叫停当前批次 ──
        if "[TRIGGER_STOP]" in chat_reply:
            rid = get_current_run_id() or "" if get_current_run_id else ""
            if pip_stop_flags is not None and rid:
                pip_stop_flags.setdefault(rid, threading.Event()).set()
            killed = kill_by_run_id(rid) if kill_by_run_id and rid else 0
            if set_status:
                set_status(STATUS["IDLE"], "")
            mgr.send_text(open_id, "open_id",
                          f"🎬 收到！已为您紧急叫停当前批次生产线（精准终止 {killed} 个进程）。")

        # ── TRIGGER_IDEAS：换一批选题 ──
        elif "[TRIGGER_IDEAS]" in chat_reply:
            import ideator
            threading.Thread(target=ideator.send_morning_topics, args=(open_id,)).start()

        # ── TRIGGER_START：立项并开始生成大纲（最关键的修复！）──
        elif "[TRIGGER_START:" in chat_reply:
            if _check_busy():
                return
            m = re.search(r"\[TRIGGER_START: (.*?),\s*([\d\.]+)\]", chat_reply)
            if m:
                topic = m.group(1).strip()
                duration = float(m.group(2).strip())
            else:
                m2 = re.search(r"\[TRIGGER_START: (.*?)\]", chat_reply)
                topic = m2.group(1).strip() if m2 else ""
                duration = DEFAULT_SYNOPSIS_DURATION_MINUTES
            if topic and run_synopsis_setup:
                mgr.send_text(open_id, "open_id",
                              f"✅ 立项动作激活：【{topic}】\n📍 生产时长：{duration} 分钟\n正在为您秘密开启这个人生副本...")
                enqueue_job(open_id, f"立项生成大纲: {topic}",
                            run_synopsis_setup, topic, open_id, "", duration)

        # ── TRIGGER_APPROVE_SYNOPSIS：大纲通过，开始生图 ──
        elif "[TRIGGER_APPROVE_SYNOPSIS]" in chat_reply:
            if current_status in ["WAITING_SYNOPSIS_APPROVAL", "ERROR", "IDLE",
                                   "GENERATING_SYNOPSIS", "GENERATING_VISUALS"]:
                if (BASE_DIR / "feishu" / "temp_synopsis.json").exists() and run_visual_setup:
                    from feishu.synopsis_duration_sync import sync_synopsis_duration_from_draft

                    top = (current_topic or "").strip()
                    if top:
                        sync_synopsis_duration_from_draft(open_id, top)
                    mgr.send_text(open_id, "open_id", "✅ 大纲已确认！正在启动定妆照生成流程...")
                    enqueue_job(open_id, f"生成定妆照: {current_topic}",
                                run_visual_setup, current_topic, open_id)
                else:
                    mgr.send_text(open_id, "open_id", "⚠️ 无待审批的剧情数据，请先下发盲盒选题。")

        # ── TRIGGER_REVISE_SYNOPSIS：大纲打回修改 ──
        elif "[TRIGGER_REVISE_SYNOPSIS:" in chat_reply:
            m = re.search(r"\[TRIGGER_REVISE_SYNOPSIS: (.*?)\]", chat_reply)
            if m and run_synopsis_setup:
                feedback = m.group(1).strip()
                enqueue_job(open_id, f"重写大纲: {current_topic}",
                            run_synopsis_setup, current_topic, open_id, feedback)

        # ── TRIGGER_APPROVE_CHARACTER：定妆通过，推入全量生产 ──
        elif "[TRIGGER_APPROVE_CHARACTER]" in chat_reply:
            if current_status == "WAITING_CHARACTER_APPROVAL" and run_project_pipeline:
                mgr.send_text(open_id, "open_id", "✅ 定妆照通过！开始推入全量生产流水线！")
                enqueue_job(open_id, f"全量生产: {current_topic}",
                            run_project_pipeline, current_topic, open_id)

        # ── TRIGGER_REGEN_CHARACTER：定妆打回重画 ──
        elif "[TRIGGER_REGEN_CHARACTER:" in chat_reply:
            m = re.search(r"\[TRIGGER_REGEN_CHARACTER: (.*?)\]", chat_reply)
            if m and run_visual_setup:
                stage_req = m.group(1).strip()
                STAGE_ALIAS_MAP = {"old": "elderly", "child": "child", "middle": "middle", "elderly": "elderly"}
                stage = STAGE_ALIAS_MAP.get(stage_req, stage_req)
                enqueue_job(open_id, f"重画阶段 {stage}: {current_topic}",
                            run_visual_setup, current_topic, open_id, stage)

        # ── TRIGGER_APPROVE_STORYBOARDS：分镜全部通过 ──
        elif "[TRIGGER_APPROVE_STORYBOARDS]" in chat_reply:
            if current_status == "WAITING_STORYBOARD_APPROVAL" and continue_after_storyboard_approval:
                mgr.send_text(open_id, "open_id", "✅ 分镜审核通过！开始切分高清 + 视频合成，请耐心等待...")
                enqueue_job(open_id, f"切分高清+合成: {current_topic}",
                            continue_after_storyboard_approval, current_topic, open_id)

        # ── TRIGGER_REJECT_STORYBOARD：打回指定批次 ──
        elif "[TRIGGER_REJECT_STORYBOARD:" in chat_reply:
            m = re.search(r"\[TRIGGER_REJECT_STORYBOARD:\s*(\d+)\s*\]", chat_reply)
            if m and current_status == "WAITING_STORYBOARD_APPROVAL" and regenerate_storyboard_batch:
                bi = int(m.group(1))
                mgr.send_text(open_id, "open_id", f"🔄 收到，正在重新生成第 {bi} 批次宫格图...")
                enqueue_job(open_id, f"重画分镜批次 {bi}: {current_topic}",
                            regenerate_storyboard_batch, current_topic, open_id, bi)

    # ── V2：提示词修改辅助方法 ─────────────────────────────────────

    @staticmethod
    def _parse_prompt_revision(msg: str) -> dict | None:
        """解析提示词修改消息，返回结构化数据或 None"""
        from feishu.pipeline.prompt_ops import parse_revision_message
        return parse_revision_message(msg)

    @staticmethod
    def _handle_prompt_revision(
        parsed: dict,
        open_id: str,
        session,
        mgr,
        topic: str,
        enqueue_job,
        get_current_run_id,
        pipeline_funcs: dict,
    ):
        """处理提示词修改消息：秒回确认 → 后台 LLM 改写 → 暂存 → 刷新卡片"""
        batch_index = parsed["batch"]
        rev_type = parsed["type"]
        subshots = parsed.get("subshots", [])
        feedback = parsed.get("feedback", "")

        run_id = get_current_run_id() if get_current_run_id else ""
        session_id = session.session_id
        card_builder = pipeline_funcs.get("build_storyboard_card")

        # 秒回确认，避免消息回调超时
        mgr.send_text(
            open_id, "open_id",
            f"🔍 正在分析批次 {batch_index} 的修改意见...",
        )

        # 后台线程执行 LLM 调用
        def _work():
            from feishu.pipeline.prompt_ops import (
                load_narrative_final,
                get_batch_prompts,
                revise_single_prompt,
                revise_batch_prompts,
            )
            from feishu.session import Session, SessionStore

            store = SessionStore()

            try:
                narrative = load_narrative_final(run_id)
            except Exception as e:
                mgr.send_text(open_id, "open_id", f"❌ 加载提示词失败：{e}")
                return

            batch_prompts = get_batch_prompts(narrative, batch_index)

            # 重新加载 session（避免与主线程冲突）
            session_dict = store.get_session(session_id)
            if not session_dict:
                mgr.send_text(open_id, "open_id", "⚠️ 会话已失效，请重新操作。")
                return
            work_session = Session.from_dict(session_dict)

            # 确保 card_id 可用（从 holder 文件恢复，以支持 PATCH 刷新卡片）
            if not work_session.card_id:
                try:
                    holder_file = Path(__file__).resolve().parent.parent / "storyboard_card_holder.json"
                    if holder_file.exists():
                        holder = json.loads(holder_file.read_text(encoding="utf-8"))
                        mid = holder.get("message_id")
                        if mid:
                            work_session.card_id = mid
                            work_session.card_type = "storyboard"
                except Exception:
                    pass

            # 获取该批次已有的修改暂存
            revised = work_session.get_context(f"revised_prompts_batch_{batch_index}") or {}
            revised = dict(revised)

            changed_count = 0
            error_msg = ""

            if rev_type == "single" and subshots:
                sid = subshots[0]
                original_en = revised.get(sid) or batch_prompts.get(sid, "")
                if not original_en:
                    error_msg = f"❌ 未找到 {sid} 的提示词"
                else:
                    new_prompt = revise_single_prompt(original_en, feedback, sid)
                    revised[sid] = new_prompt
                    changed_count = 1

            elif rev_type == "batch" and subshots:
                for sid in subshots:
                    original_en = revised.get(sid) or batch_prompts.get(sid, "")
                    if not original_en:
                        continue
                    per_feedback = f"{sid} {feedback}"
                    new_prompt = revise_single_prompt(original_en, per_feedback, sid)
                    revised[sid] = new_prompt
                    changed_count += 1

            elif rev_type == "full":
                review_prompts = {}
                for sid in batch_prompts:
                    review_prompts[sid] = revised.get(sid) or batch_prompts[sid]
                batch_revised = revise_batch_prompts(review_prompts, feedback)
                for sid, new_prompt in batch_revised.items():
                    revised[sid] = new_prompt
                changed_count = len(batch_revised)

            else:
                error_msg = "⚠️ 无法识别修改格式，请参考卡片上的模板。"

            if error_msg:
                mgr.send_text(open_id, "open_id", error_msg)
                return

            if changed_count == 0:
                mgr.send_text(open_id, "open_id", "⚠️ 未找到需要修改的提示词。")
                return

            # 暂存修改
            work_session.set_context(f"revised_prompts_batch_{batch_index}", revised)

            # 直接用英文提示词展示（无需翻译）
            en_prompts = {}
            for sid, orig_en in batch_prompts.items():
                en_prompts[sid] = revised.get(sid, orig_en)

            all_translated = work_session.get_context("translated_prompts") or {}
            all_translated[str(batch_index)] = en_prompts
            work_session.set_context("translated_prompts", all_translated)

            # 持久化到 DB
            store.save_context_json(session_id, work_session.context_json)

            # PATCH 刷新分镜卡片
            if card_builder:
                card = card_builder(work_session, mgr, for_patch=True)
                card.send_or_patch()

            mgr.send_text(
                open_id, "open_id",
                f"✅ 已根据您的意见改写批次 {batch_index} 的 {changed_count} 条提示词。\n"
                "请查看卡片确认，满意后点击「打回批次（使用修改后提示词重画）」。"
            )

        threading.Thread(target=_work, daemon=True).start()
