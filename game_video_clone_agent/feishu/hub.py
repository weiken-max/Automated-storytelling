import os
import sys
import re
import json
import subprocess
import threading
import time
import psutil
from pathlib import Path
import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from lark_oapi.api.im.v1.model.create_message_request import CreateMessageRequest
from lark_oapi.api.im.v1.model.create_message_request_body import CreateMessageRequestBody
from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTrigger, P2CardActionTriggerResponse

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from feishu_mgr import FeishuManager
from state_mgr import FeishuStateMgr

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# 定义全局路径
FULL_STORY_V6_PATH = BASE_DIR / "data" / "scripts" / "full_story_v6.json"
PID_FILE = BASE_DIR / "feishu" / "hub.pid"
PENDING_RESTART_FILE = BASE_DIR / "feishu" / "pending_restart_open_id.json"
LAST_ERROR_CTX_FILE = BASE_DIR / "feishu" / "last_error_context.json"

def preflight_story_ready(expected_topic: str = ""):
    """生产前置校验：确保剧本存在且与当前主题一致。"""
    if not FULL_STORY_V6_PATH.exists():
        return False, f"前置缺失：未找到剧本文件 {FULL_STORY_V6_PATH}"
    try:
        data = json.loads(FULL_STORY_V6_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"前置缺失：剧本文件不可读 ({e})"

    story_topic = (data.get("metadata", {}) or {}).get("topic", "")
    if expected_topic and story_topic and story_topic != expected_topic:
        return False, f"前置冲突：当前项目是【{expected_topic}】，但剧本是【{story_topic}】"

    narration = (data.get("master_design", {}) or {}).get("full_narration", "")
    if not narration:
        return False, "前置缺失：剧本中没有 full_narration"
    return True, "ok"

def write_pid():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

def schedule_self_restart_notice(open_id: str, reason: str = "manual"):
    """
    两段式重启反馈：
    1) 先记录“待回执 open_id”
    2) 延迟自杀，交给 watchdog 拉起
    """
    try:
        PENDING_RESTART_FILE.write_text(
            json.dumps({"open_id": open_id, "reason": reason, "ts": time.time()}, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception as e:
        print(f"[WARN] 写入重启回执文件失败: {e}")

    def _delayed_exit():
        time.sleep(2.0)
        os._exit(0)

    threading.Thread(target=_delayed_exit, daemon=True).start()

def flush_pending_restart_notice():
    """Hub 重启后，向触发者发送“恢复完成”回执。"""
    if not PENDING_RESTART_FILE.exists():
        return
    try:
        payload = json.loads(PENDING_RESTART_FILE.read_text(encoding="utf-8"))
        open_id = payload.get("open_id")
        reason = payload.get("reason", "manual")
        if open_id:
            mgr.send_text(
                open_id,
                "open_id",
                f"✅ 后台已完成重启并恢复在线（来源：{reason}）。\n您可以发送「状态」继续流程。"
            )
    except Exception as e:
        print(f"[WARN] 发送重启完成回执失败: {e}")
    finally:
        try:
            PENDING_RESTART_FILE.unlink(missing_ok=True)
        except Exception:
            pass

def save_last_error_context(topic: str, stage: str, error_detail: str):
    """记录最近一次失败上下文，供错误卡片重试按钮读取。"""
    try:
        payload = {
            "topic": topic or "",
            "failed_stage": stage or "UNKNOWN",
            "error_detail": (error_detail or "")[-3000:],
            "ts": time.time()
        }
        LAST_ERROR_CTX_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[WARN] 写入失败上下文失败: {e}")

def load_last_error_context() -> dict:
    """读取最近一次失败上下文。"""
    try:
        if LAST_ERROR_CTX_FILE.exists():
            return json.loads(LAST_ERROR_CTX_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] 读取失败上下文失败: {e}")
    return {}

def clear_last_error_context():
    try:
        LAST_ERROR_CTX_FILE.unlink(missing_ok=True)
    except Exception:
        pass

def kill_pipeline_processes():
    """终止所有流水线进程（psutil 优先，降级到 taskkill，彻底替代废弃的 wmic）"""
    keywords = ["_v6.py", "story_planner"]
    try:
        killed = 0
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmd = ' '.join(proc.info.get('cmdline') or [])
                if any(k in cmd for k in keywords) and proc.pid != os.getpid():
                    proc.kill()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        print(f"  [Kill] psutil 已终止 {killed} 个流水线进程")
    except Exception:
        # 降级方案：taskkill（Win10/11 均可用，wmic 的可靠替代）
        for kw in keywords:
            subprocess.run(f'taskkill /F /FI "COMMANDLINE like *{kw}*"',
                           shell=True, capture_output=True)


def load_env(path=".env.feishu"):
    env = {}
    with open(BASE_DIR / path, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                key, val = line.strip().split("=", 1)
                env[key] = val
    return env

env_vars = load_env()
mgr = FeishuManager(env_vars["FEISHU_APP_ID"], env_vars["FEISHU_APP_SECRET"])
state = FeishuStateMgr()

# ================================================================
# 全局对话历史（持久化到 state.db，重启不失忆）
# ================================================================
import sqlite3 as _sqlite3
_CHAT_DB = BASE_DIR / "feishu" / "state.db"
MAX_HISTORY_LEN = 20

def _ensure_chat_table():
    with _sqlite3.connect(_CHAT_DB) as _conn:
        _conn.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                open_id TEXT,
                role    TEXT,
                content TEXT,
                ts      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
_ensure_chat_table()

CHAT_HISTORY: dict = {}  # 内存缓冲，优先从 DB 加载

def _load_history(open_id: str) -> list:
    """从 DB 读取最近 N 条记录（冷启动时调用）"""
    with _sqlite3.connect(_CHAT_DB) as _conn:
        rows = _conn.execute(
            'SELECT role, content FROM chat_history WHERE open_id=? ORDER BY ts DESC LIMIT ?',
            (open_id, MAX_HISTORY_LEN)
        ).fetchall()
    return [{"role": r, "content": c} for r, c in reversed(rows)]

def add_to_history(open_id: str, role: str, content: str):
    """记录对话历史，内存 + DB 双写，重启后 AI 导演不失忆"""
    if open_id not in CHAT_HISTORY:
        CHAT_HISTORY[open_id] = _load_history(open_id)  # 冷启动时从 DB 恢复
    clean_content = content.replace("⬇️ **审批提示：**", "").replace("如果您觉得满意，请回复 `大纲可以`。", "").strip()
    if not clean_content:
        return
    CHAT_HISTORY[open_id].append({"role": role, "content": clean_content})
    if len(CHAT_HISTORY[open_id]) > MAX_HISTORY_LEN:
        CHAT_HISTORY[open_id] = CHAT_HISTORY[open_id][-MAX_HISTORY_LEN:]
    # 异步写 DB（不阻塞消息处理）
    try:
        with _sqlite3.connect(_CHAT_DB) as _conn:
            _conn.execute(
                'INSERT INTO chat_history (open_id, role, content) VALUES (?, ?, ?)',
                (open_id, role, clean_content)
            )
            # 只保留最近 MAX_HISTORY_LEN 条
            _conn.execute('''
                DELETE FROM chat_history WHERE open_id=? AND rowid NOT IN (
                    SELECT rowid FROM chat_history WHERE open_id=?
                    ORDER BY ts DESC LIMIT ?
                )
            ''', (open_id, open_id, MAX_HISTORY_LEN))
    except Exception:
        pass  # DB 写失败不影响正常消息处理


# ── 异步工作流线程 ──────────────────────────────────────────

def run_project_pipeline(topic: str, receive_id: str):
    """
    全自动跑通后续的流程：step1_writer -> comic_generator -> step3_assembler
    """
    try:
        clear_last_error_context()
        ok, reason = preflight_story_ready(topic)
        if not ok:
            raise RuntimeError(
                f"{reason}\n请先点击「重写剧本 + 全部重画」或重新生成定妆照后再开始生产。"
            )
        msg1 = f"🚀 收到开工指令，正在全面生产 \n主题: 【{topic}】\n这大约需要 20 分钟左右，请您耐心等待..."
        mgr.send_text(receive_id, "open_id", msg1)
        add_to_history(receive_id, "assistant", msg1)
        state.set_status("STEP1_WRITING", topic)
        
        # 1. 跑导播剧剧本 (生成提示词)
        print(f"  -> [HUB] 运行 step1_writer_v6.py...")
        subprocess.run(["python", "src/step1_writer_v6.py"], cwd=str(BASE_DIR), env=dict(os.environ, PYTHONIOENCODING="utf-8"), check=True)
        msg2 = "✅ [1/3] 分镜脚本已规划完毕！正在进入最核心的‘全量画面+配音’生成阶段..."
        mgr.send_text(receive_id, "open_id", msg2)
        add_to_history(receive_id, "assistant", msg2)
        
        state.set_status("STEP2_GENERATING", topic)
        # 2. 跑生图与配音
        print(f"  -> [HUB] 运行 step2_comic_generator_v6.py...")
        subprocess.run(["python", "src/step2_comic_generator_v6.py"], cwd=str(BASE_DIR), env=dict(os.environ, PYTHONIOENCODING="utf-8"), check=True)
        msg3 = "✅ [2/3] 全量原画与音频素材已杀青！正在为您进行最终的视频剪辑与特效合成..."
        mgr.send_text(receive_id, "open_id", msg3)
        add_to_history(receive_id, "assistant", msg3)
        
        state.set_status("STEP3_ASSEMBLING", topic)
        # 3. 合成视频
        print(f"  -> [HUB] 运行 step3_assembler_v6.py...")
        try:
            step3_ret = subprocess.run(
                ["python", "src/step3_assembler_v6.py"],
                cwd=str(BASE_DIR),
                env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                check=True,
                capture_output=True,
                text=True
            )
            if step3_ret.stdout:
                print(step3_ret.stdout)
            if step3_ret.stderr:
                print(step3_ret.stderr)
        except subprocess.CalledProcessError as e:
            err_tail = (e.stderr or e.stdout or str(e)).strip()
            if len(err_tail) > 1500:
                err_tail = err_tail[-1500:]
            print(f"[STEP3 ERR] {err_tail}")
            raise RuntimeError(f"Step3 失败：{err_tail}") from e
        # 交付视频
        output_mp4 = BASE_DIR / "data" / "output" / "narrative_v6_final_epic.mp4"
        if not output_mp4.exists():
            raise RuntimeError(f"Step3 结束后未找到成片文件：{output_mp4}")

        mgr.send_text(receive_id, "open_id", "✅ [3/3] 视频合成大功告成！正在为您同步标清预览版（飞书）和超清母带（百度网盘）...")

        # ======= 第一步：尝试推送标清版本（飞书） =======
        file_key = mgr.upload_video(str(output_mp4))
        if file_key:
            mgr.send_text(receive_id, "open_id", f"✅ 【{topic}】全自动生产完毕！视频预览如下：")
            # 发送视频卡片或直接发送文件
            msg_body = json.dumps({"file_key": file_key})
            request = CreateMessageRequest.builder() \
                .receive_id_type("open_id") \
                .request_body(CreateMessageRequestBody.builder()
                              .receive_id(receive_id)
                              .msg_type("media")
                              .content(msg_body)
                              .build()) \
                .build()
            mgr.client.im.v1.message.create(request)
        else:
            mgr.send_text(receive_id, "open_id", "⚠️ 原片超过 50MB 飞书发不过去。别慌，网盘直传马上开始！")
            
        # ======= 第二步：核心动作！最高优先级直传百度网盘 =======
        mgr.send_text(receive_id, "open_id", f"☁️ 绝密管线启动：正在将【1080P 超清母带】上传至您的个人百度网盘，预计 30 秒...")
        try:
            bypy_cmd = ["python", "-m", "bypy", "upload", str(output_mp4), f"/game_videos/{topic}_HD母带.mp4"]
            subprocess.run(bypy_cmd, env=dict(os.environ, PYTHONIOENCODING="utf-8"), check=False, timeout=600)
            mgr.send_text(receive_id, "open_id", f"🎉 **直传成功！** 您的超清大片已稳稳锁进手机！\n👉 请打开手机百度网盘，进入【我的网盘/apps/bypy/game_videos/】查收直接发抖音！")
        except subprocess.TimeoutExpired:
            print(f"[BYPY ERR] 上传云盘超时熔断！")
            mgr.send_text(receive_id, "open_id", "⚠️ 百度网盘上传超时阻断。底层母带依然保留在您的电脑桌面上。")
        except Exception as e:
            print(f"[BYPY ERR] {e}")
            mgr.send_text(receive_id, "open_id", "❌ 百度网盘通讯受阻，请检查授权。文件依然保留在您的电脑桌面上。")

        state.set_status("COMPLETED", "")
        clear_last_error_context()
        
    except Exception as e:
        failed_stage = state.get_current_state().get("status", "UNKNOWN")
        save_last_error_context(topic, failed_stage, str(e))
        mgr.send_text(receive_id, "open_id", f"🚨 警报: 工作流中断！\n错误详情: {e}")
        state.set_status("ERROR", topic)

def run_synopsis_setup(topic: str, receive_id: str, feedback: str = "", duration: float = 1.25):
    """第一重审批：只生成大纲并推给用户看（不触碰 V6 源代码）"""
    try:
        clear_last_error_context()
        from openai import OpenAI
        from src.style_config import LLM_API_KEY, LLM_BASE_URL, MODEL_LLM
        mgr.send_text(receive_id, "open_id", f"🧠 正在为【{topic}】构思剧情大纲..." if not feedback else f"🔄 收到反馈，正在为您重新修改大纲...")
        state.set_status("GENERATING_SYNOPSIS", topic)
        
        client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
        prompt = f"""你是一个极其冷酷的现实主义编剧与行业规则解剖师。
任务：根据主题设定一个充满【利益算计】、【阶层跃迁】与【人性异化】的第二人称人生副本。
主题：{topic}
{f'**重要修改意见**：{feedback}' if feedback else ''}

要求：
1. **隐性阶层结构**：故事在底层逻辑上必须包含清晰的跃迁轨迹（入局 -> 进阶 -> 掌权 -> 巅峰与反噬），但绝不使用任何等级或Level标签。
2. **核心科普（潜规则拆解）**：将该行业的核心运作机制、灰产逻辑或权力分配规则，作为主角晋升的关键武器。不要枯燥说教，要通过主角的“具体决定”和“利益交换”来展现。
3. **数字与代价**：故事推进必须伴随具体的数字（金钱、份额、时间）以及主角为了权力所抛弃的底线。
4. **结局闭环**：巅峰时刻必须伴随绝对的冷酷与孤独，主角最终要彻底沦为庞大系统的“宿命囚徒”或面临命运的黑色幽默式反噬。
5. **字数限制**：大约 700 字左右，逻辑必须极其严密。必须以“今天你要体验的人生副本是...”开头。

只要一个纯净的 JSON，包含字段: "synopsis" (大纲文本), "era" (时代背景), "identity" (终极身份), "industry_rules" (行业潜规则数组)"""
        
        completion = client.chat.completions.create(
            model=MODEL_LLM,
            messages=[{"role": "user", "content": prompt}]
        )
        content = completion.choices[0].message.content.strip()
        import re
        if content.startswith("```"): content = re.sub(r"^```(?:json)?\n|\n```$", "", content, flags=re.IGNORECASE)
        synopsis_data = json.loads(content)
        synopsis_data["duration"] = duration # 🧪 记住老板选的时长
        
        with open(BASE_DIR / "feishu" / "temp_synopsis.json", "w", encoding="utf-8") as f:
            json.dump(synopsis_data, f, ensure_ascii=False)
        
        # 汇报给飞书（发带按钮的卡片）
        synopsis_card = {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"content": f"📖 剧情大纲：{topic}", "tag": "plain_text"}, "template": "purple"},
            "elements": [
                {"tag": "markdown", "content": f"**🕰️ 时代**：{synopsis_data.get('era')}\n**👤 身份**：{synopsis_data.get('identity')}"},
                {"tag": "hr"},
                {"tag": "markdown", "content": synopsis_data.get('synopsis', '')},
                {"tag": "hr"},
                {"tag": "markdown", "content": "**请选择下一步操作：**"},
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"content": "✅ 大纲通过，生成定妆照", "tag": "plain_text"}, "type": "primary",
                     "value": {"action_type": "approve_synopsis", "topic": topic}},
                    {"tag": "button", "text": {"content": "✏️ 我要修改大纲", "tag": "plain_text"}, "type": "default",
                     "value": {"action_type": "request_revise_synopsis", "topic": topic}},
                ]},
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"content": "🚫 取消项目，重新选题", "tag": "plain_text"}, "type": "danger",
                     "value": {"action_type": "cancel_project", "topic": topic}},
                ]},
            ]
        }
        mgr.send_card(receive_id, "open_id", synopsis_card)
        add_to_history(receive_id, "assistant", f"【系统已推送剧情大纲卡片，主题：{topic}，等待审批】")
        state.set_status("WAITING_SYNOPSIS_APPROVAL", topic)

    except Exception as e:
        save_last_error_context(topic, "GENERATING_SYNOPSIS", str(e))
        mgr.send_text(receive_id, "open_id", f"🚨 大纲生成失败！\n详情: {e}")
        state.set_status("ERROR", topic)

