"""
错误恢复引擎
============
三级错误分级 + 自动重试 + 飞书远程恢复卡片

设计目标：让远程用户（手机飞书端）能处理大多数故障，
         只有代码级问题才需要坐到电脑前。
"""
import re
import threading
from enum import Enum
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

from feishu.config import STATUS


# ================================================================
# 一、错误严重级别
# ================================================================
class ErrorSeverity(Enum):
    TRANSIENT = "transient"    # 瞬时故障 → 自动重试，用户无感
    RETRYABLE = "retryable"    # 可恢复   → 推送卡片，用户点按钮重试
    FATAL     = "fatal"        # 致命     → 推送诊断卡片，告知必须电脑修复


# ================================================================
# 二、错误指纹 → 恢复策略 注册表
# ================================================================
# key 格式： "步骤名:错误特征"  步骤名用 * 表示匹配所有步骤
# 匹配规则：特征字符串出现在异常类型名 或 错误消息中即命中

ERROR_RECOVERY_MAP = {

    # ──── 瞬时故障（自动重试，用户无感）────

    "tts:ConnectionResetError": {
        "severity": ErrorSeverity.TRANSIENT,
        "title": "🎙️ TTS 网络波动",
        "user_msg": "微软语音服务连接中断，后台正在自动重试…",
        "max_auto_retry": 3,
    },
    "tts:TimeoutError": {
        "severity": ErrorSeverity.TRANSIENT,
        "title": "⏱️ TTS 请求超时",
        "user_msg": "语音合成超时，正在自动重试…",
        "max_auto_retry": 3,
    },
    "tts:Cannot connect to host": {
        "severity": ErrorSeverity.TRANSIENT,
        "title": "🌐 TTS 服务器不可达",
        "user_msg": "无法连接微软语音服务器，正在自动重试…",
        "max_auto_retry": 3,
    },
    "tts:ServerDisconnectedError": {
        "severity": ErrorSeverity.TRANSIENT,
        "title": "🔌 TTS 服务端断开",
        "user_msg": "语音服务端断开连接，正在自动重试…",
        "max_auto_retry": 3,
    },
    "tts:ClientConnectorError": {
        "severity": ErrorSeverity.TRANSIENT,
        "title": "📡 TTS 网络不可达",
        "user_msg": "网络暂时不可达，正在自动重试…",
        "max_auto_retry": 3,
    },
    "tts:*": {  # 其他 TTS 错误 → 重试
        "severity": ErrorSeverity.TRANSIENT,
        "title": "🎙️ TTS 异常",
        "user_msg": "语音合成出现异常，正在自动重试…",
        "max_auto_retry": 2,
    },
    "tts:NoConnectionError": {
        "severity": ErrorSeverity.TRANSIENT,
        "title": "🔇 TTS 连接异常",
        "user_msg": "TTS 引擎连接异常，正在自动重试…",
        "max_auto_retry": 3,
    },
    "tts:SSLError": {
        "severity": ErrorSeverity.TRANSIENT,
        "title": "🔒 TTS SSL 异常",
        "user_msg": "SSL 握手失败，正在自动重试…",
        "max_auto_retry": 3,
    },

    "llm:RateLimitError": {
        "severity": ErrorSeverity.TRANSIENT,
        "title": "⏳ LLM 限流",
        "user_msg": "大模型接口限流，后台自动等待重试…",
        "max_auto_retry": 5,
    },
    "llm:APIConnectionError": {
        "severity": ErrorSeverity.TRANSIENT,
        "title": "🌐 LLM 连接失败",
        "user_msg": "LLM 接口连接失败，正在自动重试…",
        "max_auto_retry": 3,
    },
    "llm:APITimeoutError": {
        "severity": ErrorSeverity.TRANSIENT,
        "title": "⏱️ LLM 超时",
        "user_msg": "大模型响应超时，正在自动重试…",
        "max_auto_retry": 3,
    },
    "llm:InternalServerError": {
        "severity": ErrorSeverity.TRANSIENT,
        "title": "🔧 LLM 服务端错误",
        "user_msg": "大模型服务暂时异常，正在自动重试…",
        "max_auto_retry": 3,
    },

    # ──── 可重试故障（推送卡片，用户点按钮）────

    "image:quota": {
        "severity": ErrorSeverity.RETRYABLE,
        "title": "🎨 生图配额耗尽",
        "user_msg": "图片生成 API 余额不足或配额超限。\n请充值后点击下方按钮重试。",
        "actions": [
            {"text": "🔄 重试当前步骤", "action_type": "retry_failed_stage"},
            {"text": "🗑️ 取消项目",       "action_type": "cancel_project"},
        ],
    },
    "image:auth": {
        "severity": ErrorSeverity.RETRYABLE,
        "title": "🔑 生图鉴权失败",
        "user_msg": "图片 API Key 无效。\n请在电脑上更新 `.env` 中的 `GRIBO_IMG_API_KEY` 后重试。",
        "actions": [
            {"text": "🔄 重试当前步骤", "action_type": "retry_failed_stage"},
            {"text": "🗑️ 取消项目",       "action_type": "cancel_project"},
        ],
    },
    "image:*": {
        "severity": ErrorSeverity.RETRYABLE,
        "title": "🖼️ 生图引擎异常",
        "user_msg": "图片生成出现异常。可能是网络波动，建议重试。",
        "actions": [
            {"text": "🔄 重试当前步骤", "action_type": "retry_failed_stage"},
        ],
    },

    "step1:phase2": {
        "severity": ErrorSeverity.RETRYABLE,
        "title": "📝 Step1 音频生成失败",
        "user_msg": "旁白音频（TTS）生成失败。可能是网络波动导致；后台已尽力自动重试，仍失败时请点下方「重试 Step1」再次执行 TTS 与时间轴。",
        "actions": [
            {"text": "🔄 重试 Step1（含 TTS）", "action_type": "retry_failed_stage"},
            {"text": "🗑️ 取消项目",       "action_type": "cancel_project"},
        ],
    },
    "step1:phase3": {
        "severity": ErrorSeverity.RETRYABLE,
        "title": "🎬 Step1 分镜生成失败",
        "user_msg": "分镜视觉蓝图生成失败。可能是 LLM 接口异常。",
        "actions": [
            {"text": "🔄 重试 Step1",   "action_type": "retry_failed_stage"},
            {"text": "🗑️ 取消项目",       "action_type": "cancel_project"},
        ],
    },
    "step2:grid-only": {
        "severity": ErrorSeverity.RETRYABLE,
        "title": "🧩 Step2 宫格生图失败",
        "user_msg": "16 宫格分镜图生成失败。",
        "actions": [
            {"text": "🔄 重试 Step2",   "action_type": "retry_failed_stage"},
            {"text": "⏭️ 跳过分镜生图",   "action_type": "skip_stage"},
            {"text": "🗑️ 取消项目",       "action_type": "cancel_project"},
        ],
    },
    "step3:*": {
        "severity": ErrorSeverity.RETRYABLE,
        "title": "🎥 Step3 视频合失败",
        "user_msg": "视频剪辑合成失败，可尝试重试。",
        "actions": [
            {"text": "🔄 重试 Step3",   "action_type": "retry_failed_stage"},
        ],
    },
    "pipeline:*": {
        "severity": ErrorSeverity.RETRYABLE,
        "title": "⚙️ 管线错误",
        "user_msg": "生产管线发生错误，可重试。",
        "actions": [
            {"text": "🔄 重试",       "action_type": "retry_failed_stage"},
            {"text": "🗑️ 取消项目",    "action_type": "cancel_project"},
        ],
    },

    # ──── 致命故障（只能电脑修复）────

    "import:module_not_found": {
        "severity": ErrorSeverity.FATAL,
        "title": "📦 缺少 Python 依赖",
        "user_msg": "缺少必需的 Python 模块。请在电脑上运行安装命令后重启服务。",
    },
    "import:no module named": {
        "severity": ErrorSeverity.FATAL,
        "title": "📦 缺少 Python 依赖",
        "user_msg": "缺少必需的 Python 模块。请在电脑上运行安装命令后重启服务。",
    },
    "file:full_story_v6.json": {
        "severity": ErrorSeverity.FATAL,
        "title": "📁 缺少剧本文件",
        "user_msg": "找不到 full_story_v6.json，流水线无法继续。请检查项目文件完整性。",
    },
    "file:no such file": {
        "severity": ErrorSeverity.FATAL,
        "title": "📁 缺少关键文件",
        "user_msg": "找不到关键文件，流水线无法继续。请检查项目文件完整性。",
    },
    "disk:no space": {
        "severity": ErrorSeverity.FATAL,
        "title": "💾 磁盘空间不足",
        "user_msg": "磁盘空间不足，无法继续生产。请清理磁盘后重启服务。",
    },
    "ffmpeg:not found": {
        "severity": ErrorSeverity.FATAL,
        "title": "🔧 缺少 FFmpeg",
        "user_msg": "未找到 FFmpeg。请在电脑上安装 FFmpeg 并加入系统 PATH。",
    },
}