def run_visual_setup(topic: str, receive_id: str, regen_stage: str = None):
    """
    点选主题后：先生成骨架脚本和人设图，然后发给老板看。
    """
    try:
        clear_last_error_context()
        # 尝试还原老板选的时长
        duration = 1.25
        try:
            with open(BASE_DIR / "feishu" / "temp_synopsis.json", "r", encoding="utf-8") as f:
                duration = json.load(f).get("duration", 1.25)
        except: pass

        if regen_stage == "__all__":
            if not FULL_STORY_V6_PATH.exists():
                print("  -> [HUB] 检测到 __all__ 但本地无剧本，自动回退为全新生成。")
                regen_stage = None
                msg_pre = "⚠️ 未检测到可复用剧本，已自动切换为【重写剧本 + 全部重画】..."
            else:
                msg_pre = "🎨 保留剧本，正在重画全部阶段定妆照，约 1-2 分钟..."
        elif regen_stage:
            msg_pre = f"🧠 正在为您重新绘制【{regen_stage}】阶段的形象，请稍候..."
        else:
            msg_pre = f"🧠 正在为【{topic}】构思剧本和定妆照，预计 1-2 分钟..."
        mgr.send_text(receive_id, "open_id", msg_pre)
        add_to_history(receive_id, "assistant", msg_pre)
        
        state.set_status("GENERATING_VISUALS", topic)

        # 🚀 智能复用逻辑：如果本地已经跑好了这个主题，且没有明确要求重画，就跳过
        need_generate = True
        try:
            if not regen_stage and FULL_STORY_V6_PATH.exists():
                with open(FULL_STORY_V6_PATH, "r", encoding="utf-8") as f:
                    done_data = json.load(f)
                    if done_data.get("metadata", {}).get("topic") == topic:
                        print(f"  -> [HUB] 检测到主题【{topic}】已存在就绪剧本，跳过生图环节...")
                        need_generate = False
        except: pass

        if need_generate:
            # __all__ = 保留剧本重画全部；普通 regen_stage = 重画单阶段；None = 全新生成
            if not regen_stage:
                print(f"  -> [HUB] 运行 run_story_planner_with_mock.py (duration={duration})...")
                cmd = ["python", "feishu/run_story_planner_with_mock.py", "--topic", topic, "--duration", str(duration)]
                r0 = subprocess.run(cmd, cwd=str(BASE_DIR),
                                    env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                                    capture_output=True, text=True, encoding="utf-8", errors="replace")
                if r0.returncode != 0:
                    err = (r0.stderr or r0.stdout or "无详情")[-600:]
                    raise RuntimeError(f"剧本生成失败 (exit={r0.returncode}):\n{err}")

            print(f"  -> [HUB] 运行定妆照生成引擎 ref_generator.py...")
            ref_cmd = ["python", "src/ref_generator.py", "--topic", topic, "--role", "protagonist"]
            # __all__ 不传 --stage，让 ref_generator 重画全部阶段
            if regen_stage and regen_stage != "__all__":
                ref_cmd += ["--stage", regen_stage]
            r1 = subprocess.run(ref_cmd, cwd=str(BASE_DIR),
                                env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r1.returncode != 0:
                err = (r1.stderr or r1.stdout or "无详情")[-600:]
                raise RuntimeError(f"定妆照生成失败 (exit={r1.returncode}):\n{err}")
            
            print(f"  -> [HUB] 剧本与图片生成完毕，准备上传飞书...")
        
        # 一次性抓取人生阶段定妆照展示（支持 child/youth/middle/elderly）
        stages = {
            "child": {"name": "幼年期", "btn": "👶 重画幼年"},
            "youth": {"name": "青年期", "btn": "🧑 重画青年"},
            "middle": {"name": "中年期", "btn": "👤 重画中年"},
            "elderly": {"name": "老年期", "btn": "👴 重画老年"},
        }
        stage_order = ["child", "youth", "middle", "elderly"]

        # 读取本次“应涉及阶段”（由 ref_generator 回写），避免误判“未涉及”
        expected_stages = set()
        try:
            if FULL_STORY_V6_PATH.exists():
                with open(FULL_STORY_V6_PATH, "r", encoding="utf-8") as _f:
                    _story_data = json.load(_f)
                _master = _story_data.get("master_design", {}) if isinstance(_story_data, dict) else {}
                _detected = _master.get("detected_life_stages", [])
                if isinstance(_detected, list):
                    expected_stages = {s for s in _detected if s in stages}
                # 兜底：若未写 detected_life_stages，尝试 physical_char_anchors
                if not expected_stages:
                    _anchors = _master.get("physical_char_anchors", {})
                    if isinstance(_anchors, dict):
                        expected_stages = {k for k in _anchors.keys() if k in stages}
        except Exception as _e:
            print(f"  -> [HUB] 读取阶段探测结果失败: {_e}")
        
        # 发送确认卡片（初始化头部）
        card = {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"content": f"🎬 定妆照审批：{topic}", "tag": "plain_text"}, "template": "blue"},
            "elements": [
                {"tag": "markdown", "content": "**您的主角人生阶段定妆照已出炉，请过目：**"}
            ]
        }

        generated_stages = []

        # 按固定顺序遍历阶段，分别上传并加入卡片
        for stage_key in stage_order:
            stage_info = stages[stage_key]
            stage_name = stage_info["name"]
            char_img_path = BASE_DIR / "data" / "refs" / f"protagonist_{stage_key}" / "triple_view.png"
            if char_img_path.exists():
                print(f"  -> [HUB] 正在上传 {stage_name} 定妆照...")
                img_key = mgr.upload_image(str(char_img_path))
                if img_key:
                    print(f"  -> [HUB] 上传成功: {img_key}")
                    card["elements"].append({"tag": "markdown", "content": f"👤 **{stage_name}**"})
                    card["elements"].append({"tag": "img", "img_key": img_key, "alt": {"content": stage_name, "tag": "plain_text"}})
                    generated_stages.append(stage_key)
                else:
                    print(f"  -> [HUB] 警告: {stage_name} 上传失败 (img_key 为空)")
                    card["elements"].append({"tag": "markdown", "content": f"⚠️ **{stage_name}** 图片上传失败，请在电脑 data/refs/protagonist_{stage_key}/triple_view.png 直接查看。"})
                    generated_stages.append(stage_key) # 虽然上传失败，但物理文件存在，也算生成了
            else:
                if stage_key in expected_stages:
                    # 应该有但没找到：提示真实异常，避免误导成“未涉及”
                    print(f"  -> [HUB] 异常: {stage_name} 属于应涉及阶段但未找到文件。")
                    card["elements"].append({"tag": "markdown", "content": f"⚠️ **{stage_name}**：该阶段应已生成，但当前未在 data/refs/protagonist_{stage_key}/triple_view.png 找到文件，请重画该阶段。"})
                else:
                    # 智能裁剪提示（仅在确实未涉及时显示）
                    print(f"  -> [HUB] 智能裁剪: {stage_name} 剧本未涉及，跳过展示。")
                    card["elements"].append({"tag": "markdown", "content": f"💡 **{stage_name}**：系统根据剧情跨度判断本次剧本未涉及该阶段，因此未生成此照片。"})
        
        card["elements"].append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"content": "✅ 全部通过，开始生产视频", "tag": "plain_text"},
                    "type": "primary",
                    "value": {"action_type": "approve_visuals", "topic": topic}
                }
            ]
        })

        # 动态组装单阶段重画按钮（只给生成了的阶段提供重画按钮）
        regen_actions = []
        for stage_key in generated_stages:
            regen_actions.append({
                "tag": "button",
                "text": {"content": stages[stage_key]["btn"], "tag": "plain_text"},
                "type": "default",
                "value": {"action_type": "regen_stage", "topic": topic, "stage": stage_key}
            })
        if regen_actions:
            card["elements"].append({
                "tag": "action",
                "actions": regen_actions
            })

        card["elements"].append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"content": "🎨 保留剧本，重画全部人物", "tag": "plain_text"},
                    "type": "default",
                    "value": {"action_type": "regen_all_visuals_only", "topic": topic}
                },
                {
                    "tag": "button",
                    "text": {"content": "🧨 重写剧本 + 全部重画", "tag": "plain_text"},
                    "type": "danger",
                    "value": {"action_type": "reject_visuals", "topic": topic}
                }
            ]
        })
        card["elements"].append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"content": "🚫 取消当前项目，重新开始", "tag": "plain_text"},
                    "type": "default",
                    "value": {"action_type": "cancel_project", "topic": topic}
                }
            ]
        })
        
        print(f"  -> [HUB] 正在向飞书推送/刷新审批卡片...")
        _mid_file = BASE_DIR / "feishu" / "visual_card_mid.txt"
        _updated = False
        if regen_stage:  # 单阶段或 __all__ 重画：尝试原地刷新旧卡片，不刷屏
            try:
                saved_mid = _mid_file.read_text(encoding="utf-8").strip()
                if saved_mid and mgr.update_card(saved_mid, card):
                    print(f"  -> [HUB] 卡片原地刷新成功 ({saved_mid})")
                    _updated = True
                else:
                    print(f"  -> [HUB] update_card 失败，降级发新卡")
            except Exception as _ue:
                print(f"  -> [HUB] 原地刷新出错({_ue})，降级发新卡")
        if not _updated:
            new_mid = mgr.send_card(receive_id, "open_id", card)
            if new_mid:
                _mid_file.write_text(new_mid, encoding="utf-8")
        add_to_history(receive_id, "assistant", f"【系统已推送人设阶段定妆照审批卡片给您，主题：{topic}】")
        state.set_status("WAITING_CHARACTER_APPROVAL", topic)
        print(f"  -> [HUB] 流程已挂起，等待审批。")
        
    except Exception as e:
        print(f"  -> [HUB] 严重错误: {e}")
        import traceback
        traceback.print_exc()
        save_last_error_context(topic, "GENERATING_VISUALS", str(e))
        mgr.send_text(receive_id, "open_id", f"🚨 定妆照生成失败！\n详情: {e}")
        state.set_status("ERROR", topic)

# ── 事件处理器 ──────────────────────────────────────────────

def do_card_action(data: P2CardActionTrigger) -> P2CardActionTriggerResponse:
    """处理用户在卡片上点击按钮的动作"""
    try:
        open_id = data.event.operator.open_id
        action_val = data.event.action.value
        
        if isinstance(action_val, str):
            import json
            action_val = json.loads(action_val)
            
        action_type = action_val.get("action_type")
        topic = action_val.get("topic", "")

        if action_type == "select_topic":
            curr_state = state.get_current_state()
            if curr_state["status"] not in ["IDLE", "WAITING_TOPIC", "COMPLETED"]:
                status_map = {
                    "GENERATING_SYNOPSIS": "🧠 正在编写大纲", "WAITING_SYNOPSIS_APPROVAL": "👀 等待您审批大纲",
                    "GENERATING_VISUALS": "🎨 正在绘制三阶段定妆照", "WAITING_CHARACTER_APPROVAL": "👀 等待您审批定妆图",
                    "STEP1_WRITING": "✍️ 正在规划分镜", "STEP2_GENERATING": "🖼️ 正在生成全量原画", "STEP3_ASSEMBLING": "🎬 正在剪辑合成",
                }
                curr_human_status = status_map.get(curr_state["status"], curr_state["status"])
                # 发冲突卡片，让老板选择
                conflict_card = {
                    "config": {"wide_screen_mode": True},
                    "header": {"title": {"content": "⚠️ 检测到未完成的项目", "tag": "plain_text"}, "template": "orange"},
                    "elements": [
                        {"tag": "markdown", "content": f"**您有一个上次未完成的项目：**\n🔖 主题：【{curr_state['topic']}】\n📍 当前进度：{curr_human_status}\n\n您新选择的主题是：**【{topic}】**\n\n请问您要怎么处理？"},
                        {"tag": "action", "actions": [
                            {"tag": "button", "text": {"content": "▶️ 继续上一个项目", "tag": "plain_text"}, "type": "primary",
                             "value": {"action_type": "resume_project", "topic": curr_state["topic"]}},
                            {"tag": "button", "text": {"content": "🆕 放弃上一个，开始新项目", "tag": "plain_text"}, "type": "danger",
                             "value": {"action_type": "confirm_new_project", "topic": topic, "open_id": open_id}},
                        ]}
                    ]
                }
                mgr.send_card(open_id, "open_id", conflict_card)
                return P2CardActionTriggerResponse({"toast": {"type": "warning", "content": "检测到未完成项目，请在卡片上选择如何处理。"}})

            threading.Thread(target=run_synopsis_setup, args=(topic, open_id, "", 1.25)).start()
            return P2CardActionTriggerResponse({"toast": {"type": "info", "content": f"已选中：{topic}，正在生成大纲..."}})
            
        elif action_type == "approve_synopsis":
            if os.path.exists(BASE_DIR / "feishu" / "temp_synopsis.json"):
                threading.Thread(target=run_visual_setup, args=(topic, open_id)).start()
                return P2CardActionTriggerResponse({"toast": {"type": "success", "content": "大纲通过！正在生成定妆照..."}})
            else:
                return P2CardActionTriggerResponse({"toast": {"type": "error", "content": "找不到大纲文件，请重新生成。"}})

        elif action_type == "request_revise_synopsis":
            mgr.send_text(open_id, "open_id", "✏️ 请直接说出您的修改意见，我会立刻重新生成大纲。\n例如：开头太平淡，要有更强的悬念感")
            return P2CardActionTriggerResponse({"toast": {"type": "info", "content": "请在对话框输入修改意见"}})

        elif action_type == "approve_visuals":
            curr_state = state.get_current_state()
            if curr_state["status"] not in ["WAITING_CHARACTER_APPROVAL"]:
                return P2CardActionTriggerResponse({"toast": {"type": "warning", "content": "任务已被分配，当前已处于生产中或任务已丢弃，请勿重复点击"}})
            run_topic = curr_state.get("topic") or topic
            ok, reason = preflight_story_ready(run_topic)
            if not ok:
                mgr.send_text(open_id, "open_id", f"⚠️ 无法开始生产：{reason}")
                return P2CardActionTriggerResponse({"toast": {"type": "error", "content": "前置素材不完整，请先重写剧本或重画"}})
            threading.Thread(target=run_project_pipeline, args=(run_topic, open_id)).start()
            return P2CardActionTriggerResponse({"toast": {"type": "success", "content": "收到！开始爆肝生产！"}})
            
        elif action_type == "reject_visuals":
            # BUG-11 修复：清场旧素材，防止旧分镜混入新项目
            import shutil
            for _clean_dir in [
                BASE_DIR / "data" / "storyboards",
                BASE_DIR / "data" / "audio",
                BASE_DIR / "data" / "output",
            ]:
                if _clean_dir.exists():
                    shutil.rmtree(_clean_dir)
                _clean_dir.mkdir(parents=True, exist_ok=True)
            threading.Thread(target=run_visual_setup, args=(topic, open_id)).start()
            return P2CardActionTriggerResponse({"toast": {"type": "info", "content": "收到，正在打回重写大纲并全部重画..."}})

        elif action_type == "regen_stage":
            stage = action_val.get("stage")
            threading.Thread(target=run_visual_setup, args=(topic, open_id, stage)).start()
            return P2CardActionTriggerResponse({"toast": {"type": "info", "content": f"收到，正在单独重画：{stage}"}})

        elif action_type == "regen_all_visuals_only":
            # 保留剧本，重画全部三阶段定妆照（__all__ 是内部标记，不传 --stage 给 ref_generator）
            threading.Thread(target=run_visual_setup, args=(topic, open_id, "__all__")).start()
            return P2CardActionTriggerResponse({"toast": {"type": "info", "content": "保留剧本，正在重画全部定妆照..."}}) 

        elif action_type == "cancel_project":
            kill_pipeline_processes()
            state.set_status("IDLE", "")
            mgr.send_text(open_id, "open_id", "🗑️ 已取消当前项目并重置系统。发送「换一批」可重新获取新主题。")
            return P2CardActionTriggerResponse({"toast": {"type": "success", "content": "项目已取消，系统已重置。"}})

        elif action_type == "confirm_new_project":
            new_topic = action_val.get("topic", "")
            operator_id = action_val.get("open_id", open_id)
            kill_pipeline_processes()
            state.set_status("IDLE", "")
            if new_topic:
                threading.Thread(target=run_synopsis_setup, args=(new_topic, operator_id, "", 1.25)).start()
            return P2CardActionTriggerResponse({"toast": {"type": "success", "content": f"已放弃旧项目，正在为「{new_topic}」生成大纲..."}})

        elif action_type == "resume_project":
            # 继续上一个项目：什么都不用做，提示一下
            curr_state = state.get_current_state()
            mgr.send_text(open_id, "open_id", f"▶️ 好的，继续推进【{curr_state['topic']}】。发送「状态」可查看当前进度。")
            return P2CardActionTriggerResponse({"toast": {"type": "info", "content": "继续上一个项目。"}})

        elif action_type == "do_nothing":
            return P2CardActionTriggerResponse({"toast": {"type": "info", "content": "收到，请耐心等待。"}})
            
        elif action_type == "request_ideas":
            import ideator
            threading.Thread(target=ideator.send_morning_topics, args=(open_id,)).start()
            return P2CardActionTriggerResponse({"toast": {"type": "success", "content": "为您搜罗一批新点子中..."}})
            
        elif action_type == "restart_backend":
            mgr.send_text(open_id, "open_id", "🔄 已收到重启请求：后台即将重启，约 10-20 秒恢复。")
            schedule_self_restart_notice(open_id, reason="card_button")
            return P2CardActionTriggerResponse({"toast": {"type": "info", "content": "即将杀死后台进程并冷启动..."}})

        elif action_type == "retry_failed_stage":
            curr_state = state.get_current_state()
            if curr_state["status"] != "ERROR":
                return P2CardActionTriggerResponse({"toast": {"type": "warning", "content": "当前不在错误态，无需重试。"}})

            err_ctx = load_last_error_context()
            retry_topic = topic or err_ctx.get("topic") or curr_state.get("topic", "")
            failed_stage = err_ctx.get("failed_stage", "UNKNOWN")
            if not retry_topic:
                return P2CardActionTriggerResponse({"toast": {"type": "error", "content": "缺少项目主题，请重新发起项目。"}})

            if failed_stage in ["GENERATING_SYNOPSIS", "WAITING_SYNOPSIS_APPROVAL"]:
                threading.Thread(target=run_synopsis_setup, args=(retry_topic, open_id, "", 1.25)).start()
            elif failed_stage in ["GENERATING_VISUALS", "WAITING_CHARACTER_APPROVAL"]:
                threading.Thread(target=run_visual_setup, args=(retry_topic, open_id)).start()
            elif failed_stage in ["STEP1_WRITING", "STEP2_GENERATING", "STEP3_ASSEMBLING"]:
                threading.Thread(target=run_project_pipeline, args=(retry_topic, open_id)).start()
            else:
                # 兜底：未知阶段时，从全量生产入口继续
                threading.Thread(target=run_project_pipeline, args=(retry_topic, open_id)).start()
            return P2CardActionTriggerResponse({"toast": {"type": "success", "content": f"收到，正在重试失败环节（{failed_stage}）..."}})

        return P2CardActionTriggerResponse({})
    except Exception as e:
        print(f"[ERR] Card action error: {e}")
        import traceback; traceback.print_exc()
        return P2CardActionTriggerResponse({"toast": {"type": "error", "content": f"Error: {str(e)}"}})