# 致命错误匹配兜底
FATAL_SIGNATURES = [
    "module_not_found", "no module named",
    "no space left", "disk full",
    "permission denied",
    "ffmpeg.*not found", "ffprobe.*not found",
]

# 瞬时网络错误关键词（用于未显式注册的步骤）
TRANSIENT_NETWORK_SIGNATURES = [
    "ConnectionResetError", "ConnectionRefusedError", "ConnectionError",
    "TimeoutError", "Timeout", "timed out",
    "ClientConnectorError", "ServerDisconnectedError",
    "Cannot connect to host", "Network is unreachable",
    "Temporary failure in name resolution",
    "ProxyError", "SSLError",
]


# ================================================================
# 三、错误分类 + 策略匹配
# ================================================================
def classify_error(step_name: str, error_text: str) -> dict:
    """
    根据步骤名 + 错误文本，匹配恢复策略。

    参数：
        step_name: 步骤标识（如 "tts", "llm", "image", "step1", "step2", "step3", "pipeline"）
        error_text: 异常类型名 + 错误消息的拼接文本

    返回：
        {"severity": ErrorSeverity, "title": str, "user_msg": str, "actions": [...]}
    """
    err_lower = error_text.lower()
    step_lower = step_name.lower()

    # 先检查致命签名
    for sig in FATAL_SIGNATURES:
        if re.search(sig, err_lower):
            return {
                "severity": ErrorSeverity.FATAL,
                "title": "⚠️ 致命错误",
                "user_msg": f"检测到需要电脑端处理的致命错误。\n详情：{error_text[:300]}",
                "actions": [],
            }

    # 精确匹配：step:signature
    best_match = None
    best_len = 0

    for fingerprint, strategy in ERROR_RECOVERY_MAP.items():
        fp_step, fp_sig = fingerprint.split(":", 1)

        # 步骤匹配：精确 或 通配
        if fp_step != "*" and fp_step != step_lower:
            continue

        # 签名匹配：精确
        if fp_sig != "*" and fp_sig.lower() not in err_lower:
            continue

        score = len(fp_sig)  # 更长的匹配更精确
        if score > best_len:
            best_match = strategy
            best_len = score

    if best_match:
        return dict(best_match)

    # 检查瞬时网络错误
    for sig in TRANSIENT_NETWORK_SIGNATURES:
        if sig.lower() in err_lower:
            return {
                "severity": ErrorSeverity.TRANSIENT,
                "title": "🌐 网络异常",
                "user_msg": "检测到网络异常，后台正在自动重试…",
                "max_auto_retry": 3,
            }

    # 未知错误 → 可重试（乐观策略：能重试就先重试）
    return {
        "severity": ErrorSeverity.RETRYABLE,
        "title": f"❓ {step_name} 未识别错误",
        "user_msg": f"流水线出现未预料的错误。\n```\n{error_text[:400]}\n```",
        "actions": [
            {"text": "🔄 重试当前步骤", "action_type": "retry_failed_stage"},
            {"text": "🗑️ 取消项目",       "action_type": "cancel_project"},
        ],
    }