# Global message dedup lock
PROCESSED_MSG_IDS = {}

def do_message_receive(data: P2ImMessageReceiveV1) -> None:
    """
    处理常规聊天消息（入口：防跳动 + 物理隔离）
    """
    msg_id = data.event.message.message_id
    
    # 🛡️ 拦截器 1：防止复读锁
    if msg_id in PROCESSED_MSG_IDS:
        return
    PROCESSED_MSG_IDS[msg_id] = True
    if len(PROCESSED_MSG_IDS) > 2000: 
        # 保留最近的 1000 条，平滑清理过期记忆
        for k in list(PROCESSED_MSG_IDS.keys())[:1000]:
            del PROCESSED_MSG_IDS[k]
    
    # 🛡️ 拦截器 2：异步处理（秒回飞书，免除重试补发）
    threading.Thread(target=_handle_message_logic_async, args=(data,)).start()


def send_status_card(open_id, topic, status):
    status_map = {
        "IDLE": "🟢 空闲待机（请让我推荐选题）",
        "WAITING_TOPIC": "⏳ 等待您选择盲盒题目",
        "GENERATING_SYNOPSIS": "🧠 正在连线大模型撰写剧情大纲...",
        "WAITING_SYNOPSIS_APPROVAL": "👀 大纲已发，正在等待您批示（可回复修改意见）",
        "GENERATING_VISUALS": "🎨 正在绘制三阶段定妆照...",
        "WAITING_CHARACTER_APPROVAL": "👀 定妆照已发，等待您决定是否重画",
        "STEP1_WRITING": "✍️ [生产阶段 1/3] 正在规划分镜和视觉脚本...",
        "STEP2_GENERATING": "🖼️ [生产阶段 2/3] 生图流与配音满载运转中 (耗时较长)...",
        "STEP3_ASSEMBLING": "🎬 [生产阶段 3/3] 正在剪辑合并视频大片...",
        "COMPLETED": "✅ 视频已交付！",
        "ERROR": "❌ 发生崩溃中断！流程已卡死"
    }
    human_status = status_map.get(status, status)
    
    # 根据状态配置卡片颜色和内容
    template_color = "blue"
    if status == "ERROR": template_color = "red"
    elif status in ["IDLE", "COMPLETED", "WAITING_TOPIC"]: template_color = "green"
    elif status.startswith("WAITING_"): template_color = "orange"

    card = {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"content": "📊 管线进度报告", "tag": "plain_text"}, "template": template_color},
        "elements": []
    }
    
    if status in ["IDLE", "COMPLETED", "WAITING_TOPIC"]:
        card["elements"].append({"tag": "markdown", "content": f"**📍 当前状态**：{human_status}\n\n💡 当前没有正在进行的项目，您可以开启新的旅程。"})
        card["elements"].append({"tag": "action", "actions": [
            {"tag": "button", "text": {"content": "🎲 获取盲盒选题", "tag": "plain_text"}, "type": "primary", "value": {"action_type": "request_ideas"}}
        ]})
    else:
        extra_error_info = ""
        if status == "ERROR":
            err_ctx = load_last_error_context()
            err_stage = err_ctx.get("failed_stage", "UNKNOWN")
            err_detail = (err_ctx.get("error_detail", "") or "").strip()
            if len(err_detail) > 320:
                err_detail = err_detail[-320:]
            if err_detail:
                extra_error_info = f"\n\n**🧩 失败环节**：`{err_stage}`\n**📝 最近错误**：\n`{err_detail}`"
            else:
                extra_error_info = f"\n\n**🧩 失败环节**：`{err_stage}`"

        card["elements"].append({"tag": "markdown", "content": f"**🔖 在建项目**：【{topic}】\n**📍 当前进度**：{human_status}{extra_error_info}\n\n请问您要如何处理？"})
        
        actions = []
        if status == "ERROR":
            actions.append({"tag": "button", "text": {"content": "🔁 重试失败环节", "tag": "plain_text"}, "type": "primary", "value": {"action_type": "retry_failed_stage", "topic": topic}})
            actions.append({"tag": "button", "text": {"content": "🔄 强制重启代码后台", "tag": "plain_text"}, "type": "default", "value": {"action_type": "restart_backend"}})
        # 注意：生产中不显示"耐心等待"按钮，系统默认继续运行，用户只能选择放弃
        actions.append({"tag": "button", "text": {"content": "🚫 放弃并终止此项目", "tag": "plain_text"}, "type": "danger", "value": {"action_type": "cancel_project", "topic": topic}})
        card["elements"].append({"tag": "action", "actions": actions})
        
    mgr.send_card(open_id, "open_id", card)

def _handle_message_logic_async(data: P2ImMessageReceiveV1) -> None:
    """指挥部大脑异步处理逻辑（原常规聊天逻辑）"""
    open_id = data.event.sender.sender_id.open_id
    msg_raw = data.event.message.content
    try:
        import json
        parsed = json.loads(msg_raw)
        msg = parsed.get("text", "")
        if not msg:
            msg = str(parsed)
    except:
        msg = msg_raw
        
    s = state.get_current_state()
    current_topic = s.get("topic", "暂无")
    current_status = s.get("status", "IDLE")

    # === 拦截一：状态检查与忙碌/错误状态直通车 ===
    msg_clean = msg.strip()
    
    # 如果用户问了好、或者问状态，或者是纯粹的乱码短句，且不在需要他文字输入的阶段
    # 或者是机器人在纯搬砖（生图、剪辑等），此时直接给他发状态卡片
    BUSY_OR_ERROR_STATES = ["GENERATING_SYNOPSIS", "GENERATING_VISUALS", "STEP1_WRITING", "STEP2_GENERATING", "STEP3_ASSEMBLING", "ERROR"]
    
    is_asking_status = msg_clean in ["状态", "进度", "你是谁", "在吗", "你好", "你什么情况", "什么情况"]
    INTERCEPT_WHITELIST = [
        "重启", "复活", "重置", "清空", "强行重开",
        "取消项目", "取消当前项目", "停止项目", "终止项目", "不做了", "取消",
        "换一批", "刷新", "换个", "再来一批", "重新推荐", "换一下",
        "帮助", "救命", "指令",
    ]
    is_whitelisted = any(w in msg_clean for w in INTERCEPT_WHITELIST)
    is_busy_blocked = current_status in BUSY_OR_ERROR_STATES and not is_whitelisted
    if is_asking_status or is_busy_blocked:
        send_status_card(open_id, current_topic, current_status)
        return

    elif msg_clean in ["帮助", "救命", "指令"]:
        help_text = (
            "🛠️ **工业级管线远程控制手册**\n\n"
            "1️⃣ **选题阶段**：\n   - `换一批`: 刷新盲盒点子\n   - 任意发送您的创意即可交流\n\n"
            "2️⃣ **审批阶段**：\n   - `可以`: 准了，推进下一步\n   - `不好`: 打回重画/重写\n   - 任意反馈修改意见给大模型导演\n\n"
            "3️⃣ **系统维护**：\n   - `状态`: 查看当前流水线位置\n   - `重启`: 远程复活卡死的进程\n   - `强行重开`: 彻底清空所有任务数据库"
        )
        mgr.send_text(open_id, "open_id", help_text)
        return

    elif msg_clean in ["重置", "清空", "强行重开"]:
        state.set_status("IDLE", "无")
        mgr.send_text(open_id, "open_id", "🔄 已强行重置后台状态机为【空闲状态/IDLE】，您可以重新开始盲盒流程了。")
        return

    # 取消/终止当前项目（文字快速通道）
    CANCEL_PHRASES = ["取消项目", "取消当前项目", "停止项目", "终止项目", "不做了", "停", "取消", "清除项目"]
    if any(p in msg_clean for p in CANCEL_PHRASES) and current_status not in ["IDLE", "WAITING_TOPIC", "COMPLETED"]:
        kill_pipeline_processes()
        state.set_status("IDLE", "")
        mgr.send_text(open_id, "open_id", f"🗑️ 已取消项目【{current_topic}】并重置系统。\n发送「换一批」可重新获取主题。")
        return

    elif msg_clean in ["重启", "复活"]:
        mgr.send_text(open_id, "open_id", "🚀 收到！后台开始冷重启，约 10-20 秒恢复。")
        schedule_self_restart_notice(open_id, reason="text_command")
        return

    # ===== 快速通道：对于语义极明确的常用短词，**绕开 LLM** 直接执行，100%可靠 =====
    # 「审批通过」快速通道
    APPROVE_PHRASES = [
        "可以", "行", "妥", "确定", "通过", "准了", "不错", "ok", "OK",
        "下一步", "进行下一步", "开始下一步", "进入下一步", "下一步吧", "进入下一个步骤",
        "继续", "继续吧", "继续进行", "权利",
        "开始生产", "生成吧", "开始吧", "拍吧", "搞起", "搞起来", "就这个吧", "就这样吧",
    ]
    # 审批态下，“好/可”过于模糊，要求二次确认或直接点卡片按钮，避免误触发推进
    if current_status in ["WAITING_SYNOPSIS_APPROVAL", "WAITING_CHARACTER_APPROVAL"] and msg_clean in ["好", "可"]:
        mgr.send_text(
            open_id,
            "open_id",
            "⚠️ 为避免误触发，请点击卡片按钮确认；或回复「下一步/确认通过」再继续。"
        )
        return
    # 判断是否是审批通过意图：直接匹配，或是包含审批词且消息很短
    is_approval = (
        msg_clean in APPROVE_PHRASES
        or any(msg_clean.startswith(p) or msg_clean.endswith(p) for p in ["下一步", "进行下一步", "开始吹", "可以，进", "好了，"])
        or (len(msg_clean) <= 10 and any(p in msg_clean for p in ["下一步", "进行", "开始吹"]))
    )
    if is_approval:
        if current_status == "WAITING_SYNOPSIS_APPROVAL":
            if os.path.exists(BASE_DIR / "feishu" / "temp_synopsis.json"):
                mgr.send_text(open_id, "open_id", "✅ 收到！大纲已确认，正在可动定妆照生成流程...")
                threading.Thread(target=run_visual_setup, args=(current_topic, open_id)).start()
            else:
                mgr.send_text(open_id, "open_id", "⚠️ 无待审批的剧情数据，请先运行选题或重置。")
            return
        elif current_status == "WAITING_CHARACTER_APPROVAL":
            mgr.send_text(open_id, "open_id", "✅ 定妆照已确认！开始推入剧本生产流水线！")
            threading.Thread(target=run_project_pipeline, args=(current_topic, open_id)).start()
            return
        # 其他状态下说“可以”，不需要走展，继续渗透到 LLM 做更新天道的盁天大真丬

    # 「扛一批」快速通道
    REFRESH_PHRASES = ["换一批", "刷新", "换个", "再来一批", "重新推荐", "不想要这些", "换一下"]
    if any(p in msg_clean for p in REFRESH_PHRASES):
        import ideator
        threading.Thread(target=ideator.send_morning_topics, args=(open_id,)).start()
        return

    # 「盲盒 / 出主意」快速通道  
    IDEAS_PHRASES = ["盲盒", "出题", "给我出个主题", "推荐一个", "推荐主题"]
    if any(p in msg_clean for p in IDEAS_PHRASES):
        import ideator
        threading.Thread(target=ideator.send_morning_topics, args=(open_id,)).start()
        return

    from openai import OpenAI
    from src.style_config import LLM_API_KEY, LLM_BASE_URL, MODEL_LLM
    try:
        client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
        
        # --- 核心大脑：动态指令集 ---
        instruction_set = ""
        if current_status in ["IDLE", "WAITING_TOPIC", "COMPLETED"]:
            instruction_set = """【当前权限：选题与立项】
老板还没有选定要拍的主题，引导他表达创意或选择题目。
1. 老板明确说出了要拍的主题（哪怕是一句描述），直接开机：
   指令模板：[TRIGGER_START: 主题名称, 视频时长分钟] （没提时长默认 1.25）
2. 老板想要换一批建议、不知道拍啥、让你出主意：
   指令模板：[TRIGGER_IDEAS]
⚠️ 注意：如果老板只是在随便聊聊创意，还没说"拍这个"、"就这个"、"开始"等确认词，不要输出任何指令！"""
        
        elif current_status == "WAITING_SYNOPSIS_APPROVAL":
            instruction_set = """【当前权限：大纲审批】
系统刚刚已向老板发送了剧情大纲，老板正在审阅。你的唯一任务是判断老板对"当前这份大纲"的态度。

【判断准则 - 必须严格遵守】
✅ 以下情况输出 [TRIGGER_APPROVE_SYNOPSIS]（老板同意了当前大纲，推进下一步）：
  - 说"可以"、"行"、"好的"、"不错"、"通过"、"OK"、"就这个"
  - 说"进行下一步"、"下一步吧"、"开始生产"、"进下一步"、"继续"
  - 说"可以，视频时长X分钟"、"好了，X分钟"、"可以，时长X"（含时长的确认 = 确认大纲同时指定时长）
  - 说"生成吧"、"开始吧"、"拍吧"、"搞起"
✏️ 以下情况输出 [TRIGGER_REVISE_SYNOPSIS: 具体修改要求]（老板提出了修改意见）：
  - 说"故事不够好"、"结尾不行"、"换个更有趣的"、"修改一下XXX"
  - 说"故事情节改成XXX"、"我觉得XXX不对"等带有具体改动的话

⚠️ 禁令：
- **绝对禁止**在大纲审批阶段输出 [TRIGGER_START]，老板说"可以"绝对是在对当前大纲表态，不是在重新立项！
- 如果老板只是在随口聊天或问问题，用专业语气回答，不要输出任何指令。"""
        
        elif current_status == "WAITING_CHARACTER_APPROVAL":
            instruction_set = """【当前权限：定妆照审批】
系统已向老板发送了主角幼/中/老三阶段定妆照。
1. 老板同意了照片（说"可以"、"不错"、"通过"、"下一步"等确认词）：
   指令模板：[TRIGGER_APPROVE_CHARACTER]
2. 老板不满意，要求重新绘制：
   指令模板：[TRIGGER_REGEN_CHARACTER: child/middle/old/all之中的一个]
   （child=幼年/童年，middle=中年/成年，old=老年，all=全部重画）"""


        system_prompt = f"""你是视频项目的沟通协调员，帮助用户和后台自动化系统对话。

你绝对不能模拟系统行为、编造进度或编造系统限制。你只负责引导用户决策和理解意图。

【管线知识】1.大纲(Synopsis) -> 2.定妆照(Visuals) -> 3.剧本分镜 -> 4.渲染生成 -> 5.剪辑交付。

【当前环境数据】
- 进行中主题：{current_topic}
- 流程状态：{current_status}

{instruction_set}

【铁律禁令 - 必须严格遵守】
1. 严禁虚构系统行为：绝对不能写"正在生成...97%...完成"、"图片已发送"之类的假进度消息。
2. 严禁编造系统限制：绝对不能说"系统暂不支持传图"、"需对接本地渲染终端"等，这些全是错误的。
3. 如果用户问图片/定妆照在哪里，只需说：后台正在处理，完成后会自动推送飞书卡片，无需用户操作。
4. 不要在没有明确意图时输出控制指令。
5. 大纲审批阶段老板说"可以/下一步/继续"=批准当前大纲，不要跳回立项。
回复控制在80字内。"""
        
        add_to_history(open_id, "user", msg)
        messages = [{"role": "system", "content": system_prompt}] + CHAT_HISTORY.get(open_id, [])
        
        completion = client.chat.completions.create(
            model=MODEL_LLM,
            messages=messages,
            temperature=0.8
        )
        chat_reply = completion.choices[0].message.content.strip()
        
        # 记录 AI 发送给用户的内容（清理掉隐藏指令）
        clean_reply_for_history = re.sub(r"\[TRIGGER_.*?\]", "", chat_reply).strip()
        if clean_reply_for_history:
            mgr.send_text(open_id, "open_id", clean_reply_for_history)
            add_to_history(open_id, "assistant", clean_reply_for_history)

        
        # 🛡️ 工业级任务保护逻辑：防止任务“撞车”
        def _check_busy() -> bool:
             s2 = state.get_current_state()
             if s2["status"] not in ["IDLE", "WAITING_TOPIC", "COMPLETED", "WAITING_SYNOPSIS_APPROVAL", "WAITING_CHARACTER_APPROVAL", "ERROR"]:
                 mgr.send_text(open_id, "open_id", f"🚫 **目前已有任务在运行中！**\n\n🔖 **任务名**：【{s2['topic']}】\n⚠️ 请等待它运行结束，或者通过【重置】命令强行终止旧任务。")
                 return True
             return False

        # 解析指令
        if "[TRIGGER_STOP]" in chat_reply:
            kill_pipeline_processes()
            state.set_status("IDLE", "")
            mgr.send_text(open_id, "open_id", "🎬 收到！已为您紧急叫停所有生产线。")
            
        elif "[TRIGGER_IDEAS]" in chat_reply:
            import ideator
            import threading
            threading.Thread(target=ideator.send_morning_topics, args=(open_id,)).start()
            
        elif "[TRIGGER_APPROVE_SYNOPSIS]" in chat_reply:
            # 大纲批准，开始生图
            if current_status in ["WAITING_SYNOPSIS_APPROVAL", "ERROR", "IDLE", "GENERATING_SYNOPSIS", "GENERATING_VISUALS"]:
                import os
                if os.path.exists(BASE_DIR / "feishu" / "temp_synopsis.json"):
                    import threading
                    threading.Thread(target=run_visual_setup, args=(current_topic, open_id)).start()
                else:
                    mgr.send_text(open_id, "open_id", "⚠️ 找不到待审批的剧情数据，请先下发盲盒选题。")

        elif "[TRIGGER_REVISE_SYNOPSIS:" in chat_reply:
            m = re.search(r"\[TRIGGER_REVISE_SYNOPSIS: (.*?)\]", chat_reply)
            if m:
                feedback = m.group(1).strip()
                import threading
                threading.Thread(target=run_synopsis_setup, args=(current_topic, open_id, feedback)).start()

        elif "[TRIGGER_START:" in chat_reply:
            if _check_busy(): return
            m = re.search(r"\[TRIGGER_START: (.*?),\s*([\d\.]+)\]", chat_reply)
            if m:
                topic = m.group(1).strip()
                duration = float(m.group(2).strip())
            else:
                # 兼容旧的反推格式/无时长的格式
                m2 = re.search(r"\[TRIGGER_START: (.*?)\]", chat_reply)
                topic = m2.group(1).strip() if m2 else ""
                duration = 1.25
                
            if topic:
                import threading
                mgr.send_text(open_id, "open_id", f"✅ 立项动作激活：【{topic}】\n📍 生产时长：{duration} 分钟\n正在为您秘密开启这个人生副本...")
                threading.Thread(target=run_synopsis_setup, args=(topic, open_id, "", duration)).start()

        elif "[TRIGGER_APPROVE_CHARACTER]" in chat_reply:
            if current_status == "WAITING_CHARACTER_APPROVAL":
                import threading
                mgr.send_text(open_id, "open_id", "✅ 定妆照通过！开始推入剪辑生产流流水线！")
                threading.Thread(target=run_project_pipeline, args=(current_topic, open_id)).start()

        elif "[TRIGGER_REGEN_CHARACTER:" in chat_reply:
            m = re.search(r"\[TRIGGER_REGEN_CHARACTER: (.*?)\]", chat_reply)
            if m:
                stage_req = m.group(1).strip()
                # BUG-09 修复：统一别名，"old" → "elderly"（与 ref_generator/style_config 保持一致）
                STAGE_ALIAS = {"old": "elderly", "child": "child", "middle": "middle", "elderly": "elderly"}
                stage = STAGE_ALIAS.get(stage_req)
                threading.Thread(target=run_visual_setup, args=(current_topic, open_id, stage)).start()

    except Exception as e:
        print(f"  -> [CHAT_ERR] 类型={type(e).__name__} 信息={e}")
        import traceback
        traceback.print_exc()
        # 尝试说一句有帮助的话而不是废话
        s3 = state.get_current_state()
        status_tip = {
            "WAITING_SYNOPSIS_APPROVAL": "您可以直接发送「可以」推进下一步，或直接说出修改意见。",
            "WAITING_CHARACTER_APPROVAL": "您可以发送「可以」开始生产，或发送「重画」并说明哪个阶段。",
        }.get(s3["status"], "可以发送「状态」查看当前进度。")
        mgr.send_text(open_id, "open_id", f"▶️ {status_tip}")

# ── 启动总线 ───────────────────────────────────────────────

event_handler = lark.EventDispatcherHandler.builder("", "") \
    .register_p2_card_action_trigger(do_card_action) \
    .register_p2_im_message_receive_v1(do_message_receive) \
    .build()

cli = lark.ws.Client(
    app_id=env_vars["FEISHU_APP_ID"],
    app_secret=env_vars["FEISHU_APP_SECRET"],
    event_handler=event_handler,
    log_level=lark.LogLevel.INFO
)

if __name__ == "__main__":
    write_pid()
    flush_pending_restart_notice()
    while True:
        try:
            ts = time.strftime('%Y-%m-%d %H:%M:%S')
            sys.stdout.buffer.write(f"[{ts}] [START] Connecting to Feishu...\n".encode('utf-8'))
            sys.stdout.buffer.flush()
            cli.start()
        except Exception as e:
            ts = time.strftime('%Y-%m-%d %H:%M:%S')
            sys.stdout.buffer.write(f"[{ts}] [RECONNECT] {e}, retrying in 10s...\n".encode('utf-8'))
            sys.stdout.buffer.flush()
            time.sleep(10)