# ================================================================
# 四、错误恢复卡片生成
# ================================================================
def build_error_recovery_card(strategy: dict, step_name: str, topic: str,
                               error_text: str = "", attempt: int = 1,
                               auto_retry_remaining: int = 0,
                               run_id: str = "") -> dict:
    """
    生成飞书错误恢复卡片。

    参数：
        strategy: classify_error() 返回的策略字典
        step_name: 当前步骤名
        topic: 项目主题
        error_text: 原始错误文本（截断到 500 字符）
        attempt: 当前重试次数
        auto_retry_remaining: 自动重试剩余次数（瞬时故障时 >0）

    返回：飞书卡片 dict
    """
    severity = strategy.get("severity", ErrorSeverity.RETRYABLE)
    actions = strategy.get("actions", [])

    header_color = {
        ErrorSeverity.TRANSIENT: "blue",
        ErrorSeverity.RETRYABLE: "orange",
        ErrorSeverity.FATAL: "red",
    }.get(severity, "red")

    status_icon = {
        ErrorSeverity.TRANSIENT: "🔄",
        ErrorSeverity.RETRYABLE: "⚠️",
        ErrorSeverity.FATAL: "🚨",
    }.get(severity, "❌")

    title = strategy.get("title", "流水线错误")
    user_msg = strategy.get("user_msg", "发生未知错误。")

    # 构建详情
    detail = f"{status_icon} **{title}**\n\n{user_msg}"
    if auto_retry_remaining > 0:
        detail += f"\n\n⏳ 后台自动重试中…（剩余 {auto_retry_remaining} 次）"
    elif severity == ErrorSeverity.TRANSIENT:
        detail += f"\n\n❌ 自动重试 {attempt} 次后仍未恢复。"
    if error_text:
        detail += f"\n\n📋 错误详情：\n```\n{error_text[:500]}\n```"
    rid = (run_id or "").strip()
    if rid:
        detail += f"\n\n🔖 **Run-ID**：`{rid}`"
    detail += f"\n\n📌 项目：{topic}\n⚙️ 步骤：{step_name}"

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"content": title, "tag": "plain_text"},
            "template": header_color,
        },
        "elements": [
            {"tag": "markdown", "content": detail},
        ],
    }

    # 恢复按钮（仅可重试/瞬态耗尽时显示）
    if actions and severity != ErrorSeverity.FATAL:
        card["elements"].append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"content": a["text"], "tag": "plain_text"},
                    "type": "primary" if "重试" in a["text"] else "danger",
                    "value": {
                        "action_type": a["action_type"],
                        "topic": topic,
                        "step_name": step_name,
                    },
                }
                for a in actions
            ],
        })

    return card


# ================================================================
# 五、全局错误上下文存储（跨步骤共享）
# ================================================================
_last_error_context: dict = {}
_error_lock = threading.Lock()


def set_error_context(topic: str, step_name: str, strategy: dict, error_text: str, failed_stage: str = "") -> None:
    """记录最近一次错误上下文，供远程重试使用"""
    with _error_lock:
        _last_error_context.clear()
        _last_error_context.update({
            "topic": topic,
            "step_name": step_name,
            "failed_stage": failed_stage or step_name,
            "severity": strategy.get("severity", ErrorSeverity.RETRYABLE).value,
            "title": strategy.get("title", ""),
            "user_msg": strategy.get("user_msg", ""),
            "error_text": error_text[:1000],
            "timestamp": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
        })


def get_error_context() -> dict:
    """获取最近一次错误上下文"""
    with _error_lock:
        return dict(_last_error_context)


def clear_error_context() -> None:
    """清除错误上下文"""
    with _error_lock:
        _last_error_context.clear()
