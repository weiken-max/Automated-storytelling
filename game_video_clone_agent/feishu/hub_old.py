import os
import sys
import re
import json
import subprocess
import threading
import time
import queue
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
from src.run_context import get_paths, get_current_run_id, RUNS_ROOT, CURRENT_RUN_FILE
PYTHON_BIN = sys.executable

PID_FILE = BASE_DIR / "feishu" / "hub.pid"
PENDING_RESTART_FILE = BASE_DIR / "feishu" / "pending_restart_open_id.json"
LAST_ERROR_CTX_FILE = BASE_DIR / "feishu" / "last_error_context.json"
STORYBOARD_CARD_HOLDER_FILE = BASE_DIR / "feishu" / "storyboard_card_holder.json"

# 导入错误恢复引擎
from feishu.error_recovery import (
    classify_error,
    build_error_recovery_card,
    set_error_context,
    ErrorSeverity,
)


def _active_paths():
    return get_paths(create_if_missing=False)


def _active_asset_paths():
    paths = _active_paths() or {}
    if not paths:
        return {}
    scripts_dir = paths["scripts_dir"]
    return {
        "run_dir": paths["run_dir"],
        "scripts_dir": scripts_dir,
        "refs_dir": paths["refs_dir"],
        "storyboards_dir": paths["storyboards_dir"],
        "audio_dir": paths["audio_dir"],
        "output_dir": paths["output_dir"],
        "full_story": scripts_dir / "full_story_v6.json",
        "pseudo_srt": scripts_dir / "pseudo_srt.json",
        "narrative": scripts_dir / "narrative_v6_final.json",
        "master_voice": paths["audio_dir"] / "master_voice.mp3",
        "final_mp4": paths["output_dir"] / "narrative_v6_final_epic.mp4",
    }


def _run_assets_status():
    a = _active_asset_paths()
    if not a:
        return {"ok": False, "reason": "未检测到激活批次", "assets": {}, "run_id": None}
    storyboards_dir = a["storyboards_dir"]
    s_count = len(list(storyboards_dir.glob("S_*.png"))) if storyboards_dir.exists() else 0
    assets = {
        "full_story": a["full_story"].exists(),
        "pseudo_srt": a["pseudo_srt"].exists(),
        "narrative": a["narrative"].exists(),
        "master_voice": a["master_voice"].exists(),
        "s_016": (storyboards_dir / "S_016.png").exists(),
        "storyboards_any": s_count > 0,
        "final_mp4": a["final_mp4"].exists(),
    }
    return {"ok": True, "reason": "ok", "assets": assets, "run_id": get_current_run_id(), "s_count": s_count}


def _read_step2_report(run_id: str) -> dict:
    """读取 Step2 结构化报告，供 Step3 准入门禁使用。"""
    try:
        if not run_id:
            return {}
        report_path = RUNS_ROOT / run_id / "logs" / "step2_report.json"
        if report_path.exists():
            return json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] 读取 step2_report 失败: {e}")
    return {}


def _validate_step2_gate(run_id: str) -> tuple[bool, str]:
    """Step3 准入门禁：Step2 必须结构化成功且分镜落盘。"""
    report = _read_step2_report(run_id)
    if not report:
        return False, "未找到 Step2 报告（step2_report.json），无法确认生图成功。"
    if not report.get("ok", False):
        batch = report.get("blocking_batch", "?")
        reason = report.get("reason", "未知错误")
        rng = report.get("subshot_range", "")
        return False, f"Step2 未通过（batch={batch} {rng}）：{reason}"
    total = int(report.get("total_shots", 0) or 0)
    generated = int(report.get("generated_shots", 0) or 0)
    if total <= 0 or generated < total:
        return False, f"Step2 产物不完整：已生成 {generated}/{total}。"
    return True, "ok"


# Step3 孤儿自愈（Step2 已成功但成片未落盘）全局互斥，避免并发双跑 ffmpeg
_orphan_step3_lock = threading.Lock()


def _step3_orphan_recovery_needed() -> tuple[bool, dict | None, str]:
    """
    判断当前激活批次是否需要自动补跑 Step3。
    返回 (need, assets, run_id)；need 为 True 时 assets 非空。
    """
    run_id = get_current_run_id() or ""
    if not run_id:
        return False, None, ""
    assets = _active_asset_paths()
    if not assets:
        return False, None, run_id
    if assets["final_mp4"].exists():
        return False, None, run_id
    gate_ok, _ = _validate_step2_gate(run_id)
    if not gate_ok:
        return False, None, run_id
    if not assets["master_voice"].exists() or not assets["narrative"].exists():
        return False, None, run_id
    if not assets["storyboards_any"]:
        return False, None, run_id
    return True, assets, run_id


def _notify_step3_success_with_upload(open_id: str, final_mp4: Path, headline: str) -> None:
    """Step3 成功后：飞书文本 + 尝试上传视频预览（与 retry_single_step 行为一致）。"""
    final_path = str(final_mp4.resolve()).replace("\\", "/")
    file_size_mb = round(final_mp4.stat().st_size / (1024 * 1024), 2)
    mgr.send_text(
        open_id,
        "open_id",
        f"{headline}，成片已输出：{final_path}\n"
        f"📦 文件大小：{file_size_mb} MB\n"
        "正在尝试发送飞书预览...",
    )
    try:
        file_key = mgr.upload_video(str(final_mp4))
        if file_key:
            msg_body = json.dumps({"file_key": file_key})
            request = CreateMessageRequest.builder() \
                .receive_id_type("open_id") \
                .request_body(CreateMessageRequestBody.builder()
                              .receive_id(open_id)
                              .msg_type("media")
                              .content(msg_body)
                              .build()) \
                .build()
            media_resp = mgr.client.im.v1.message.create(request)
            if not media_resp or not media_resp.success():
                fail_msg = ""
                if media_resp:
                    fail_msg = f" code={getattr(media_resp, 'code', '')} msg={getattr(media_resp, 'msg', '')}"
                mgr.send_text(
                    open_id,
                    "open_id",
                    "⚠️ 飞书视频发送失败（上传已完成但消息投递失败）。"
                    f"{fail_msg}\n"
                    f"本次项目已完成，成片本地路径：{final_path}",
                )
        else:
            mgr.send_text(
                open_id,
                "open_id",
                f"⚠️ 飞书未返回 file_key（可能超限或接口失败）。\n"
                f"但本次项目已完成，成片已生成：{final_path}",
            )
    except Exception as e:
        mgr.send_text(
            open_id,
            "open_id",
            f"⚠️ 飞书视频推送异常：{e}\n"
            f"但本次项目已完成，成片已生成：{final_path}",
        )


def _recover_step3_if_orphaned(open_id: str | None, *, wait_for_lock: bool = False) -> bool:
    """
    若 Step2 已成功但缺成片，则自动执行 Step3。
    open_id 为空时仅打印日志（用于 Hub 冷启动等无会话场景）。
    wait_for_lock=True：队列 worker 使用，在检测到需要自愈时会阻塞等待锁，避免与后台自愈并发时误开 Step1。
    返回 True 表示已尝试进入合成流程（拿到锁且门禁通过）；False 为跳过。
    """
    need, assets, run_id = _step3_orphan_recovery_needed()
    if not need or not assets:
        return False
    acquired = _orphan_step3_lock.acquire(blocking=wait_for_lock)
    if not acquired:
        print("[RECOVER] Step3 自愈跳过：已有其他线程正在执行合成。")
        return False
    try:
        need2, assets2, run_id2 = _step3_orphan_recovery_needed()
        if not need2 or not assets2:
            return False
        assets, run_id = assets2, run_id2
        stop_flag = PIPELINE_STOP_FLAGS.setdefault(run_id, threading.Event())
        topic = state.get_current_state().get("topic", "")
        print(f"[RECOVER] Step3 孤儿自愈：run_id={run_id} topic={topic!r}，正在自动补跑 Step3...")
        if open_id:
            try:
                mgr.send_text(
                    open_id,
                    "open_id",
                    "🔧 **自动恢复**：检测到当前批次 Step2 已完成，但成片尚未生成。\n"
                    f"Run-ID：`{run_id}`\n正在自动执行 Step3（视频合成），请稍候。",
                )
            except Exception as ex:
                print(f"[WARN] 自愈飞书提示失败: {ex}")
        state.set_status("STEP3_ASSEMBLING", topic)
        out3, err3 = _run_cmd_with_pid_tracking(
            [PYTHON_BIN, "src/step3_assembler_v6.py"],
            BASE_DIR,
            run_id,
            stop_flag=stop_flag,
            capture_output=True,
        )
        if out3:
            print(out3)
        if err3:
            print(err3)
        final_mp4 = assets["final_mp4"]
        if final_mp4.exists():
            if open_id:
                _notify_step3_success_with_upload(
                    open_id,
                    final_mp4,
                    "✅ 自动补跑 Step3 完成",
                )
                state.set_status("COMPLETED", topic)
            else:
                print(
                    f"[RECOVER] Step3 完成（无飞书会话）：{final_mp4.resolve()}",
                )
                state.set_status("COMPLETED", topic)
        else:
            msg = "⚠️ Step3 执行结束但未检测到成片文件，请检查本地日志。"
            if open_id:
                mgr.send_text(open_id, "open_id", msg)
            else:
                print(f"[RECOVER] {msg}")
            state.set_status("ERROR", topic)
        return True
    except subprocess.CalledProcessError as e:
        err = ((e.stderr or e.output or str(e)) or "")[-1200:]
        if open_id:
            mgr.send_text(open_id, "open_id", f"🚨 自动补跑 Step3 失败：{err}")
        else:
            print(f"[RECOVER] Step3 失败：{err}")
        state.set_status("ERROR", state.get_current_state().get("topic", ""))
        return True
    except Exception as e:
        if open_id:
            mgr.send_text(open_id, "open_id", f"🚨 自动补跑 Step3 异常：{e}")
        else:
            print(f"[RECOVER] Step3 异常：{e}")
        state.set_status("ERROR", state.get_current_state().get("topic", ""))
        return True
    finally:
        try:
            _orphan_step3_lock.release()
        except Exception:
            pass


def _schedule_step3_orphan_recovery_if_needed(open_id: str) -> None:
    """在独立线程中执行自愈，避免阻塞飞书消息线程。"""
    need, _, _ = _step3_orphan_recovery_needed()
    if not need:
        return

    def _job():
        _recover_step3_if_orphaned(open_id, wait_for_lock=True)

    threading.Thread(target=_job, daemon=True).start()


def _notify_step2_failed(
    receive_id: str,
    topic: str,
    run_id: str,
    card_holder: dict,
    *,
    headline: str,
    stderr_tail: str = "",
    gate_reason: str = "",
) -> None:
    """
    Step2 失败时：更新运维进度卡片 + 单独发一条文本消息。
    避免用户只看卡片上「Step2 生图中」误以为仍在跑（此前子进程非零退出时未刷新卡片）。
    """
    state.set_status("STEP2_FAILED", topic)
    report = _read_step2_report(run_id)

    lines_md = [
        f"**{headline}**\n"
        "流水线已在此**停止**，进度条不会自动再往前走；请按下方指引重试。"
    ]
    lines_plain = [
        headline,
        "流水线已停止，请勿再等进度自动推进。",
        f"主题：{topic}",
        f"Run-ID：{run_id}",
    ]

    if gate_reason:
        lines_md.append(gate_reason)
        lines_plain.append(gate_reason.replace("**", ""))
    elif isinstance(report, dict) and report.get("ok") is False:
        b = report.get("blocking_batch", "?")
        tb = report.get("total_batches", "?")
        rng = report.get("subshot_range", "")
        gs = report.get("generated_shots", 0)
        ts = report.get("total_shots", 0)
        r = report.get("reason", "未知")
        lines_md.append(
            f"**失败宫格批次**：第 {b} / {tb} 批\n"
            f"**分镜编号**：{rng}\n"
            f"**子图进度**：{gs} / {ts} 张（`S_*.png`）\n"
            f"**原因**：{r}"
        )
        lines_plain.append(
            f"失败宫格批次：第{b}/{tb}批 | 分镜 {rng} | 子图 {gs}/{ts} 张。"
        )
        lines_plain.append(f"原因：{r}")
    elif isinstance(report, dict) and report:
        lines_md.append("（已存在 step2_report.json，但未标记为失败，请以日志为准。）")
        lines_plain.append("step2_report 状态异常，请查看本地终端日志。")
    else:
        lines_md.append("（未找到 `logs/step2_report.json`，可能进程异常退出。）")
        lines_plain.append("未找到 step2_report.json，请查看本地终端日志。")

    st = (stderr_tail or "").strip()
    if st:
        tail = st[-1000:] if len(st) > 1000 else st
        lines_md.append(f"\n**进程输出尾部：**\n```\n{tail}\n```")
        lines_plain.append("")
        lines_plain.append("进程日志尾部：")
        lines_plain.append(tail)

    lines_md.append("\n👉 **下一步**：请点击卡片「重跑 Step 2 (生图)」或发送 `/retry step2`")
    lines_plain.append("")
    lines_plain.append("下一步：点击「重跑 Step 2」或发送 /retry step2")

    detail = "\n\n".join(lines_md)
    _send_or_patch_progress_card(
        receive_id,
        _build_progress_card(
            topic,
            run_id,
            "❌ Step2 失败 · 已阻断 Step3",
            70,
            100,
            detail=detail,
        ),
        card_holder,
    )
    try:
        mgr.send_text(receive_id, "open_id", "\n".join(lines_plain))
    except Exception as ex:
        print(f"[WARN] Step2 失败飞书文本推送失败: {ex}")


# ── 分镜宫格审核卡 ──────────────────────────────────────────

def _load_storyboard_card_holder() -> dict:
    """加载分镜审核卡的 message_id，用于原地更新。"""
    try:
        if STORYBOARD_CARD_HOLDER_FILE.exists():
            return json.loads(STORYBOARD_CARD_HOLDER_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"message_id": None, "topic": "", "run_id": ""}


def _save_storyboard_card_holder(holder: dict):
    STORYBOARD_CARD_HOLDER_FILE.parent.mkdir(parents=True, exist_ok=True)
    STORYBOARD_CARD_HOLDER_FILE.write_text(json.dumps(holder, ensure_ascii=False), encoding="utf-8")


def _build_storyboard_review_card(
    topic: str,
    run_id: str,
    grid_files: list,
    batch_states: dict,
    revision_note: str = "",
) -> dict:
    """
    构建分镜宫格审核卡片。
    batch_states: {batch_index: "ok"|"failed"|"regening"} 用于标记每批次状态。
    revision_note: 追加在首段说明后（如重画后提示用户以新卡片为准）。
    """
    card = {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"content": f"🎬 分镜宫格审核：{topic}", "tag": "plain_text"}, "template": "blue"},
        "elements": [],
    }
    head = (
        f"**Run-ID**：`{run_id}`\n共 **{len(grid_files)}** 个批次的 16 宫格预览图已生成。"
        f"请逐张审核尺寸/布局是否正确，有问题请点按钮打回重画。"
    )
    if revision_note:
        head = f"{head}{revision_note}"
    card["elements"].append({"tag": "markdown", "content": head})

    for i, gf in enumerate(grid_files, 1):
        batch_name = gf.name
        state = batch_states.get(i, "ok")
        status_emoji = {"ok": "✅", "failed": "❌", "regening": "🔄"}.get(state, "✅")
        status_text = {"ok": "已就绪", "failed": "生成失败", "regening": "重画中..."}.get(state, "已就绪")
        # 计算该批次的分镜范围
        batch_start = (i - 1) * 16 + 1
        batch_end = batch_start + 15

        card["elements"].append({"tag": "hr"})
        card["elements"].append({
            "tag": "markdown",
            "content": f"{status_emoji} **批次 {i}/{len(grid_files)}**（分镜 S_{batch_start:03d}~S_{batch_end:03d}）{status_text}"
        })
        # 图片标签：飞书会按缩略图展示
        abs_path = gf if isinstance(gf, Path) else Path(str(gf))
        if abs_path.exists():
            img_key = mgr.upload_image(str(abs_path))
            if img_key:
                card["elements"].append({
                    "tag": "img",
                    "img_key": img_key,
                    "alt": {"content": f"批次{i}", "tag": "plain_text"},
                })
            else:
                card["elements"].append({
                    "tag": "markdown",
                    "content": f"⚠️ 批次 {i} 图片上传失败：`{abs_path}`"
                })
        else:
            card["elements"].append({
                "tag": "markdown",
                "content": f"⚠️ 批次 {i} 文件不存在：`{abs_path}`"
            })

        # 每个批次配一个打回按钮
        card["elements"].append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"content": f"❌ 打回批次 {i}（重画）", "tag": "plain_text"},
                "type": "danger",
                "value": {"action_type": "reject_storyboard_batch", "topic": topic, "batch_index": i}
            }]
        })

    # 底部：全部通过按钮
    card["elements"].append({"tag": "hr"})
    card["elements"].append({
        "tag": "action",
        "actions": [{
            "tag": "button",
            "text": {"content": "✅ 全部通过，开始切分高清 + 视频合成", "tag": "plain_text"},
            "type": "primary",
            "value": {"action_type": "approve_storyboards", "topic": topic}
        }]
    })
    return card


def run_storyboard_review(topic: str, receive_id: str):
    """Phase 2A 完成后：上传所有宫格图，发送审核卡片到飞书。"""
    assets = _active_asset_paths()
    if not assets:
        mgr.send_text(receive_id, "open_id", "❌ 未检测到激活批次，无法发送分镜审核卡。")
        return
    run_id = get_current_run_id() or "unknown"
    storyboards_dir = assets["storyboards_dir"]
    if not storyboards_dir.exists():
        mgr.send_text(receive_id, "open_id", "❌ 分镜目录不存在。")
        return

    grid_files = sorted(storyboards_dir.glob("grid_batch_*.png"))
    if not grid_files:
        mgr.send_text(receive_id, "open_id", "⚠️ 未生成任何宫格图，请检查 Step2-A 日志。")
        return

    mgr.send_text(receive_id, "open_id",
                  f"📬 已生成 {len(grid_files)} 个批次的 16 宫格分镜图，正在打包发送审核卡...")

    batch_states = {i: "ok" for i in range(1, len(grid_files) + 1)}
    card = _build_storyboard_review_card(topic, run_id, grid_files, batch_states)
    message_id = mgr.send_card(receive_id, "open_id", card)

    holder = {"message_id": message_id, "topic": topic, "run_id": run_id, "open_id": receive_id}
    _save_storyboard_card_holder(holder)

    state.set_status("WAITING_STORYBOARD_APPROVAL", topic)

    if message_id:
        print(f"  -> [HUB] 分镜审核卡已发送 (message_id={message_id})")
    else:
        mgr.send_text(receive_id, "open_id", "⚠️ 审核卡发送失败，请检查飞书 Bot 权限或网络。")


def resend_storyboard_review_card(open_id: str):
    """
    磁盘上已有 grid_batch_*.png，但飞书未收到或未展示分镜审核卡时：
    仅重新调用 run_storyboard_review（不重新跑 Step2 生图）。
    """
    assets = _active_asset_paths()
    if not assets:
        mgr.send_text(
            open_id,
            "open_id",
            "❌ 未检测到激活批次。若刚换过工作目录，请先 `/switch <Run-ID>` 再补发。",
        )
        return
    st = state.get_current_state()
    topic_use = (st.get("topic") or "").strip()
    if not topic_use and assets.get("narrative") and assets["narrative"].exists():
        try:
            fs_data = json.loads(assets["narrative"].read_text(encoding="utf-8"))
            mt = (fs_data.get("metadata") or {}).get("topic", "")
            if mt:
                topic_use = str(mt).strip()
        except Exception:
            pass
    if not topic_use:
        mgr.send_text(
            open_id,
            "open_id",
            "❌ 无法补发：缺少项目主题。请发「状态」确认在建项目，或 `/switch` 到正确批次。",
        )
        return
    sb = assets.get("storyboards_dir")
    grids = sorted(sb.glob("grid_batch_*.png")) if sb and sb.exists() else []
    if not grids:
        mgr.send_text(
            open_id,
            "open_id",
            "❌ 当前批次下没有 `grid_batch_*.png`，无法补发。请先完成 Step2-A 宫格生图。",
        )
        return
    mgr.send_text(
        open_id,
        "open_id",
        f"📬 已排队补发分镜审核卡（磁盘共 {len(grids)} 批宫格），队列执行后将推送新卡片…",
    )
    enqueue_job(
        open_id,
        f"补发分镜审核卡: {topic_use}",
        run_storyboard_review,
        topic_use,
        open_id,
    )


def _send_fresh_storyboard_review_card(
    receive_id: str,
    topic: str,
    *,
    revision_note: str = "",
) -> None:
    """
    重新上传宫格并 **新发** 一条分镜审核卡（更新 holder）。
    飞书客户端对 interactive 消息的 patch 往往缓存旧 img_key，打回重画后必须用新消息才能稳定看到新图。
    """
    assets = _active_asset_paths()
    if not assets:
        mgr.send_text(receive_id, "open_id", "❌ 无激活批次，无法推送更新后的分镜卡。")
        return
    run_id = get_current_run_id() or "unknown"
    storyboards_dir = assets["storyboards_dir"]
    if not storyboards_dir.exists():
        mgr.send_text(receive_id, "open_id", "❌ 分镜目录不存在。")
        return
    grid_files = sorted(storyboards_dir.glob("grid_batch_*.png"))
    if not grid_files:
        mgr.send_text(receive_id, "open_id", "⚠️ 未找到任何 grid_batch_*.png。")
        return
    batch_states = {i: "ok" for i in range(1, len(grid_files) + 1)}
    card = _build_storyboard_review_card(
        topic, run_id, grid_files, batch_states, revision_note=revision_note
    )
    new_mid = mgr.send_card(receive_id, "open_id", card)
    if new_mid:
        _save_storyboard_card_holder(
            {"message_id": new_mid, "topic": topic, "run_id": run_id, "open_id": receive_id}
        )
        state.set_status("WAITING_STORYBOARD_APPROVAL", topic)
        print(f"  -> [HUB] 已新发分镜审核卡 message_id={new_mid}")
    else:
        mgr.send_text(
            receive_id,
            "open_id",
            "⚠️ 分镜审核卡发送失败，请检查飞书 Bot 权限或网络后重试「补发分镜审核卡」。",
        )


def _send_single_batch_grid_preview(receive_id: str, topic: str, batch_index: int, run_id: str) -> bool:
    """
    打回重画成功后优先发送：仅该批 grid_batch 的一张图消息（只上传这一张，体感最快）。
    """
    assets = _active_asset_paths()
    if not assets:
        return False
    sd = assets.get("storyboards_dir")
    if not sd or not sd.exists():
        return False
    grid_path = sd / f"grid_batch_{batch_index:03d}.png"
    if not grid_path.exists():
        mgr.send_text(
            receive_id,
            "open_id",
            f"⚠️ 第 {batch_index} 批文件不存在：`{grid_path.name}`，无法发预览图。",
        )
        return False
    mgr.send_text(
        receive_id,
        "open_id",
        f"✅ **第 {batch_index} 批**已重画完成（Run-ID: `{run_id}` · {topic}）\n"
        f"👇 下方为**本批 16 宫格**预览；汇总审核卡稍后会自动更新。",
    )
    mid = mgr.send_image_message(receive_id, "open_id", str(grid_path))
    if mid:
        print(f"  -> [HUB] 已发单批预览图 message_id={mid} batch={batch_index}")
        return True
    mgr.send_text(
        receive_id,
        "open_id",
        f"⚠️ 第 {batch_index} 批预览图上传失败，请查看本地 `{grid_path.name}` 或稍后「补发分镜审核卡」。",
    )
    return False


def regenerate_storyboard_batch(topic: str, receive_id: str, batch_index: int):
    """
    用户打回某个批次 → 单批次重画 → 刷新审核卡。
    注意：此函数在 enqueue_job 的独立线程中执行，避免阻塞飞书 WebSocket。
    """
    try:
        state.set_status("STEP2_GENERATING", topic)
        msg = f"🔄 正在重新生成第 {batch_index} 批次的 16 宫格图，请稍候..."
        mgr.send_text(receive_id, "open_id", msg)

        # 运行单批次重画
        proc = subprocess.run(
            [PYTHON_BIN, "src/step2_comic_generator_v6.py", "--single-batch", str(batch_index)],
            cwd=str(BASE_DIR),
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "无详情")[-600:]
            mgr.send_text(receive_id, "open_id",
                          f"❌ 第 {batch_index} 批次重画失败：\n```\n{err}\n```")
            state.set_status("WAITING_STORYBOARD_APPROVAL", topic)
            return

        # 重画成功：先发单批预览（仅上传该批一张图）；汇总大卡延后发送，避免先等大图上传
        state.set_status("WAITING_STORYBOARD_APPROVAL", topic)
        run_id = get_current_run_id() or "unknown"
        _send_single_batch_grid_preview(receive_id, topic, batch_index, run_id)
        note = (
            f"\n\n_第 **{batch_index}** 批已重画；单批预览见上方图片消息，"
            f"完整操作仍以**本条汇总卡**为准。_"
        )

        def _deferred_summary_card():
            time.sleep(2.0)
            try:
                _send_fresh_storyboard_review_card(receive_id, topic, revision_note=note)
                mgr.send_text(
                    receive_id,
                    "open_id",
                    "📋 汇总「分镜宫格审核」卡片已更新（含全部批次按钮）。若仍看不到新图，请稍下拉会话。",
                )
            except Exception as ex:
                print(f"  -> [HUB] 延后汇总卡失败: {ex}")
                try:
                    mgr.send_text(
                        receive_id,
                        "open_id",
                        "⚠️ 汇总审核卡更新失败，请发「补发分镜审核卡」重试。",
                    )
                except Exception:
                    pass

        threading.Thread(target=_deferred_summary_card, daemon=True).start()

    except Exception as e:
        mgr.send_text(receive_id, "open_id", f"🚨 重画批次时异常：{e}")
        state.set_status("WAITING_STORYBOARD_APPROVAL", topic)


def continue_after_storyboard_approval(topic: str, receive_id: str):
    """
    审核通过后：Step2-B（裁切+高清）→ Step3（视频合成）。
    """
    run_id = get_current_run_id() or "unknown"
    stop_flag = PIPELINE_STOP_FLAGS.setdefault(run_id, threading.Event())
    card_holder = {"message_id": None}

    try:
        state.set_status("STEP2_GENERATING", topic)
        _send_or_patch_progress_card(
            receive_id,
            _build_progress_card(topic, run_id, "⏳ Step2-B 裁切高清中", 30, 100, detail="正在对宫格图进行裁切与 Real-ESRGAN 高清..."),
            card_holder
        )

        # Step2-B：裁切 + 高清
        proc = subprocess.run(
            [PYTHON_BIN, "src/step2_comic_generator_v6.py", "--phase", "slice-only"],
            cwd=str(BASE_DIR),
            env=dict(os.environ, PYTHONIOENCODING="utf-8", CHAIN_STEP3="1"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "无详情")[-1200:]
            _notify_step2_failed(
                receive_id, topic, run_id, card_holder,
                headline="❌ Step2-B 裁切高清失败",
                stderr_tail=err,
            )
            raise RuntimeError(f"Step2-B 失败：{err}")

        # 检查链式 Step3 是否已完成
        _chained_ok_file = RUNS_ROOT / run_id / "logs" / "step3_chained_ok.json"
        assets_now = _active_asset_paths()
        _chained_done = (
            _chained_ok_file.exists()
            and assets_now
            and assets_now["final_mp4"].exists()
        )
        if _chained_done:
            print("  -> [HUB] Step2-B 链式 Step3 已完成。")
            _chained_ok_file.unlink(missing_ok=True)
            state.set_status("COMPLETED", topic)
            _send_or_patch_progress_card(
                receive_id,
                _build_progress_card(topic, run_id, "✅ 全部完成！", 100, 100, detail="视频已落盘。"),
                card_holder
            )
            if assets_now and assets_now["final_mp4"].exists():
                _notify_step3_success_with_upload(
                    receive_id, assets_now["final_mp4"],
                    "🎉 分镜审核通过，视频合成完毕！"
                )
            return

        # 链式未完成 → 显式跑 Step3
        state.set_status("STEP3_ASSEMBLING", topic)
        _send_or_patch_progress_card(
            receive_id,
            _build_progress_card(topic, run_id, "⏳ Step3 视频合成中", 85, 100),
            card_holder
        )
        step3_proc = subprocess.run(
            [PYTHON_BIN, "src/step3_assembler_v6.py"],
            cwd=str(BASE_DIR),
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if step3_proc.returncode != 0:
            err3 = (step3_proc.stderr or step3_proc.stdout or "无详情")[-1200:]
            raise RuntimeError(f"Step3 失败：{err3}")

        assets_final = _active_asset_paths()
        if assets_final and assets_final["final_mp4"].exists():
            state.set_status("COMPLETED", topic)
            _send_or_patch_progress_card(
                receive_id,
                _build_progress_card(topic, run_id, "✅ 全部完成！", 100, 100),
                card_holder
            )
            _notify_step3_success_with_upload(
                receive_id, assets_final["final_mp4"],
                "🎉 分镜审核通过，视频合成完毕！"
            )
        else:
            state.set_status("ERROR", topic)
            mgr.send_text(receive_id, "open_id", "⚠️ Step3 运行结束但未检测到成片文件，请检查日志。")

    except Exception as e:
        print(f"  -> [HUB] continue_after_storyboard_approval 异常: {e}")
        failed_stage = "POST_APPROVAL_STEP3" if "Step3" in str(e) else "POST_APPROVAL_SLICE"
        save_last_error_context(topic, failed_stage, str(e))
        state.set_status("ERROR", topic)
        try:
            mgr.send_text(receive_id, "open_id", f"🚨 分镜通过后流水线中断：{e}")
        except Exception:
            pass


def _parse_storyboard_reject_batch(msg_clean: str):
    """解析「打回/重画第 N 批」类自然语言中的批次号；无法解析则返回 None。"""
    patterns = [
        r"打回第\s*(\d+)\s*(?:批|张)",
        r"第\s*(\d+)\s*(?:批|张)\s*(?:重画|重绘|重新生成|重新画|有问题)",
        r"(?:重画|重绘)\s*第\s*(\d+)\s*(?:批|张)",
    ]
    for pat in patterns:
        m = re.search(pat, msg_clean)
        if m:
            try:
                return int(m.group(1))
            except (ValueError, IndexError):
                continue
    return None


def preflight_story_ready(expected_topic: str = ""):
    """生产前置校验：确保剧本存在且与当前主题一致。"""
    a = _active_asset_paths()
    if not a:
        return False, "前置缺失：未检测到激活 Run-ID"
    full_story_path = a["full_story"]
    if not full_story_path.exists():
        return False, f"前置缺失：未找到剧本文件 {full_story_path}"
    try:
        data = json.loads(full_story_path.read_text(encoding="utf-8"))
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

# ── 错误恢复辅助函数 ──────────────────────────────────────────

def _send_error_recovery_card(receive_id: str, strategy: dict, step_name: str,
                                topic: str, error_text: str = "",
                                attempt: int = 1, auto_retry_remaining: int = 0) -> None:
    """向飞书推送错误恢复卡片（带重试/跳过按钮）"""
    try:
        run_id = get_current_run_id() or ""
        card = build_error_recovery_card(
            strategy, step_name, topic,
            error_text=error_text, attempt=attempt,
            auto_retry_remaining=auto_retry_remaining,
            run_id=run_id,
        )
        mgr.send_card(receive_id, "open_id", card)
    except Exception as e:
        print(f"  [WARN] 发送错误恢复卡片失败: {e}")


def _handle_step_error_with_recovery(receive_id: str, topic: str,
                                       step_name: str, error: Exception,
                                       failed_stage: str = "") -> None:
    """
    统一错误处理入口：
    1. 分类错误（瞬态/可重试/致命）
    2. 记录到全局错误上下文 + 文件（兼容旧逻辑）
    3. 推送飞书错误恢复卡片
    4. 设置状态为 ERROR
    """
    err_text = f"{type(error).__name__}: {error}"
    strategy = classify_error(step_name, err_text)

    # 保存上下文（error_recovery 的跨步骤共享存储）
    set_error_context(topic, step_name, strategy, err_text, failed_stage)
    # 同时保存到文件（兼容旧的 hub_old 读取方式）
    save_last_error_context(topic, failed_stage or step_name, err_text)

    state.set_status("ERROR", topic)

    # 推送恢复卡片
    _send_error_recovery_card(receive_id, strategy, step_name, topic, err_text)


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
# 任务队列与精准进程管理（全局串行）
# ================================================================
TASK_QUEUE: "queue.Queue[dict]" = queue.Queue()
PID_REGISTRY_FILE = BASE_DIR / "feishu" / "run_pid_registry.json"
PIPELINE_STOP_FLAGS: dict[str, threading.Event] = {}
RUN_LOCK = threading.Lock()
CURRENT_TASK_INFO: dict = {"running": False, "description": "", "open_id": "", "run_id": "", "topic": ""}

# 最近一次交互用户的 open_id（Hub 重启后推送「未完成项目」提醒）
LAST_OPERATOR_OPEN_ID_FILE = BASE_DIR / "feishu" / "last_operator_open_id.json"

_OPS_RETRY_JOB_DESC = {
    "step1": "断点续传 step1",
    "step2": "断点续传 step2",
    "step3": "断点续传 step3",
}

_UNFINISHED_RESUME_STATUSES = frozenset(
    {
        "GENERATING_SYNOPSIS",
        "WAITING_SYNOPSIS_APPROVAL",
        "GENERATING_VISUALS",
        "WAITING_CHARACTER_APPROVAL",
        "WAITING_STORYBOARD_APPROVAL",
        "STEP1_WRITING",
        "STEP1_READY",
        "STEP2_GENERATING",
        "STEP2_FAILED",
        "STEP2_SUCCESS",
        "STEP3_ASSEMBLING",
        "ERROR",
    }
)


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
    except Exception as e:
        print(f"[WARN] 持久化 open_id 失败: {e}")


def _load_last_operator_open_id() -> str:
    try:
        if LAST_OPERATOR_OPEN_ID_FILE.exists():
            return (
                json.loads(LAST_OPERATOR_OPEN_ID_FILE.read_text(encoding="utf-8")).get("open_id") or ""
            ).strip()
    except Exception:
        pass
    return ""


def _ops_retry_step_busy(step_name: str) -> bool:
    """同一 Step 断点续传是否已在执行或队列中（防重复点击）。"""
    sn = (step_name or "").lower().strip()
    needle = _OPS_RETRY_JOB_DESC.get(sn)
    if not needle:
        return False
    if CURRENT_TASK_INFO.get("running"):
        d = (CURRENT_TASK_INFO.get("description") or "").strip()
        if d == needle or needle in d:
            return True
    try:
        raw_q = getattr(TASK_QUEUE, "queue", None)
        if raw_q:
            for item in list(raw_q):
                if isinstance(item, dict) and (item.get("description") or "") == needle:
                    return True
    except Exception:
        pass
    return False


def _retry_hint_footer(step_num: int) -> str:
    return (
        f"\n\n👉 如需再次尝试，请稍后点击「重跑 Step {step_num}」"
        f"或发送 `/retry step{step_num}`。"
    )


def _step_num_from_name(step_name: str) -> int:
    return {"step1": 1, "step2": 2, "step3": 3}.get((step_name or "").lower().strip(), 1)


def _should_offer_resume_after_reconnect() -> tuple[bool, dict]:
    """Hub 启动后：是否需要推送「未完成项目」提醒。"""
    st = state.get_current_state()
    topic = (st.get("topic") or "").strip()
    status = st.get("status") or "IDLE"
    run_id = get_current_run_id() or ""
    ast = _run_assets_status()
    assets = ast.get("assets") or {} if ast.get("ok") else {}

    if status == "COMPLETED" and assets.get("final_mp4"):
        return False, {}

    if topic and status in _UNFINISHED_RESUME_STATUSES:
        return True, {"topic": topic, "status": status, "run_id": run_id}

    if run_id and ast.get("ok"):
        if assets.get("full_story") and not assets.get("final_mp4"):
            return True, {"topic": topic or "(请对照 Run-ID)", "status": status, "run_id": run_id}

    return False, {}


def send_resume_prompt_card(open_id: str, info: dict) -> None:
    """关机/断网/重启后：简要探针 + 引导运维面板。"""
    topic = info.get("topic", "未命名")
    run_id = info.get("run_id") or get_current_run_id() or "未知"
    status = info.get("status") or state.get_current_state().get("status", "IDLE")
    ast = _run_assets_status()
    assets = ast.get("assets", {}) if ast.get("ok") else {}
    s_count = ast.get("s_count", 0)
    readiness = (
        f"🎯 Run：`{run_id}`\n"
        f"📦 剧本：{'✅' if assets.get('full_story') else '⏳'}  "
        f"🎵 主音轨：{'✅' if assets.get('master_voice') else '⏳'}\n"
        f"🧩 蓝图：{'✅' if assets.get('narrative') else '⏳'}  "
        f"🖼️ 分镜：已产 {s_count} 张\n"
        f"🎬 成片：{'✅' if assets.get('final_mp4') else '⏳'}"
    )
    card = {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"content": "🔌 本机管线已重新连接飞书", "tag": "plain_text"}, "template": "orange"},
        "elements": [
            {
                "tag": "markdown",
                "content": (
                    f"检测到**可能有未完成的项目**（关机、断网或 Hub 重启后常见）。\n\n"
                    f"**主题**：【{topic}】\n"
                    f"**记录状态**：`{status}`\n\n"
                    f"{readiness}\n\n"
                    f"请先查看最新进度；若曾中断，可用运维「重跑 Step 1/2/3」断点续跑。"
                ),
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"content": "📊 查看最新进度", "tag": "plain_text"},
                        "type": "primary",
                        "value": {"action_type": "ops_status"},
                    },
                    {
                        "tag": "button",
                        "text": {"content": "稍后我自己查", "tag": "plain_text"},
                        "type": "default",
                        "value": {"action_type": "startup_resume_dismiss"},
                    },
                ],
            },
        ],
    }
    mgr.send_card(open_id, "open_id", card)


def _load_pid_registry() -> dict:
    try:
        if PID_REGISTRY_FILE.exists():
            return json.loads(PID_REGISTRY_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_pid_registry(reg: dict):
    try:
        PID_REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_REGISTRY_FILE.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[WARN] 写入 PID 注册表失败: {e}")


def _register_pid(run_id: str, pid: int):
    if not run_id or not pid:
        return
    with RUN_LOCK:
        reg = _load_pid_registry()
        rec = reg.get(run_id, {})
        pids = set(rec.get("pids", []))
        pids.add(int(pid))
        rec["pids"] = sorted(pids)
        rec["updated_at"] = time.time()
        reg[run_id] = rec
        _save_pid_registry(reg)


def _clear_run_pids(run_id: str):
    if not run_id:
        return
    with RUN_LOCK:
        reg = _load_pid_registry()
        if run_id in reg:
            del reg[run_id]
            _save_pid_registry(reg)


def _get_run_pids(run_id: str) -> list[int]:
    reg = _load_pid_registry()
    rec = reg.get(run_id, {})
    return [int(x) for x in rec.get("pids", []) if isinstance(x, int) or str(x).isdigit()]


def _kill_by_run_id(run_id: str) -> int:
    killed = 0
    for pid in _get_run_pids(run_id):
        try:
            p = psutil.Process(pid)
            if p.is_running():
                p.kill()
                killed += 1
        except Exception:
            continue
    _clear_run_pids(run_id)
    return killed


def _run_cmd_with_pid_tracking(
    cmd: list[str],
    cwd: Path,
    run_id: str,
    stop_flag: threading.Event | None = None,
    capture_output: bool = False,
    extra_env: dict | None = None,
):
    _env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if extra_env:
        _env.update(extra_env)
    popen_kwargs = {
        "cwd": str(cwd),
        "env": _env,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if capture_output:
        popen_kwargs["stdout"] = subprocess.PIPE
        popen_kwargs["stderr"] = subprocess.PIPE
    proc = subprocess.Popen(cmd, **popen_kwargs)
    _register_pid(run_id, proc.pid)
    while True:
        if stop_flag and stop_flag.is_set():
            try:
                proc.kill()
            except Exception:
                pass
            raise RuntimeError(f"任务已被中止: {' '.join(cmd)}")
        ret = proc.poll()
        if ret is not None:
            if ret != 0:
                out = ""
                if capture_output:
                    out = ((proc.stderr.read() if proc.stderr else "") or (proc.stdout.read() if proc.stdout else "") or "")[-1500:]
                raise subprocess.CalledProcessError(ret, cmd, output=out, stderr=out)
            if capture_output:
                out = proc.stdout.read() if proc.stdout else ""
                err = proc.stderr.read() if proc.stderr else ""
                return out, err
            return "", ""
        time.sleep(0.2)


def _run_cmd_with_auto_retry(
    cmd: list[str],
    cwd: Path,
    run_id: str,
    step_name: str,
    receive_id: str = "",
    topic: str = "",
    stop_flag: threading.Event | None = None,
    capture_output: bool = False,
    extra_env: dict | None = None,
) -> tuple:
    """
    带自动重试的子进程执行器。

    对 TRANSIENT 级错误自动重试（指数退避），RETRYABLE/FATAL 直接抛出让上层处理。
    重试期间通过飞书推送进度提示。
    """
    import time as _time
    last_err_text = ""

    for attempt in range(1, 4):
        try:
            return _run_cmd_with_pid_tracking(
                cmd, cwd, run_id,
                stop_flag=stop_flag,
                capture_output=capture_output,
                extra_env=extra_env,
            )
        except subprocess.CalledProcessError as e:
            last_err_text = (e.stderr or e.output or str(e))[-1200:]
            strategy = classify_error(step_name, last_err_text)

            if strategy.get("severity") == ErrorSeverity.TRANSIENT:
                max_auto = strategy.get("max_auto_retry", 3)
                if attempt < max_auto:
                    wait = 2 ** attempt
                    detail = strategy.get("user_msg", "正在自动重试…")
                    print(f"  [AUTO-RETRY] {step_name} 瞬时故障（第{attempt}次），{wait}s后重试…")
                    if receive_id:
                        try:
                            mgr.send_text(receive_id, "open_id",
                                f"{strategy.get('title', '🔄 自动重试')}\n{detail}\n第 {attempt}/{max_auto} 次重试，等待 {wait} 秒…")
                        except Exception:
                            pass
                    _time.sleep(wait)
                    continue
                else:
                    # 自动重试耗尽 → 降级为 RETRYABLE；恢复卡由外层 _handle_step_error_with_recovery 统一推送，避免重复
                    print(f"  [AUTO-RETRY] {step_name} 自动重试 {attempt} 次后仍未恢复")
                    strategy["severity"] = ErrorSeverity.RETRYABLE
            raise  # 非瞬态 或 重试耗尽 → 向上抛出

        except RuntimeError as e:
            if "已被中止" in str(e):
                raise
            last_err_text = str(e)[-1200:]
            # 中止类错误不重试
            raise

        except Exception as e:
            last_err_text = f"{type(e).__name__}: {e}"[-1200:]
            strategy = classify_error(step_name, last_err_text)
            if strategy.get("severity") == ErrorSeverity.TRANSIENT:
                wait = 2 ** attempt
                print(f"  [AUTO-RETRY] {step_name} 通用瞬时故障（第{attempt}次），{wait}s后重试…")
                if receive_id:
                    try:
                        mgr.send_text(receive_id, "open_id",
                            f"🔄 {strategy.get('title', '自动重试')}\n第 {attempt}/3 次重试…")
                    except Exception:
                        pass
                _time.sleep(wait)
                continue
            raise

    raise RuntimeError(f"{step_name} 自动重试耗尽: {last_err_text}")


def _pipeline_worker_loop():
    while True:
        task = TASK_QUEUE.get()
        if task is None:
            TASK_QUEUE.task_done()
            continue
        try:
            fn = task.get("fn")
            args = task.get("args", ())
            kwargs = task.get("kwargs", {})
            CURRENT_TASK_INFO.update({
                "running": True,
                "description": task.get("description", ""),
                "open_id": task.get("open_id", ""),
                "run_id": task.get("run_id", ""),
                "topic": task.get("topic", ""),
            })
            if callable(fn):
                # 全自动用户不跑单步：若 Step2 已成功但缺成片，在任意排队任务前先补跑 Step3。
                # 排除 retry_single_step，避免与「重试 Step3」重复执行或与「重试 Step2」意图冲突。
                if fn is not retry_single_step:
                    oid = (task.get("open_id") or "").strip() or None
                    need0, _, _ = _step3_orphan_recovery_needed()
                    if need0:
                        _recover_step3_if_orphaned(oid, wait_for_lock=True)
                fn(*args, **kwargs)
        except Exception as e:
            print(f"[WORKER] 任务执行异常: {e}")
        finally:
            CURRENT_TASK_INFO.update({
                "running": False,
                "description": "",
                "open_id": "",
                "run_id": "",
                "topic": "",
            })
            TASK_QUEUE.task_done()


threading.Thread(target=_pipeline_worker_loop, daemon=True).start()


def _async_send_text(open_id: str, content: str):
    def _job():
        try:
            mgr.send_text(open_id, "open_id", content)
        except Exception as e:
            print(f"[WARN] 异步发送文本失败: {e}")
    threading.Thread(target=_job, daemon=True).start()


def _normalize_action_value(raw_val):
    """容错解析卡片 action.value，避免回调线程因 JSON 异常中断。"""
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


# ── 大纲卡片：成片时长草稿（秒）持久化，避免「对话框说了 6 分钟却没写入」──
SYNOPSIS_CARD_MID_FILE = BASE_DIR / "feishu" / "synopsis_card_mid.txt"
SYNOPSIS_DURATION_DRAFT_FILE = BASE_DIR / "feishu" / "synopsis_duration_draft.json"
_DURATION_SEC_MIN = 30
_DURATION_SEC_MAX = 7200  # 与 story_planner 上限 120 分钟一致


def _clamp_duration_seconds(sec: int) -> int:
    return max(_DURATION_SEC_MIN, min(_DURATION_SEC_MAX, int(sec)))


def _snap_seconds_to_step(sec: int, step: int = 30) -> int:
    return _clamp_duration_seconds(int(round(sec / step) * step))


def _initial_seconds_from_minutes(minutes: float) -> int:
    sec = int(round(float(minutes) * 60))
    return _snap_seconds_to_step(sec)


def _format_duration_cn(sec: int) -> str:
    sec = _clamp_duration_seconds(sec)
    m, s = divmod(sec, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h} 小时 {m} 分 {s} 秒"
    return f"{m} 分 {s} 秒"


def _seconds_to_minutes_float(sec: int) -> float:
    return round(sec / 60.0, 4)


def _load_synopsis_duration_drafts() -> dict:
    try:
        if SYNOPSIS_DURATION_DRAFT_FILE.exists():
            return json.loads(SYNOPSIS_DURATION_DRAFT_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [WARN] 读取 synopsis_duration_draft 失败: {e}")
    return {"drafts": {}}


def _save_synopsis_duration_draft(open_id: str, topic: str, seconds: int) -> None:
    seconds = _clamp_duration_seconds(int(seconds))
    data = _load_synopsis_duration_drafts()
    drafts = data.setdefault("drafts", {})
    drafts[open_id] = {"topic": topic, "seconds": seconds, "ts": time.time()}
    try:
        SYNOPSIS_DURATION_DRAFT_FILE.parent.mkdir(parents=True, exist_ok=True)
        SYNOPSIS_DURATION_DRAFT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"  [WARN] 写入 synopsis_duration_draft 失败: {e}")


def _load_synopsis_duration_draft(open_id: str, topic: str, fallback_seconds: int) -> int:
    data = _load_synopsis_duration_drafts()
    rec = (data.get("drafts") or {}).get(open_id)
    if isinstance(rec, dict) and rec.get("topic") == topic and rec.get("seconds") is not None:
        return _clamp_duration_seconds(int(rec["seconds"]))
    return _clamp_duration_seconds(int(fallback_seconds))


def _clear_synopsis_duration_draft(open_id: str) -> None:
    data = _load_synopsis_duration_drafts()
    drafts = data.setdefault("drafts", {})
    if open_id in drafts:
        del drafts[open_id]
        try:
            SYNOPSIS_DURATION_DRAFT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


def _apply_duration_to_temp_synopsis(minutes: float) -> None:
    path = BASE_DIR / "feishu" / "temp_synopsis.json"
    if not path.exists():
        return
    try:
        synopsis_data = json.loads(path.read_text(encoding="utf-8"))
        synopsis_data["duration"] = float(minutes)
        path.write_text(json.dumps(synopsis_data, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"  [WARN] 回写 temp_synopsis duration 失败: {e}")


def _sync_synopsis_duration_from_draft(open_id: str, topic: str) -> None:
    """将卡片上选的时长写入 temp_synopsis.json（供定妆 / 剧本扩写读取）。"""
    path = BASE_DIR / "feishu" / "temp_synopsis.json"
    if not path.exists():
        return
    try:
        synopsis_data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    fb = _initial_seconds_from_minutes(float(synopsis_data.get("duration", 1.25)))
    sec = _load_synopsis_duration_draft(open_id, topic, fb)
    _apply_duration_to_temp_synopsis(_seconds_to_minutes_float(sec))


def build_synopsis_approval_card(topic: str, synopsis_data: dict, duration_sec: int) -> dict:
    duration_sec = _clamp_duration_seconds(int(duration_sec))
    mo = _seconds_to_minutes_float(duration_sec)
    industry = synopsis_data.get("industry_rules") or []
    industry_md = ""
    if industry:
        bullets = "\n".join(f"- {x}" for x in industry[:24])
        industry_md = f"\n\n**📌 行业潜规则**\n{bullets}"
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"content": f"📖 剧情大纲：{topic}", "tag": "plain_text"}, "template": "purple"},
        "elements": [
            {"tag": "markdown", "content": f"**🕰️ 时代**：{synopsis_data.get('era')}\n**👤 身份**：{synopsis_data.get('identity')}{industry_md}"},
            {"tag": "hr"},
            {"tag": "markdown", "content": synopsis_data.get("synopsis", "")},
            {"tag": "hr"},
            {"tag": "markdown", "content": (
                "**⏱️ 成片目标时长**\n"
                "点 **−30 秒** / **+30 秒** 微调，或选下方常用档位；"
                "点 **确认时长并生成定妆照** 后，将把当前选择写入生产管线。\n\n"
                f"**当前选择：**{_format_duration_cn(duration_sec)}（约 **{mo:g}** 分钟）"
            )},
            {"tag": "action", "actions": [
                {"tag": "button", "text": {"content": "−30 秒", "tag": "plain_text"}, "type": "default",
                 "value": {"action_type": "synopsis_duration_delta", "topic": topic, "delta": -30}},
                {"tag": "button", "text": {"content": "+30 秒", "tag": "plain_text"}, "type": "default",
                 "value": {"action_type": "synopsis_duration_delta", "topic": topic, "delta": 30}},
            ]},
            {"tag": "action", "actions": [
                {"tag": "button", "text": {"content": "3 分钟", "tag": "plain_text"}, "type": "default",
                 "value": {"action_type": "synopsis_duration_preset", "topic": topic, "minutes": 3}},
                {"tag": "button", "text": {"content": "6 分钟", "tag": "plain_text"}, "type": "primary",
                 "value": {"action_type": "synopsis_duration_preset", "topic": topic, "minutes": 6}},
                {"tag": "button", "text": {"content": "10 分钟", "tag": "plain_text"}, "type": "default",
                 "value": {"action_type": "synopsis_duration_preset", "topic": topic, "minutes": 10}},
                {"tag": "button", "text": {"content": "15 分钟", "tag": "plain_text"}, "type": "default",
                 "value": {"action_type": "synopsis_duration_preset", "topic": topic, "minutes": 15}},
            ]},
            {"tag": "hr"},
            {"tag": "markdown", "content": "**请选择下一步操作：**"},
            {"tag": "action", "actions": [
                {"tag": "button", "text": {"content": "✅ 确认时长并生成定妆照", "tag": "plain_text"}, "type": "primary",
                 "value": {"action_type": "approve_synopsis", "topic": topic}},
                {"tag": "button", "text": {"content": "✏️ 我要修改大纲", "tag": "plain_text"}, "type": "default",
                 "value": {"action_type": "request_revise_synopsis", "topic": topic}},
            ]},
            {"tag": "action", "actions": [
                {"tag": "button", "text": {"content": "🚫 取消项目，重新选题", "tag": "plain_text"}, "type": "danger",
                 "value": {"action_type": "cancel_project", "topic": topic}},
            ]},
        ],
    }


def _patch_synopsis_approval_card(open_id: str, message_id: str, topic: str) -> bool:
    path = BASE_DIR / "feishu" / "temp_synopsis.json"
    if not path.exists() or not message_id:
        return False
    try:
        synopsis_data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    fb = _initial_seconds_from_minutes(float(synopsis_data.get("duration", 1.25)))
    sec = _load_synopsis_duration_draft(open_id, topic, fb)
    card = build_synopsis_approval_card(topic, synopsis_data, sec)
    return mgr.update_card(message_id, card)


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
    run_id = get_current_run_id() or "unknown"
    stop_flag = PIPELINE_STOP_FLAGS.setdefault(run_id, threading.Event())
    card_holder = {"message_id": None}
    try:
        clear_last_error_context()
        ok, reason = preflight_story_ready(topic)
        if not ok:
            raise RuntimeError(
                f"{reason}\n请先点击「重写剧本 + 全部重画」或重新生成定妆照后再开始生产。"
            )
        _send_or_patch_progress_card(
            receive_id,
            _build_progress_card(topic, run_id, "⏳ 排队已开始，准备执行 Step1", 0, 100),
            card_holder
        )
        msg1 = f"🚀 任务已进入全局队列并开始执行\n主题: 【{topic}】\nRun-ID: {run_id}"
        mgr.send_text(receive_id, "open_id", msg1)
        state.set_status("STEP1_WRITING", topic)
        
        # 1. Step1：phase2 → pseudo_srt + master_voice；phase3 → narrative_v6_final（Step2 依赖后者）
        print(f"  -> [HUB] 运行 step1_writer_v6.py --phase phase2 ...")
        _run_cmd_with_auto_retry(
            [PYTHON_BIN, "src/step1_writer_v6.py", "--phase", "phase2"],
            BASE_DIR, run_id, step_name="tts",
            receive_id=receive_id, topic=topic, stop_flag=stop_flag,
        )
        print(f"  -> [HUB] 运行 step1_writer_v6.py --phase phase3 ...")
        _run_cmd_with_auto_retry(
            [PYTHON_BIN, "src/step1_writer_v6.py", "--phase", "phase3"],
            BASE_DIR, run_id, step_name="step1",
            receive_id=receive_id, topic=topic, stop_flag=stop_flag,
        )
        assets = _active_asset_paths()
        if not assets:
            raise RuntimeError("Step1 后未检测到激活 Run-ID。")
        if not assets["pseudo_srt"].exists():
            raise RuntimeError(f"Step1 结束后未找到 pseudo_srt：{assets['pseudo_srt']}")
        if not assets["master_voice"].exists():
            raise RuntimeError(f"Step1 结束后未找到主音轨：{assets['master_voice']}")
        if not assets["narrative"].exists():
            raise RuntimeError(f"Step1 结束后未找到叙事蓝图：{assets['narrative']}")
        _send_or_patch_progress_card(
            receive_id,
            _build_progress_card(topic, run_id, "✅ Step1 完成 (主音轨生成完毕)", 20, 100),
            card_holder
        )
        
        state.set_status("STEP2_GENERATING", topic)
        # 2. Step2-A：仅生成 16 宫格大图（不做裁切/高清），完成后推送飞书审核卡
        print(f"  -> [HUB] 运行 step2_comic_generator_v6.py --phase grid-only ...")
        assets_before = _active_asset_paths()
        total_shots = 0
        if assets_before and assets_before["narrative"].exists():
            try:
                _n = json.loads(assets_before["narrative"].read_text(encoding="utf-8"))
                total_shots = len((_n.get("timeline") or []))
            except Exception:
                total_shots = 0

        _send_or_patch_progress_card(
            receive_id,
            _build_progress_card(topic, run_id, "⏳ Step2-A 宫格生图中", 20, 100, detail="正在逐批生成 16 宫格预览图..."),
            card_holder
        )
        step2a_proc = subprocess.Popen(
            [PYTHON_BIN, "src/step2_comic_generator_v6.py", "--phase", "grid-only"],
            cwd=str(BASE_DIR),
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _register_pid(run_id, step2a_proc.pid)

        # 后台吞管道
        _s2a_stdout: list = []
        _s2a_stderr: list = []
        def _drain_pipe(pipe, buf):
            try:
                for ln in pipe:
                    buf.append(ln)
            except Exception:
                pass
        threading.Thread(target=_drain_pipe, args=(step2a_proc.stdout, _s2a_stdout), daemon=True).start()
        threading.Thread(target=_drain_pipe, args=(step2a_proc.stderr, _s2a_stderr), daemon=True).start()

        last_tick = 0.0
        while True:
            if stop_flag.is_set():
                try:
                    step2a_proc.kill()
                except Exception:
                    pass
                raise RuntimeError("任务已被中止（Step2-A）")
            ret = step2a_proc.poll()
            now = time.time()
            if now - last_tick >= 1.0:
                last_tick = now
                assets_live = _active_asset_paths()
                grids_done = 0
                if assets_live and assets_live["storyboards_dir"].exists():
                    grids_done = len(list(assets_live["storyboards_dir"].glob("grid_batch_*.png")))
                total_batches = (total_shots + 15) // 16 if total_shots else 1
                denom = max(1, total_batches)
                pct = int((grids_done / denom) * 50)
                _send_or_patch_progress_card(
                    receive_id,
                    _build_progress_card(
                        topic, run_id,
                        f"⏳ Step2-A 宫格生图中: {grids_done}/{denom} 批",
                        20 + pct, 100,
                        detail=f"⏳ 宫格生成中: {generate_progress_bar(grids_done, denom)}  {grids_done}/{denom} 批"
                    ),
                    card_holder
                )
            if ret is not None:
                if ret != 0:
                    err2 = (
                        "".join(_s2a_stderr[-200:])
                        or "".join(_s2a_stdout[-200:])
                        or ""
                    )[-1200:]
                    # exit code 2 = 部分批次失败但非致命
                    if ret == 2:
                        print(f"  -> [HUB] Step2-A 部分批次失败（exit=2），继续推送审核卡。")
                    else:
                        _notify_step2_failed(
                            receive_id, topic, run_id, card_holder,
                            headline="❌ Step2-A 宫格生图失败",
                            stderr_tail=err2,
                        )
                        raise RuntimeError(f"Step2-A 失败：{err2}")
                break
            time.sleep(0.2)

        assets = _active_asset_paths()
        if not assets or (not assets["master_voice"].exists()) or (not assets["narrative"].exists()):
            raise RuntimeError("Step2-A 结束后检测到 Step1 产物缺失，无法继续。")

        # 验证宫格图是否存在
        grid_files = list(assets["storyboards_dir"].glob("grid_batch_*.png"))
        if not grid_files:
            raise RuntimeError("Step2-A 结束后未生成任何 grid_batch_*.png 宫格图。")

        _send_or_patch_progress_card(
            receive_id,
            _build_progress_card(topic, run_id, "📬 宫格已生成，正在推送审核卡...", 70, 100),
            card_holder
        )

        # 推送分镜审核卡，流水线在此暂停，等待用户审核
        run_storyboard_review(topic, receive_id)
        print(f"  -> [HUB] Step2-A 完成，审核卡已推送，等待用户审批。")
        # 函数在此返回；后续由 continue_after_storyboard_approval() 接手

    except Exception as e:
        failed_stage = state.get_current_state().get("status", "UNKNOWN")
        print(f"  -> [HUB] 流水线异常: {type(e).__name__}: {e}")
        err_snip = f"{type(e).__name__}: {e}".lower()
        step_for_classify = "pipeline"
        if failed_stage == "STEP1_WRITING" or "phase2" in err_snip or "step1_writer" in err_snip:
            step_for_classify = "step1"
        elif failed_stage in ("STEP2_GENERATING", "STEP2_FAILED") or "step2_comic" in err_snip:
            step_for_classify = "step2"
        elif failed_stage == "STEP3_ASSEMBLING" or "step3_assembler" in err_snip:
            step_for_classify = "step3"
        _handle_step_error_with_recovery(
            receive_id, topic, step_for_classify, e, failed_stage=failed_stage,
        )
    finally:
        _clear_run_pids(run_id)
        PIPELINE_STOP_FLAGS.pop(run_id, None)

def run_synopsis_setup(topic: str, receive_id: str, feedback: str = "", duration: float = 1.25):
    """第一重审批：只生成大纲并推给用户看（不触碰 V6 源代码）"""
    try:
        clear_last_error_context()
        from openai import OpenAI
        from src.style_config import LLM_API_KEY, LLM_BASE_URL, MODEL_LLM
        mgr.send_text(receive_id, "open_id", f"🧠 正在为【{topic}】构思剧情大纲..." if not feedback else f"🔄 收到反馈，正在为您重新修改大纲...")
        state.set_status("GENERATING_SYNOPSIS", topic)

        # 改稿时沿用上一份大纲卡片里确认的成片时长（避免回退成默认 1.25）
        if feedback:
            try:
                prev_path = BASE_DIR / "feishu" / "temp_synopsis.json"
                if prev_path.exists():
                    prev = json.loads(prev_path.read_text(encoding="utf-8"))
                    if prev.get("duration") is not None:
                        duration = float(prev["duration"])
            except Exception:
                pass
        
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
        synopsis_data["duration"] = duration  # 初始值；老板可在卡片上微调后由「确认」回写

        with open(BASE_DIR / "feishu" / "temp_synopsis.json", "w", encoding="utf-8") as f:
            json.dump(synopsis_data, f, ensure_ascii=False)

        init_sec = _initial_seconds_from_minutes(float(duration))
        _save_synopsis_duration_draft(receive_id, topic, init_sec)
        synopsis_card = build_synopsis_approval_card(topic, synopsis_data, init_sec)
        new_mid = mgr.send_card(receive_id, "open_id", synopsis_card)
        if new_mid:
            try:
                SYNOPSIS_CARD_MID_FILE.write_text(new_mid, encoding="utf-8")
            except Exception as e:
                print(f"  [WARN] 写入 synopsis_card_mid: {e}")
        add_to_history(receive_id, "assistant", f"【系统已推送剧情大纲卡片，主题：{topic}，等待审批】")
        state.set_status("WAITING_SYNOPSIS_APPROVAL", topic)

    except Exception as e:
        print(f"  -> [HUB] 大纲生成异常: {type(e).__name__}: {e}")
        _handle_step_error_with_recovery(
            receive_id, topic, "llm", e, failed_stage="GENERATING_SYNOPSIS",
        )

def run_visual_setup(topic: str, receive_id: str, regen_stage: str = None, regen_supporting_role_id: str = None):
    """
    点选主题后：先生成骨架脚本和人设图，然后发给老板看。
    regen_supporting_role_id：仅重画 cast_registry 中该 role_id 的配角三视图（子进程 ref_generator --regen-supporting）。
    """
    try:
        clear_last_error_context()
        regen_sup = (str(regen_supporting_role_id).strip() if regen_supporting_role_id else "")
        # 尝试还原老板选的时长
        duration = 1.25
        try:
            with open(BASE_DIR / "feishu" / "temp_synopsis.json", "r", encoding="utf-8") as f:
                duration = json.load(f).get("duration", 1.25)
        except: pass

        assets = _active_asset_paths()
        full_story_path = assets["full_story"] if assets else (BASE_DIR / "data" / "scripts" / "full_story_v6.json")
        if regen_sup:
            if not full_story_path.exists():
                raise RuntimeError("本地无剧本 full_story_v6.json，无法单独重画配角。")
            msg_pre = f"🎨 正在为配角单独重绘三视图（`{regen_sup}`），约 1-2 分钟…"
        elif regen_stage == "__all__":
            if not full_story_path.exists():
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

        # 关键策略（2026-04-30）：禁用“同主题自动复用旧剧本”。
        # 目的：保证“审批通过/修改后的最新大纲”一定参与长文案生成，
        # 避免误复用历史 full_story_v6.json 导致改稿不生效。
        need_generate = True

        if need_generate:
            if regen_sup:
                print(f"  -> [HUB] 运行 ref_generator.py --regen-supporting {regen_sup} …")
                ref_cmd = [PYTHON_BIN, "src/ref_generator.py", "--topic", topic, "--regen-supporting", regen_sup]
                r1 = subprocess.run(ref_cmd, cwd=str(BASE_DIR),
                                    env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                                    capture_output=True, text=True, encoding="utf-8", errors="replace")
                if r1.returncode != 0:
                    err = (r1.stderr or r1.stdout or "无详情")[-600:]
                    raise RuntimeError(f"配角定妆重绘失败 (exit={r1.returncode}):\n{err}")
            else:
                # __all__ = 保留剧本重画全部；普通 regen_stage = 重画单阶段；None = 全新生成
                if not regen_stage:
                    print(f"  -> [HUB] 运行 run_story_planner_with_mock.py (duration={duration})...")
                    cmd = [PYTHON_BIN, "feishu/run_story_planner_with_mock.py", "--topic", topic, "--duration", str(duration)]
                    r0 = subprocess.run(cmd, cwd=str(BASE_DIR),
                                        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                                        capture_output=True, text=True, encoding="utf-8", errors="replace")
                    if r0.returncode != 0:
                        err = (r0.stderr or r0.stdout or "无详情")[-600:]
                        raise RuntimeError(f"剧本生成失败 (exit={r0.returncode}):\n{err}")

                    # 🛡️ 二次校验：即使 returncode=0，也必须确认文件真的落盘了。
                    # 背景：story_planner 早期版本在 LLM 失败时只 return（退出码仍为 0），
                    # 导致 hub 误判为成功，继续跑定妆照，最后在"通过"环节才暴露报错。
                    assets_after_plan = _active_asset_paths()
                    full_story_after_plan = assets_after_plan["full_story"] if assets_after_plan else full_story_path
                    if not full_story_after_plan.exists():
                        partial_log = (r0.stderr or r0.stdout or "无日志")[-800:]
                        raise RuntimeError(
                            f"剧本进程虽返回 0，但 full_story_v6.json 未写入磁盘，"
                            f"流水线中止。\n子进程日志:\n{partial_log}"
                        )

                # 防重复触发：全新生成分支（regen_stage=None）下，story_planner_v6 已在阶段二末尾触发定妆照。
                # 此处仅在“重画分支”下再调用 ref_generator，避免出现“生成两遍 + 第一版被归档”的现象。
                if regen_stage:
                    print(f"  -> [HUB] 运行定妆照生成引擎 ref_generator.py...")
                    ref_cmd = [PYTHON_BIN, "src/ref_generator.py", "--topic", topic, "--role", "protagonist"]
                    # __all__ 不传 --stage，让 ref_generator 重画全部阶段
                    if regen_stage != "__all__":
                        ref_cmd += ["--stage", regen_stage]
                    r1 = subprocess.run(ref_cmd, cwd=str(BASE_DIR),
                                        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                                        capture_output=True, text=True, encoding="utf-8", errors="replace")
                    if r1.returncode != 0:
                        err = (r1.stderr or r1.stdout or "无详情")[-600:]
                        raise RuntimeError(f"定妆照生成失败 (exit={r1.returncode}):\n{err}")
            
            print(f"  -> [HUB] 剧本与图片生成完毕，准备上传飞书...")
        
        # 定妆照卡片：优先 ref_display_slots（主角阶段 + 配角）；否则回退按固定四阶段扫描
        stages = {
            "child": {"name": "幼年期", "btn": "👶 重画幼年"},
            "youth": {"name": "青年期", "btn": "🧑 重画青年"},
            "middle": {"name": "中年期", "btn": "👤 重画中年"},
            "elderly": {"name": "老年期", "btn": "👴 重画老年"},
        }
        stage_order = ["child", "youth", "middle", "elderly"]

        expected_stages = set()
        ref_slots = []
        story_for_card = None
        try:
            assets_after_ref = _active_asset_paths()
            full_story_after_ref = assets_after_ref["full_story"] if assets_after_ref else full_story_path
            if full_story_after_ref.exists():
                with open(full_story_after_ref, "r", encoding="utf-8") as _f:
                    _story_data = json.load(_f)
                story_for_card = _story_data if isinstance(_story_data, dict) else None
                _master = _story_data.get("master_design", {}) if isinstance(_story_data, dict) else {}
                _detected = _master.get("detected_life_stages", [])
                if isinstance(_detected, list):
                    expected_stages = {s for s in _detected if s in stages}
                if not expected_stages:
                    _anchors = _master.get("physical_char_anchors", {})
                    if isinstance(_anchors, dict):
                        expected_stages = {k for k in _anchors.keys() if k in stages}
                ref_slots = _master.get("ref_display_slots") or []
        except Exception as _e:
            print(f"  -> [HUB] 读取定妆展示清单失败: {_e}")

        card = {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"content": f"🎬 定妆照审批：{topic}", "tag": "plain_text"}, "template": "blue"},
            "elements": [],
        }

        generated_stages = []

        if ref_slots:
            card["elements"].append(
                {
                    "tag": "markdown",
                    "content": "**定妆参考图**（主角各阶段 + 配角）。**English display names** 已写入剧本，后续分镜将沿用。",
                }
            )
            for slot in ref_slots:
                if not isinstance(slot, dict):
                    continue
                abs_p = slot.get("abs_path") or ""
                if not abs_p:
                    continue
                char_img_path = Path(abs_p)
                kind = slot.get("kind", "")
                name_en = slot.get("display_name_en", "") or "Character"
                stage_key = slot.get("stage", "")
                rid = slot.get("role_id", "")
                if not char_img_path.is_file():
                    print(f"  -> [HUB] 缺失文件: {char_img_path}")
                    card["elements"].append(
                        {
                            "tag": "markdown",
                            "content": f"⚠️ **{name_en}**：未找到 `{char_img_path}`。",
                        }
                    )
                    continue
                if kind == "protagonist":
                    st_name = stages.get(stage_key, {}).get("name", stage_key)
                    caption_md = f"🎭 **{name_en}** · 主角 · {st_name}（`{stage_key}`）"
                    if stage_key in stages:
                        generated_stages.append(stage_key)
                else:
                    caption_md = f"🎭 **{name_en}** · 配角 · `role_id={rid}`"
                print(f"  -> [HUB] 正在上传定妆图: {name_en} ({kind})...")
                img_key = mgr.upload_image(str(char_img_path))
                if img_key:
                    card["elements"].append({"tag": "markdown", "content": caption_md})
                    card["elements"].append(
                        {
                            "tag": "img",
                            "img_key": img_key,
                            "alt": {"content": name_en[:40], "tag": "plain_text"},
                        }
                    )
                else:
                    card["elements"].append(
                        {
                            "tag": "markdown",
                            "content": f"⚠️ **{name_en}** 上传飞书失败，请本地查看：`{char_img_path}`",
                        }
                    )
        else:
            card["elements"].append(
                {"tag": "markdown", "content": "**您的主角人生阶段定妆照已出炉，请过目：**"}
            )
            for stage_key in stage_order:
                stage_info = stages[stage_key]
                stage_name = stage_info["name"]
                refs_root = assets_after_ref["refs_dir"] if assets_after_ref else (BASE_DIR / "data" / "refs")
                char_img_path = refs_root / f"protagonist_{stage_key}" / "triple_view.png"
                if char_img_path.exists():
                    print(f"  -> [HUB] 正在上传 {stage_name} 定妆照...")
                    img_key = mgr.upload_image(str(char_img_path))
                    if img_key:
                        print(f"  -> [HUB] 上传成功: {img_key}")
                        card["elements"].append({"tag": "markdown", "content": f"👤 **{stage_name}**"})
                        card["elements"].append(
                            {"tag": "img", "img_key": img_key, "alt": {"content": stage_name, "tag": "plain_text"}}
                        )
                        generated_stages.append(stage_key)
                    else:
                        print(f"  -> [HUB] 警告: {stage_name} 上传失败 (img_key 为空)")
                        card["elements"].append(
                            {
                                "tag": "markdown",
                                "content": f"⚠️ **{stage_name}** 图片上传失败，请在电脑 `{char_img_path}` 直接查看。",
                            }
                        )
                        generated_stages.append(stage_key)
                else:
                    if stage_key in expected_stages:
                        print(f"  -> [HUB] 异常: {stage_name} 属于应涉及阶段但未找到文件。")
                        card["elements"].append(
                            {
                                "tag": "markdown",
                                "content": f"⚠️ **{stage_name}**：该阶段应已生成，但当前未在 `{char_img_path}` 找到文件，请重画该阶段。",
                            }
                        )
                    else:
                        print(f"  -> [HUB] 智能裁剪: {stage_name} 剧本未涉及，跳过展示。")
                        card["elements"].append(
                            {
                                "tag": "markdown",
                                "content": f"💡 **{stage_name}**：系统根据剧情跨度判断本次剧本未涉及该阶段，因此未生成此照片。",
                            }
                        )
        
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

        sup_regen_actions = []
        _sup_candidates: list[tuple[str, str]] = []
        if ref_slots:
            for slot in ref_slots:
                if not isinstance(slot, dict) or slot.get("kind") != "supporting":
                    continue
                _rid = str(slot.get("role_id") or "").strip()
                if not _rid:
                    continue
                _sup_candidates.append((_rid, str(slot.get("display_name_en") or _rid)))
        elif story_for_card:
            _md = story_for_card.get("master_design") or {}
            _cr = _md.get("cast_registry") or {}
            _pa = _md.get("physical_char_anchors") or {}
            for _sup in _cr.get("supporting") or []:
                if not isinstance(_sup, dict):
                    continue
                _rid = str(_sup.get("role_id") or "").strip()
                if not _rid:
                    continue
                if not _pa.get(f"supporting_{_rid}"):
                    continue
                _sup_candidates.append((_rid, str(_sup.get("display_name_en") or _rid)))
        _seen_sup_btn = set()
        for _rid, _nm in _sup_candidates:
            if _rid in _seen_sup_btn:
                continue
            _seen_sup_btn.add(_rid)
            _nm_short = _nm[:20] + ("…" if len(_nm) > 20 else "")
            sup_regen_actions.append({
                "tag": "button",
                "text": {"content": f"🎭 重画配角：{_nm_short}", "tag": "plain_text"},
                "type": "default",
                "value": {"action_type": "regen_supporting", "topic": topic, "supporting_role_id": _rid},
            })
        if sup_regen_actions:
            card["elements"].append({"tag": "action", "actions": sup_regen_actions})

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
        if regen_stage or regen_sup:  # 单阶段 / __all__ / 配角重画：尝试原地刷新旧卡片，不刷屏
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
        print(f"  -> [HUB] 定妆照生成异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        _handle_step_error_with_recovery(
            receive_id, topic, "image", e, failed_stage="GENERATING_VISUALS",
        )

# ── 事件处理器 ──────────────────────────────────────────────

def do_card_action(data: P2CardActionTrigger) -> P2CardActionTriggerResponse:
    """处理用户在卡片上点击按钮的动作"""
    try:
        open_id = data.event.operator.open_id
        _remember_operator_open_id(open_id)
        action_val = _normalize_action_value(data.event.action.value)
        card_message_id = ""
        try:
            if getattr(data.event, "message", None) is not None:
                card_message_id = getattr(data.event.message, "message_id", "") or ""
        except Exception:
            card_message_id = ""
            
        action_type = action_val.get("action_type")
        topic = action_val.get("topic", "")

        if action_type == "select_topic":
            curr_state = state.get_current_state()
            if curr_state["status"] not in ["IDLE", "WAITING_TOPIC", "COMPLETED"]:
                status_map = {
                    "GENERATING_SYNOPSIS": "🧠 正在编写大纲", "WAITING_SYNOPSIS_APPROVAL": "👀 等待您审批大纲",
                    "GENERATING_VISUALS": "🎨 正在绘制三阶段定妆照", "WAITING_CHARACTER_APPROVAL": "👀 等待您审批定妆图",
                    "WAITING_STORYBOARD_APPROVAL": "🧩 分镜宫格已发，等待您打回批次或全部通过",
                    "STEP1_WRITING": "✍️ 正在规划分镜",
                    "STEP1_READY": "✅ Step1 已完成（可开始 Step2）",
                    "STEP2_GENERATING": "🖼️ 正在生成全量原画",
                    "STEP2_FAILED": "❌ Step2 失败（已阻断进入 Step3）",
                    "STEP2_SUCCESS": "✅ Step2 通过（可进入 Step3）",
                    "STEP3_ASSEMBLING": "🎬 正在剪辑合成",
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

            enqueue_job(open_id, f"生成大纲: {topic}", run_synopsis_setup, topic, open_id, "", 1.25)
            return P2CardActionTriggerResponse({"toast": {"type": "info", "content": f"已选中：{topic}，正在生成大纲..."}})

        elif action_type == "synopsis_duration_delta":
            curr_state = state.get_current_state()
            if curr_state.get("status") != "WAITING_SYNOPSIS_APPROVAL" or curr_state.get("topic") != topic:
                return P2CardActionTriggerResponse({"toast": {"type": "warning", "content": "当前不在大纲审批阶段或主题不一致。"}})
            try:
                delta = int(action_val.get("delta", 0))
            except (TypeError, ValueError):
                delta = 0
            path = BASE_DIR / "feishu" / "temp_synopsis.json"
            if not path.exists():
                return P2CardActionTriggerResponse({"toast": {"type": "error", "content": "找不到大纲文件。"}})
            try:
                synopsis_data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return P2CardActionTriggerResponse({"toast": {"type": "error", "content": "大纲文件损坏。"}})
            fb = _initial_seconds_from_minutes(float(synopsis_data.get("duration", 1.25)))
            sec = _load_synopsis_duration_draft(open_id, topic, fb)
            sec = _clamp_duration_seconds(sec + delta)
            _save_synopsis_duration_draft(open_id, topic, sec)
            mid = card_message_id or (SYNOPSIS_CARD_MID_FILE.read_text(encoding="utf-8").strip() if SYNOPSIS_CARD_MID_FILE.exists() else "")
            if mid and _patch_synopsis_approval_card(open_id, mid, topic):
                return P2CardActionTriggerResponse({"toast": {"type": "success", "content": f"已设为 {_format_duration_cn(sec)}"}})
            return P2CardActionTriggerResponse({"toast": {"type": "success", "content": f"已设为 {_format_duration_cn(sec)}（若卡片未刷新请展开最新消息）"}})

        elif action_type == "synopsis_duration_preset":
            curr_state = state.get_current_state()
            if curr_state.get("status") != "WAITING_SYNOPSIS_APPROVAL" or curr_state.get("topic") != topic:
                return P2CardActionTriggerResponse({"toast": {"type": "warning", "content": "当前不在大纲审批阶段或主题不一致。"}})
            try:
                minutes = float(action_val.get("minutes", 6))
            except (TypeError, ValueError):
                minutes = 6.0
            sec = _snap_seconds_to_step(int(round(minutes * 60)))
            _save_synopsis_duration_draft(open_id, topic, sec)
            mid = card_message_id or (SYNOPSIS_CARD_MID_FILE.read_text(encoding="utf-8").strip() if SYNOPSIS_CARD_MID_FILE.exists() else "")
            if mid and _patch_synopsis_approval_card(open_id, mid, topic):
                return P2CardActionTriggerResponse({"toast": {"type": "success", "content": f"已设为 {_format_duration_cn(sec)}"}})
            return P2CardActionTriggerResponse({"toast": {"type": "success", "content": f"已设为 {_format_duration_cn(sec)}（若卡片未刷新请展开最新消息）"}})
            
        elif action_type == "approve_synopsis":
            if os.path.exists(BASE_DIR / "feishu" / "temp_synopsis.json"):
                _sync_synopsis_duration_from_draft(open_id, topic)
                enqueue_job(open_id, f"生成定妆照: {topic}", run_visual_setup, topic, open_id)
                return P2CardActionTriggerResponse({"toast": {"type": "success", "content": "已写入成片时长，正在生成定妆照..."}})
            else:
                return P2CardActionTriggerResponse({"toast": {"type": "error", "content": "找不到大纲文件，请重新生成。"}})

        elif action_type == "request_revise_synopsis":
            _async_send_text(open_id, "✏️ 请直接说出您的修改意见，我会立刻重新生成大纲。\n例如：开头太平淡，要有更强的悬念感")
            return P2CardActionTriggerResponse({"toast": {"type": "info", "content": "请在对话框输入修改意见"}})

        elif action_type == "approve_visuals":
            curr_state = state.get_current_state()
            status = curr_state.get("status") or "IDLE"
            run_topic = (curr_state.get("topic") or topic or "").strip()

            busy_prod = status in [
                "STEP1_WRITING",
                "STEP1_READY",
                "STEP2_GENERATING",
                "STEP2_FAILED",
                "STEP3_ASSEMBLING",
                "WAITING_STORYBOARD_APPROVAL",
            ]
            if busy_prod:
                return P2CardActionTriggerResponse(
                    {
                        "toast": {
                            "type": "warning",
                            "content": "已在视频生产流程中，请勿重复点击。发送「状态」查看进度。",
                        }
                    }
                )

            if status == "COMPLETED":
                return P2CardActionTriggerResponse(
                    {"toast": {"type": "info", "content": "当前项目已完成。如需新项目请重新选题。"}}
                )

            if status not in ["WAITING_CHARACTER_APPROVAL"]:
                assets_chk = _active_asset_paths()
                cand_topic = run_topic or (topic or "").strip()
                ok_pf, _reason_pf = preflight_story_ready(cand_topic)
                narrative_started = bool(
                    assets_chk
                    and assets_chk.get("narrative")
                    and assets_chk["narrative"].exists()
                )
                if ok_pf and status in ["IDLE", "ERROR"]:
                    if narrative_started:
                        return P2CardActionTriggerResponse(
                            {
                                "toast": {
                                    "type": "warning",
                                    "content": "检测到管线曾启动（已有分镜蓝图 narrative_v6_final）。请发送「状态」查看进度，或使用运维面板「重跑 Step 1/2/3」。",
                                }
                            }
                        )
                    disk_topic = cand_topic
                    try:
                        if assets_chk and assets_chk.get("full_story") and assets_chk["full_story"].exists():
                            fs_data = json.loads(
                                assets_chk["full_story"].read_text(encoding="utf-8")
                            )
                            disk_topic = (
                                (fs_data.get("metadata") or {}).get("topic") or disk_topic
                            )
                    except Exception:
                        pass
                    if disk_topic:
                        state.set_status("WAITING_CHARACTER_APPROVAL", disk_topic)
                        run_topic = disk_topic
                        status = "WAITING_CHARACTER_APPROVAL"

                if status not in ["WAITING_CHARACTER_APPROVAL"]:
                    return P2CardActionTriggerResponse(
                        {
                            "toast": {
                                "type": "warning",
                                "content": "任务已被分配，当前已处于生产中或任务已丢弃，请勿重复点击",
                            }
                        }
                    )

            curr_state = state.get_current_state()
            run_topic = (curr_state.get("topic") or topic or "").strip()
            ok, reason = preflight_story_ready(run_topic)
            if not ok:
                _async_send_text(open_id, f"⚠️ 无法开始生产：{reason}")
                return P2CardActionTriggerResponse({"toast": {"type": "error", "content": "前置素材不完整，请先重写剧本或重画"}})
            enqueue_job(open_id, f"全量生产: {run_topic}", run_project_pipeline, run_topic, open_id)
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
            enqueue_job(open_id, f"重写剧本并重画: {topic}", run_visual_setup, topic, open_id)
            return P2CardActionTriggerResponse({"toast": {"type": "info", "content": "收到，正在打回重写大纲并全部重画..."}})

        elif action_type == "regen_stage":
            stage = action_val.get("stage")
            enqueue_job(open_id, f"重画阶段 {stage}: {topic}", run_visual_setup, topic, open_id, stage)
            return P2CardActionTriggerResponse({"toast": {"type": "info", "content": f"收到，正在单独重画：{stage}"}})

        elif action_type == "regen_all_visuals_only":
            # 保留剧本，重画全部三阶段定妆照（__all__ 是内部标记，不传 --stage 给 ref_generator）
            enqueue_job(open_id, f"重画全部定妆照: {topic}", run_visual_setup, topic, open_id, "__all__")
            return P2CardActionTriggerResponse({"toast": {"type": "info", "content": "保留剧本，正在重画全部定妆照..."}})

        elif action_type == "regen_supporting":
            rid = str(action_val.get("supporting_role_id") or "").strip()
            if not rid:
                return P2CardActionTriggerResponse({"toast": {"type": "error", "content": "缺少配角标识（supporting_role_id）。"}})
            enqueue_job(
                open_id,
                f"重画配角 {rid}: {topic}",
                run_visual_setup,
                topic,
                open_id,
                None,
                regen_supporting_role_id=rid,
            )
            return P2CardActionTriggerResponse({"toast": {"type": "info", "content": f"收到，正在单独重绘配角：{rid}"}})

        elif action_type == "reject_storyboard_batch":
            curr_state = state.get_current_state()
            if curr_state.get("status") != "WAITING_STORYBOARD_APPROVAL":
                return P2CardActionTriggerResponse({"toast": {"type": "warning", "content": "当前不在分镜审核阶段。"}})
            try:
                batch_index = int(action_val.get("batch_index", 0))
            except (TypeError, ValueError):
                return P2CardActionTriggerResponse({"toast": {"type": "error", "content": "批次号无效。"}})
            if batch_index < 1:
                return P2CardActionTriggerResponse({"toast": {"type": "error", "content": "批次号无效。"}})
            enqueue_job(
                open_id,
                f"重画分镜批次 {batch_index}: {topic}",
                regenerate_storyboard_batch,
                topic,
                open_id,
                batch_index,
            )
            return P2CardActionTriggerResponse({"toast": {"type": "info", "content": f"收到，正在重新生成第 {batch_index} 批次宫格图..."}})

        elif action_type == "approve_storyboards":
            curr_state = state.get_current_state()
            if curr_state.get("status") != "WAITING_STORYBOARD_APPROVAL":
                return P2CardActionTriggerResponse({"toast": {"type": "warning", "content": "当前不在分镜审核阶段（若正在重画某批次，请等完成后再点通过）。"}})
            _async_send_text(open_id, "✅ 分镜审核通过！开始切分高清 + 视频合成，请耐心等待...")
            enqueue_job(open_id, f"切分高清+合成: {topic}", continue_after_storyboard_approval, topic, open_id)
            return P2CardActionTriggerResponse({"toast": {"type": "success", "content": "审核通过，开始裁切高清与视频合成！"}})

        elif action_type == "cancel_project":
            rid = get_current_run_id() or ""
            PIPELINE_STOP_FLAGS.setdefault(rid, threading.Event()).set()
            killed = _kill_by_run_id(rid) if rid else 0
            state.set_status("IDLE", "")
            _clear_synopsis_duration_draft(open_id)
            _async_send_text(open_id, f"🗑️ 已取消当前项目并重置系统（精准终止 {killed} 个进程）。发送「换一批」可重新获取新主题。")
            return P2CardActionTriggerResponse({"toast": {"type": "success", "content": "项目已取消，系统已重置。"}})

        elif action_type == "confirm_new_project":
            new_topic = action_val.get("topic", "")
            operator_id = action_val.get("open_id", open_id)
            rid = get_current_run_id() or ""
            PIPELINE_STOP_FLAGS.setdefault(rid, threading.Event()).set()
            _kill_by_run_id(rid)
            state.set_status("IDLE", "")
            if new_topic:
                enqueue_job(operator_id, f"新项目大纲: {new_topic}", run_synopsis_setup, new_topic, operator_id, "", 1.25)
            return P2CardActionTriggerResponse({"toast": {"type": "success", "content": f"已放弃旧项目，正在为「{new_topic}」生成大纲..."}})

        elif action_type == "resume_project":
            # 继续上一个项目：什么都不用做，提示一下
            curr_state = state.get_current_state()
            _async_send_text(open_id, f"▶️ 好的，继续推进【{curr_state['topic']}】。发送「状态」可查看当前进度。")
            return P2CardActionTriggerResponse({"toast": {"type": "info", "content": "继续上一个项目。"}})

        elif action_type == "do_nothing":
            return P2CardActionTriggerResponse({"toast": {"type": "info", "content": "收到，请耐心等待。"}})
            
        elif action_type == "request_ideas":
            import ideator
            threading.Thread(target=ideator.send_morning_topics, args=(open_id,)).start()
            return P2CardActionTriggerResponse({"toast": {"type": "success", "content": "为您搜罗一批新点子中..."}})
            
        elif action_type == "restart_backend":
            _async_send_text(open_id, "🔄 已收到重启请求：后台即将重启，约 10-20 秒恢复。")
            schedule_self_restart_notice(open_id, reason="card_button")
            return P2CardActionTriggerResponse({"toast": {"type": "info", "content": "即将杀死后台进程并冷启动..."}})

        elif action_type in ("retry_failed_stage", "retry_failed_step"):
            curr_state = state.get_current_state()
            if curr_state["status"] != "ERROR":
                return P2CardActionTriggerResponse({"toast": {"type": "warning", "content": "当前不在错误态，无需重试。"}})

            err_ctx = load_last_error_context()
            retry_topic = topic or err_ctx.get("topic") or curr_state.get("topic", "")
            failed_stage = err_ctx.get("failed_stage", "UNKNOWN")
            if not retry_topic:
                return P2CardActionTriggerResponse({"toast": {"type": "error", "content": "缺少项目主题，请重新发起项目。"}})

            if failed_stage in ["GENERATING_SYNOPSIS", "WAITING_SYNOPSIS_APPROVAL"]:
                enqueue_job(open_id, f"重试大纲: {retry_topic}", run_synopsis_setup, retry_topic, open_id, "", 1.25)
            elif failed_stage in ["GENERATING_VISUALS", "WAITING_CHARACTER_APPROVAL"]:
                enqueue_job(open_id, f"重试定妆照: {retry_topic}", run_visual_setup, retry_topic, open_id)
            elif failed_stage in ["POST_APPROVAL_SLICE", "POST_APPROVAL_STEP3"]:
                enqueue_job(
                    open_id,
                    f"重试切分/合成: {retry_topic}",
                    continue_after_storyboard_approval,
                    retry_topic,
                    open_id,
                )
            elif failed_stage in ["STEP1_WRITING", "STEP2_GENERATING", "STEP2_FAILED", "STEP3_ASSEMBLING"]:
                enqueue_job(open_id, f"重试全量生产: {retry_topic}", run_project_pipeline, retry_topic, open_id)
            else:
                # 兜底：未知阶段时，从全量生产入口继续
                enqueue_job(open_id, f"重试全量生产: {retry_topic}", run_project_pipeline, retry_topic, open_id)
            _async_send_text(
                open_id,
                f"🔁 已受理重试请求\n主题：{retry_topic}\n失败环节：{failed_stage}\n"
                f"Run-ID：{get_current_run_id() or 'unknown'}\n"
                "任务已入队，执行结果将继续回传。"
            )
            return P2CardActionTriggerResponse({"toast": {"type": "success", "content": f"收到，正在重试失败环节（{failed_stage}）..."}})

        elif action_type == "skip_tts_continue":
            return P2CardActionTriggerResponse({
                "toast": {
                    "type": "info",
                    "content": "「跳过音频」已关闭。请点「重试 Step1」或运维卡「重跑 Step1」。",
                }
            })

        elif action_type == "skip_stage":
            curr_state = state.get_current_state()
            if curr_state["status"] != "ERROR":
                return P2CardActionTriggerResponse({"toast": {"type": "warning", "content": "当前不在错误态。"}})
            err_ctx = load_last_error_context()
            retry_topic = (topic or action_val.get("topic") or err_ctx.get("topic") or curr_state.get("topic", "")).strip()
            failed_stage = (err_ctx.get("failed_stage") or "").strip()
            if failed_stage not in ("STEP2_GENERATING", "STEP2_FAILED"):
                return P2CardActionTriggerResponse(
                    {"toast": {"type": "warning", "content": "仅适用于 Step2 宫格生图阶段失败，且磁盘上已有部分宫格时。"}}
                )
            if not retry_topic:
                return P2CardActionTriggerResponse({"toast": {"type": "error", "content": "缺少项目主题。"}})
            enqueue_job(
                open_id,
                f"跳过分镜生图(已有宫格): {retry_topic}",
                _try_skip_step2_grid_to_review,
                retry_topic,
                open_id,
            )
            return P2CardActionTriggerResponse({"toast": {"type": "success", "content": "已排队：尝试用现有宫格推送审核卡。"}})

        elif action_type == "ops_status":
            curr_state = state.get_current_state()
            enqueue_job(
                open_id,
                "刷新状态看板",
                send_status_card,
                open_id,
                curr_state.get("topic", "暂无"),
                curr_state.get("status", "IDLE"),
                send_ack=False
            )
            return P2CardActionTriggerResponse({"toast": {"type": "info", "content": "已刷新最新进度。"}})

        elif action_type == "ops_retry_step1":
            target_run_id = action_val.get("run_id", "").strip()
            if target_run_id in ("", "未初始化"):
                return P2CardActionTriggerResponse({"toast": {"type": "error", "content": "当前批次未初始化，请先创建任务。"}})
            if target_run_id:
                ok, reason = switch_active_run(target_run_id)
                if not ok:
                    return P2CardActionTriggerResponse({"toast": {"type": "error", "content": f"切换失败: {reason}"}})
            if _ops_retry_step_busy("step1"):
                return P2CardActionTriggerResponse(
                    {
                        "toast": {
                            "type": "warning",
                            "content": "Step1 已在执行或排队中，请耐心等待；完成后会推送成功或失败结果。",
                        }
                    }
                )
            enqueue_job(open_id, "断点续传 step1", retry_single_step, "step1", open_id, send_ack=False)
            return P2CardActionTriggerResponse({"toast": {"type": "success", "content": "Step1 已加入队列。"}})

        elif action_type == "ops_retry_step2":
            target_run_id = action_val.get("run_id", "").strip()
            if target_run_id in ("", "未初始化"):
                return P2CardActionTriggerResponse({"toast": {"type": "error", "content": "当前批次未初始化，请先创建任务。"}})
            if target_run_id:
                ok, reason = switch_active_run(target_run_id)
                if not ok:
                    return P2CardActionTriggerResponse({"toast": {"type": "error", "content": f"切换失败: {reason}"}})
            if _ops_retry_step_busy("step2"):
                return P2CardActionTriggerResponse(
                    {
                        "toast": {
                            "type": "warning",
                            "content": "Step2 已在执行或排队中，请耐心等待；完成后会推送成功或失败结果。",
                        }
                    }
                )
            enqueue_job(open_id, "断点续传 step2", retry_single_step, "step2", open_id, send_ack=False)
            return P2CardActionTriggerResponse({"toast": {"type": "success", "content": "Step2 已加入队列。"}})

        elif action_type == "ops_retry_step3":
            target_run_id = action_val.get("run_id", "").strip()
            if target_run_id in ("", "未初始化"):
                return P2CardActionTriggerResponse({"toast": {"type": "error", "content": "当前批次未初始化，请先创建任务。"}})
            if target_run_id:
                ok, reason = switch_active_run(target_run_id)
                if not ok:
                    return P2CardActionTriggerResponse({"toast": {"type": "error", "content": f"切换失败: {reason}"}})
            if _ops_retry_step_busy("step3"):
                return P2CardActionTriggerResponse(
                    {
                        "toast": {
                            "type": "warning",
                            "content": "Step3 已在执行或排队中，请耐心等待；完成后会推送成功或失败结果。",
                        }
                    }
                )
            enqueue_job(open_id, "断点续传 step3", retry_single_step, "step3", open_id, send_ack=False)
            return P2CardActionTriggerResponse({"toast": {"type": "success", "content": "Step3 已加入队列。"}})

        elif action_type == "startup_resume_dismiss":
            return P2CardActionTriggerResponse(
                {"toast": {"type": "info", "content": "好的。随时发送「状态」或 /status 可打开运维面板。"}}
            )

        elif action_type == "ops_abort_run":
            target_run_id = action_val.get("run_id", "").strip() or (get_current_run_id() or "")
            if not target_run_id:
                return P2CardActionTriggerResponse({"toast": {"type": "error", "content": "未提供可中止的 Run-ID。"}})
            PIPELINE_STOP_FLAGS.setdefault(target_run_id, threading.Event()).set()
            killed = _kill_by_run_id(target_run_id)
            _async_send_text(open_id, f"🛑 已执行紧急中止：{target_run_id}（精准终止 {killed} 个进程）。")
            return P2CardActionTriggerResponse({"toast": {"type": "warning", "content": f"已中止 {target_run_id}"}})

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
        "WAITING_STORYBOARD_APPROVAL": "🧩 分镜宫格已发，等待您打回某批或全部通过",
        "STEP1_WRITING": "✍️ [生产阶段 1/3] 正在规划分镜和视觉脚本...",
        "STEP1_READY": "✅ [生产阶段 1/3] 已就绪：主音轨 + 分镜蓝图完成，可执行 Step2 生图",
        "STEP2_GENERATING": "🖼️ [生产阶段 2/3] 仅容器生图执行中 (耗时较长)...",
        "STEP2_FAILED": "❌ [生产阶段 2/3] 生图失败，已阻断进入 Step3（请重跑 Step2）",
        "STEP2_SUCCESS": "✅ [生产阶段 2/3] 生图通过，等待进入 Step3",
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
    
    run_probe = _run_assets_status()
    run_id = run_probe.get("run_id") or "未初始化"
    assets = run_probe.get("assets", {})
    s_count = run_probe.get("s_count", 0)
    readiness = (
        f"🎯 Run-ID：`{run_id}`\n"
        f"📦 剧本：{'✅' if assets.get('full_story') else '⏳'}  "
        f"🎵 主音轨：{'✅' if assets.get('master_voice') else '⏳'}\n"
        f"🧩 蓝图：{'✅' if assets.get('narrative') else '⏳'}  "
        f"🖼️ S_016：{'✅' if assets.get('s_016') else '⏳'}（已产 {s_count} 张）\n"
        f"🎬 成片：{'✅' if assets.get('final_mp4') else '⏳'}"
    )
    queue_len = TASK_QUEUE.qsize()
    queued_preview = []
    try:
        # 只读预览，不修改队列
        raw_q = list(getattr(TASK_QUEUE, "queue", []))
        for idx, item in enumerate(raw_q[:3], start=1):
            desc = ""
            if isinstance(item, dict):
                desc = str(item.get("description") or item.get("topic") or "待执行任务").strip()
            else:
                desc = "待执行任务"
            queued_preview.append(f"{idx}) {desc}")
    except Exception:
        queued_preview = []
    if CURRENT_TASK_INFO.get("running"):
        running_desc = CURRENT_TASK_INFO.get("description") or (CURRENT_TASK_INFO.get("topic") or "未知任务")
        queue_status = f"🚦 队列状态：当前正在运行: [{running_desc}] | 队列中等待: {queue_len} 个任务"
    else:
        queue_status = "🚦 队列状态：🟢 当前系统空闲，算力待命中。"
    queue_detail = f"**队列预览（前3项）**\n" + ("\n".join(queued_preview) if queued_preview else "（空）")

    if status in ["IDLE", "COMPLETED", "WAITING_TOPIC"]:
        card["elements"].append({"tag": "markdown", "content": f"**📍 当前状态**：{human_status}\n\n💡 当前没有正在进行的项目，您可以开启新的旅程。"})
        card["elements"].append({"tag": "hr"})
        card["elements"].append({"tag": "markdown", "content": f"**运行探针**\n{readiness}\n\n{queue_status}\n\n{queue_detail}"})
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
        card["elements"].append({"tag": "hr"})
        card["elements"].append({"tag": "markdown", "content": f"**运行探针**\n{readiness}\n\n{queue_status}\n\n{queue_detail}"})
        
        actions = []
        if status == "ERROR":
            actions.append({"tag": "button", "text": {"content": "🔁 重试失败环节", "tag": "plain_text"}, "type": "primary", "value": {"action_type": "retry_failed_stage", "topic": topic}})
            actions.append({"tag": "button", "text": {"content": "🔄 强制重启代码后台", "tag": "plain_text"}, "type": "default", "value": {"action_type": "restart_backend"}})
        # 注意：生产中不显示"耐心等待"按钮，系统默认继续运行，用户只能选择放弃
        actions.append({"tag": "button", "text": {"content": "🚫 放弃并终止此项目", "tag": "plain_text"}, "type": "danger", "value": {"action_type": "cancel_project", "topic": topic}})
        card["elements"].append({"tag": "action", "actions": actions})

    # 运维按钮组（统一放底部；拆成两行：避免单组按钮过多被客户端截断）
    card["elements"].append({"tag": "hr"})
    card["elements"].append({
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {"content": "查看最新进度", "tag": "plain_text"},
                "type": "default",
                "value": {"action_type": "ops_status"},
            },
            {
                "tag": "button",
                "text": {"content": "重跑 Step 1 (分镜/音轨)", "tag": "plain_text"},
                "type": "primary",
                "value": {"action_type": "ops_retry_step1", "run_id": run_id},
            },
            {
                "tag": "button",
                "text": {"content": "重跑 Step 2 (生图)", "tag": "plain_text"},
                "type": "default",
                "value": {"action_type": "ops_retry_step2", "run_id": run_id},
            },
        ],
    })
    card["elements"].append({
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {"content": "重跑 Step 3 (合成)", "tag": "plain_text"},
                "type": "default",
                "value": {"action_type": "ops_retry_step3", "run_id": run_id},
            },
            {
                "tag": "button",
                "text": {"content": "紧急中止该任务", "tag": "plain_text"},
                "type": "danger",
                "value": {"action_type": "ops_abort_run", "run_id": run_id},
            },
        ],
    })
        
    mgr.send_card(open_id, "open_id", card)


def generate_progress_bar(current: int, total: int, length: int = 20) -> str:
    total = max(1, int(total))
    current = max(0, min(int(current), total))
    filled = int(length * current / total)
    bar = "█" * filled + "░" * (length - filled)
    pct = int((current / total) * 100)
    return f"[{bar}] {pct}%"


def _build_progress_card(topic: str, run_id: str, status_text: str, current: int, total: int, detail: str = "") -> dict:
    progress = generate_progress_bar(current, total)
    content = (
        f"**🎬 项目**：{topic or '未命名'}\n"
        f"**🧪 Run-ID**：`{run_id or '未初始化'}`\n"
        f"**📍状态**：{status_text}\n"
        f"**📊进度**：{progress}"
    )
    if detail:
        content += f"\n\n{detail}"
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"content": "🛠️ 运维控制台（原地刷新）", "tag": "plain_text"}, "template": "blue"},
        "elements": [{"tag": "markdown", "content": content}],
    }


def _send_or_patch_progress_card(open_id: str, card: dict, holder: dict):
    mid = holder.get("message_id")
    if mid:
        ok = mgr.update_card(mid, card)
        if ok:
            return
    new_mid = mgr.send_card(open_id, "open_id", card)
    if new_mid:
        holder["message_id"] = new_mid


def switch_active_run(target_run_id: str):
    target = (RUNS_ROOT / target_run_id).resolve()
    if not target.exists() or not target.is_dir():
        return False, f"历史批次不存在：{target_run_id}"
    CURRENT_RUN_FILE.parent.mkdir(parents=True, exist_ok=True)
    CURRENT_RUN_FILE.write_text(
        json.dumps({"run_id": target_run_id}, ensure_ascii=False),
        encoding="utf-8"
    )
    return True, "ok"


def _try_skip_step2_grid_to_review(topic: str, receive_id: str) -> None:
    """Step2 宫格失败但已有部分 grid 时：直接推送分镜审核卡。"""
    topic_use = ""
    try:
        clear_last_error_context()
        topic_use = (topic or "").strip() or (state.get_current_state().get("topic") or "").strip()
        assets = _active_asset_paths()
        if not assets:
            mgr.send_text(receive_id, "open_id", "❌ 无激活批次，无法跳过分镜阶段。")
            state.set_status("ERROR", topic_use)
            return
        sb = assets.get("storyboards_dir")
        grids = sorted(sb.glob("grid_batch_*.png")) if sb and sb.exists() else []
        if not grids:
            mgr.send_text(
                receive_id,
                "open_id",
                "❌ 当前没有任何宫格图，无法跳过；请先修复生图或点「重试」。",
            )
            state.set_status("ERROR", topic_use)
            return
        state.set_status("STEP2_GENERATING", topic_use)
        run_storyboard_review(topic_use, receive_id)
        mgr.send_text(
            receive_id,
            "open_id",
            f"✅ 已跳过剩余生图：已用现有 {len(grids)} 个批次推送分镜审核卡。",
        )
    except Exception as e:
        _handle_step_error_with_recovery(
            receive_id,
            topic_use or topic,
            "step2",
            e,
            failed_stage="STEP2_FAILED",
        )


def retry_single_step(step_name: str, open_id: str):
    try:
        assets = _active_asset_paths()
        if not assets:
            mgr.send_text(open_id, "open_id", "❌ 未检测到激活 Run-ID，请先执行完整任务初始化。")
            return
        run_id = get_current_run_id() or "unknown"
        stop_flag = PIPELINE_STOP_FLAGS.setdefault(run_id, threading.Event())
        step = (step_name or "").lower().strip()
        if step == "step1":
            if not assets.get("full_story") or not assets["full_story"].exists():
                mgr.send_text(
                    open_id,
                    "open_id",
                    "❌ 无法执行 Step1：当前批次缺少 `full_story_v6.json`（需先完成定妆与剧本生成）。",
                )
                return
            topic_for = (state.get_current_state().get("topic") or "").strip()
            try:
                fs_data = json.loads(assets["full_story"].read_text(encoding="utf-8"))
                mt = (fs_data.get("metadata") or {}).get("topic", "")
                if mt:
                    topic_for = str(mt).strip()
            except Exception:
                pass
            state.set_status("STEP1_WRITING", topic_for)
            mgr.send_text(
                open_id,
                "open_id",
                f"🔁 正在执行 Step1：phase2（主音轨+pseudo_srt）→ phase3（narrative 蓝图）…\nRun-ID: `{run_id}`",
            )
            _run_cmd_with_pid_tracking(
                [PYTHON_BIN, "src/step1_writer_v6.py", "--phase", "phase2"],
                BASE_DIR,
                run_id,
                stop_flag=stop_flag,
            )
            _run_cmd_with_pid_tracking(
                [PYTHON_BIN, "src/step1_writer_v6.py", "--phase", "phase3"],
                BASE_DIR,
                run_id,
                stop_flag=stop_flag,
            )
            assets2 = _active_asset_paths() or {}
            ok_step1 = (
                assets2.get("pseudo_srt")
                and assets2["pseudo_srt"].exists()
                and assets2.get("master_voice")
                and assets2["master_voice"].exists()
                and assets2.get("narrative")
                and assets2["narrative"].exists()
            )
            if ok_step1:
                state.set_status("STEP1_READY", topic_for)
                mgr.send_text(
                    open_id,
                    "open_id",
                    "✅ Step1 已完成（主音轨、pseudo_srt、narrative_v6_final 已就绪）。\n"
                    "👉 下一步请点击卡片「重跑 Step 2 (生图)」继续。",
                )
            else:
                state.set_status("ERROR", topic_for)
                mgr.send_text(
                    open_id,
                    "open_id",
                    "⚠️ Step1 进程已结束，但未检测到完整产物，请查看本机终端日志或重试。",
                )
            return
        if step == "step2":
            if not assets["narrative"].exists():
                mgr.send_text(open_id, "open_id", "❌ 无法重试 Step2：当前批次缺失 `narrative_v6_final.json`，请先执行 Step1。")
                return
            topic_for = state.get_current_state().get("topic", "")
            report = _read_step2_report(run_id)
            phase = str(report.get("phase") or "").lower()
            gate_ok, gate_reason = _validate_step2_gate(run_id)
            total_from_report = int(report.get("total_shots", 0) or 0)
            generated_from_report = int(report.get("generated_shots", 0) or 0)
            incomplete_outputs = total_from_report > 0 and generated_from_report < total_from_report
            sb_dir = assets.get("storyboards_dir")
            grids = sorted(sb_dir.glob("grid_batch_*.png")) if sb_dir and sb_dir.exists() else []
            has_s = bool(sb_dir and sb_dir.exists() and any(sb_dir.glob("S_*.png")))

            state.set_status("STEP2_GENERATING", topic_for)

            if gate_ok or incomplete_outputs:
                if incomplete_outputs:
                    mgr.send_text(
                        open_id,
                        "open_id",
                        (
                            "🔁 检测到 Step2 产物不完整（"
                            f"{generated_from_report}/{total_from_report}），"
                            "将执行完整 Step2（宫格重算→裁切→高清）补齐缺失批次…\n"
                            f"Run-ID: `{run_id}`"
                        ),
                    )
                else:
                    mgr.send_text(
                        open_id,
                        "open_id",
                        f"🔁 门禁已通过；将执行完整 Step2（清空分镜并重算宫格→裁切→高清）…\nRun-ID: `{run_id}`",
                    )
                out2, err2 = _run_cmd_with_pid_tracking(
                    [PYTHON_BIN, "src/step2_comic_generator_v6.py"],
                    BASE_DIR,
                    run_id,
                    stop_flag=stop_flag,
                    capture_output=True,
                )
                if out2:
                    print(out2)
                if err2:
                    print(err2)
            elif grids and phase == "slice-only":
                mgr.send_text(
                    open_id,
                    "open_id",
                    f"🔁 重试 Step2-B（裁切+高清）…\nRun-ID: `{run_id}`",
                )
                out2, err2 = _run_cmd_with_pid_tracking(
                    [PYTHON_BIN, "src/step2_comic_generator_v6.py", "--phase", "slice-only"],
                    BASE_DIR,
                    run_id,
                    stop_flag=stop_flag,
                    extra_env={"CHAIN_STEP3": "1"},
                    capture_output=True,
                )
                if out2:
                    print(out2)
                if err2:
                    print(err2)
            elif grids and has_s and phase != "grid-only":
                mgr.send_text(open_id, "open_id", f"🔁 重试 Step2-B（裁切+高清）…\nRun-ID: `{run_id}`")
                out2, err2 = _run_cmd_with_pid_tracking(
                    [PYTHON_BIN, "src/step2_comic_generator_v6.py", "--phase", "slice-only"],
                    BASE_DIR,
                    run_id,
                    stop_flag=stop_flag,
                    extra_env={"CHAIN_STEP3": "1"},
                    capture_output=True,
                )
                if out2:
                    print(out2)
                if err2:
                    print(err2)
            else:
                mgr.send_text(open_id, "open_id", f"🔁 重试 Step2-A（仅宫格生图）…\nRun-ID: `{run_id}`")
                out2, err2 = _run_cmd_with_pid_tracking(
                    [PYTHON_BIN, "src/step2_comic_generator_v6.py", "--phase", "grid-only"],
                    BASE_DIR,
                    run_id,
                    stop_flag=stop_flag,
                    capture_output=True,
                )
                if out2:
                    print(out2)
                if err2:
                    print(err2)
                assets2 = _active_asset_paths()
                gfs = (
                    list(assets2["storyboards_dir"].glob("grid_batch_*.png"))
                    if assets2 and assets2.get("storyboards_dir") and assets2["storyboards_dir"].exists()
                    else []
                )
                if not gfs:
                    state.set_status("STEP2_FAILED", topic_for)
                    mgr.send_text(open_id, "open_id", "❌ Step2-A 重试结束仍未生成宫格，请查看本机终端日志。")
                    return
                run_storyboard_review(topic_for, open_id)
                mgr.send_text(
                    open_id,
                    "open_id",
                    f"✅ Step2-A 重试完成，已推送分镜审核卡（Run-ID: `{run_id}`）。请在卡片上通过或打回批次。",
                )
                return

            gate_ok2, gate_reason2 = _validate_step2_gate(run_id)
            if not gate_ok2:
                state.set_status("STEP2_FAILED", topic_for)
                mgr.send_text(open_id, "open_id", f"❌ Step2 重试后门禁未通过：{gate_reason2}")
                return
            mgr.send_text(open_id, "open_id", f"✅ Step2 重试完成并通过门禁（Run-ID: {run_id}）。")
            state.set_status("STEP2_SUCCESS", topic_for)
            return
        if step == "step3":
            if not assets["master_voice"].exists():
                mgr.send_text(open_id, "open_id", "❌ 无法合成视频，当前批次缺失核心主音轨，请先退回执行 Step1！")
                return
            if not assets["narrative"].exists():
                mgr.send_text(open_id, "open_id", "❌ 无法重试 Step3：当前批次缺失 `narrative_v6_final.json`，请先执行 Step1。")
                return
            if not assets["storyboards_any"]:
                mgr.send_text(open_id, "open_id", "❌ 无法重试 Step3：当前批次没有可用分镜图，请先执行 Step2。")
                return
            gate_ok, gate_reason = _validate_step2_gate(run_id)
            if not gate_ok:
                mgr.send_text(open_id, "open_id", f"❌ 无法重试 Step3：Step2 门禁未通过。{gate_reason}")
                return
            state.set_status("STEP3_ASSEMBLING", state.get_current_state().get("topic", ""))
            mgr.send_text(open_id, "open_id", f"🔁 正在重试 Step3（Run-ID: {run_id}）...")
            out3, err3 = _run_cmd_with_pid_tracking(
                [PYTHON_BIN, "src/step3_assembler_v6.py"],
                BASE_DIR,
                run_id,
                stop_flag=stop_flag,
                capture_output=True,
            )
            if out3:
                print(out3)
            if err3:
                print(err3)
            final_mp4 = assets["final_mp4"]
            if final_mp4.exists():
                _notify_step3_success_with_upload(open_id, final_mp4, "✅ Step3 重试完成")
                state.set_status("COMPLETED", state.get_current_state().get("topic", ""))
            else:
                mgr.send_text(open_id, "open_id", "⚠️ Step3 执行结束但未检测到成片文件，请检查日志。")
            return
        mgr.send_text(open_id, "open_id", "❌ 仅支持 `/retry step1`、`/retry step2` 或 `/retry step3`。")
    except subprocess.CalledProcessError as e:
        err = ((e.stderr or e.output or str(e)) or "")[-1200:]
        mgr.send_text(open_id, "open_id", f"🚨 单步重试失败：{err}")
        state.set_status("ERROR", state.get_current_state().get("topic", ""))
    except Exception as e:
        mgr.send_text(open_id, "open_id", f"🚨 单步重试异常：{e}")
        state.set_status("ERROR", state.get_current_state().get("topic", ""))


def enqueue_job(open_id: str, description: str, fn, *args, send_ack: bool = True, **kwargs):
    if send_ack:
        _async_send_text(open_id, f"✅ 收到指令，任务已排队：{description}")
    TASK_QUEUE.put({
        "fn": fn,
        "args": args,
        "kwargs": kwargs,
        "description": description,
        "open_id": open_id,
        "run_id": get_current_run_id() or "",
        "topic": state.get_current_state().get("topic", ""),
    })

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

    # === 运维指令：/status /switch /retry ===
    if msg_clean in ["/status", "状态", "进度"]:
        _schedule_step3_orphan_recovery_if_needed(open_id)
        send_status_card(open_id, current_topic, current_status)
        return

    m_switch = re.match(r"^/(?:switch)\s+([A-Za-z0-9_\-]+)\s*$", msg_clean, flags=re.IGNORECASE)
    if not m_switch:
        m_switch = re.match(r"^切换\s+([A-Za-z0-9_\-]+)\s*$", msg_clean, flags=re.IGNORECASE)
    if m_switch:
        target_run_id = m_switch.group(1).strip()
        ok, reason = switch_active_run(target_run_id)
        if ok:
            mgr.send_text(
                open_id,
                "open_id",
                f"✅ 已切换至历史工作区：{target_run_id}。\n接下来执行的任何单步操作，都将基于此批次的数据覆盖运行。"
            )
            send_status_card(open_id, current_topic, current_status)
        else:
            mgr.send_text(open_id, "open_id", f"❌ 切换失败：{reason}")
        return

    m_retry = re.match(r"^/(?:retry)\s+(step1|step2|step3)\s*$", msg_clean, flags=re.IGNORECASE)
    if not m_retry:
        m_retry = re.match(r"^重试\s+(step1|step2|step3)\s*$", msg_clean, flags=re.IGNORECASE)
    if m_retry:
        step_name = m_retry.group(1).lower()
        enqueue_job(open_id, f"断点续传 {step_name}", retry_single_step, step_name, open_id)
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
        resend_storyboard_review_card(open_id)
        return

    # 如果用户问了好、或者问状态，或者是纯粹的乱码短句，且不在需要他文字输入的阶段
    # 或者是机器人在纯搬砖（生图、剪辑等），此时直接给他发状态卡片
    BUSY_OR_ERROR_STATES = [
        "GENERATING_SYNOPSIS", "GENERATING_VISUALS",
        "STEP1_WRITING", "STEP2_GENERATING", "STEP2_FAILED",
        "STEP3_ASSEMBLING", "ERROR"
    ]
    
    is_asking_status = msg_clean in ["你是谁", "在吗", "你好", "你什么情况", "什么情况"]
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
            "\n\n4️⃣ **运维面板命令**：\n"
            "   - `/status`: 查看当前 Run-ID 与素材就绪探针\n"
            "   - `/switch Run_YYYY...`: 切换到历史批次\n"
            "   - `/retry step1`、`/retry step2` 或 `/retry step3`: 对当前批次执行断点续传\n"
            "   - `/resend storyboard` 或 `补发分镜审核卡`: 宫格已在磁盘但飞书未收到审核卡时，仅补推审核卡"
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
        rid = get_current_run_id() or ""
        PIPELINE_STOP_FLAGS.setdefault(rid, threading.Event()).set()
        killed = _kill_by_run_id(rid) if rid else 0
        state.set_status("IDLE", "")
        mgr.send_text(open_id, "open_id", f"🗑️ 已取消项目【{current_topic}】并重置系统（精准终止 {killed} 个进程）。\n发送「换一批」可重新获取主题。")
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
    # 分镜审核态：补充「开始切分」等短语，避免只说行业用语时绕不开 LLM
    if current_status == "WAITING_STORYBOARD_APPROVAL" and any(
        p in msg_clean for p in ("开始切分", "切分高清", "宫格通过", "分镜通过", "确认宫格", "通过宫格")
    ):
        mgr.send_text(open_id, "open_id", "✅ 分镜审核通过！开始切分高清 + 视频合成，请耐心等待...")
        enqueue_job(open_id, f"切分高清+合成: {current_topic}", continue_after_storyboard_approval, current_topic, open_id)
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
                _sync_synopsis_duration_from_draft(open_id, current_topic)
                enqueue_job(open_id, f"生成定妆照: {current_topic}", run_visual_setup, current_topic, open_id)
            else:
                mgr.send_text(open_id, "open_id", "⚠️ 无待审批的剧情数据，请先运行选题或重置。")
            return
        elif current_status == "WAITING_CHARACTER_APPROVAL":
            mgr.send_text(open_id, "open_id", "✅ 定妆照已确认！开始推入剧本生产流水线！")
            enqueue_job(open_id, f"全量生产: {current_topic}", run_project_pipeline, current_topic, open_id)
            return
        elif current_status == "WAITING_STORYBOARD_APPROVAL":
            mgr.send_text(open_id, "open_id", "✅ 分镜审核通过！开始切分高清 + 视频合成，请耐心等待...")
            enqueue_job(open_id, f"切分高清+合成: {current_topic}", continue_after_storyboard_approval, current_topic, open_id)
            return
        # 其他状态下用户说「可以」不走上方审批分支，交由下方通用 LLM 对话逻辑处理

    # 「分镜打回」快速通道：识别「打回第 X 批」「第 X 批重画」等
    batch_rej = _parse_storyboard_reject_batch(msg_clean)
    if batch_rej is not None:
        if current_status == "WAITING_STORYBOARD_APPROVAL":
            mgr.send_text(open_id, "open_id", f"🔄 收到！正在重新生成第 {batch_rej} 批次宫格图...")
            enqueue_job(
                open_id,
                f"重画分镜批次 {batch_rej}: {current_topic}",
                regenerate_storyboard_batch,
                current_topic,
                open_id,
                batch_rej,
            )
        else:
            mgr.send_text(open_id, "open_id", "⚠️ 当前不在分镜审核阶段，打回指令无效。")
        return

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
系统刚刚已向老板发送了剧情大纲（卡片上可点 −30秒/+30秒 或 3/6/10/15 分钟 设定成片时长，确认后会写入后台）。老板正在审阅。你的唯一任务是判断老板对"当前这份大纲"的态度。

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

        elif current_status == "WAITING_STORYBOARD_APPROVAL":
            instruction_set = """【当前权限：分镜宫格审批】
系统已向老板发送了所有批次的 16 宫格分镜预览图（一张卡片包含全部批次）。
1. 老板确认全部无误，可以进入切分高清 → [TRIGGER_APPROVE_STORYBOARDS]
2. 老板指出某批次有问题 → [TRIGGER_REJECT_STORYBOARD: 批次号]
   （例如说"第2张比例不对"、"批次3有问题"、"第1批重画"）"""


        system_prompt = f"""你是视频项目的沟通协调员，帮助用户和后台自动化系统对话。

你绝对不能模拟系统行为、编造进度或编造系统限制。你只负责引导用户决策和理解意图。

【管线知识】1.大纲 -> 2.定妆照 -> 3.剧本与分镜蓝图(Step1) -> 4.分镜宫格预览(Step2-A，人工审核) -> 5.裁切高清(Step2-B) -> 6.视频合成(Step3) 与交付。

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
             if s2["status"] not in ["IDLE", "WAITING_TOPIC", "COMPLETED"]:
                 mgr.send_text(
                     open_id,
                     "open_id",
                     f"🚫 **系统正在专心处理上一个项目！**\n🔖 **在建任务**：【{s2['topic']}】\n⚠️ 必须等它完成，或发送【取消】、【重置】指令终止它后，才能开启新项目。"
                 )
                 return True
             return False

        # 解析指令
        if "[TRIGGER_STOP]" in chat_reply:
            rid = get_current_run_id() or ""
            PIPELINE_STOP_FLAGS.setdefault(rid, threading.Event()).set()
            killed = _kill_by_run_id(rid) if rid else 0
            state.set_status("IDLE", "")
            mgr.send_text(open_id, "open_id", f"🎬 收到！已为您紧急叫停当前批次生产线（精准终止 {killed} 个进程）。")
            
        elif "[TRIGGER_IDEAS]" in chat_reply:
            import ideator
            import threading
            threading.Thread(target=ideator.send_morning_topics, args=(open_id,)).start()
            
        elif "[TRIGGER_APPROVE_SYNOPSIS]" in chat_reply:
            # 大纲批准，开始生图
            if current_status in ["WAITING_SYNOPSIS_APPROVAL", "ERROR", "IDLE", "GENERATING_SYNOPSIS", "GENERATING_VISUALS"]:
                import os
                if os.path.exists(BASE_DIR / "feishu" / "temp_synopsis.json"):
                    _sync_synopsis_duration_from_draft(open_id, current_topic)
                    enqueue_job(open_id, f"生成定妆照: {current_topic}", run_visual_setup, current_topic, open_id)
                else:
                    mgr.send_text(open_id, "open_id", "⚠️ 找不到待审批的剧情数据，请先下发盲盒选题。")

        elif "[TRIGGER_REVISE_SYNOPSIS:" in chat_reply:
            m = re.search(r"\[TRIGGER_REVISE_SYNOPSIS: (.*?)\]", chat_reply)
            if m:
                feedback = m.group(1).strip()
                enqueue_job(open_id, f"重写大纲: {current_topic}", run_synopsis_setup, current_topic, open_id, feedback)

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
                mgr.send_text(open_id, "open_id", f"✅ 立项动作激活：【{topic}】\n📍 生产时长：{duration} 分钟\n正在为您秘密开启这个人生副本...")
                enqueue_job(open_id, f"立项生成大纲: {topic}", run_synopsis_setup, topic, open_id, "", duration)

        elif "[TRIGGER_APPROVE_CHARACTER]" in chat_reply:
            if current_status == "WAITING_CHARACTER_APPROVAL":
                mgr.send_text(open_id, "open_id", "✅ 定妆照通过！开始推入剪辑生产流流水线！")
                enqueue_job(open_id, f"全量生产: {current_topic}", run_project_pipeline, current_topic, open_id)

        elif "[TRIGGER_REGEN_CHARACTER:" in chat_reply:
            m = re.search(r"\[TRIGGER_REGEN_CHARACTER: (.*?)\]", chat_reply)
            if m:
                stage_req = m.group(1).strip()
                # BUG-09 修复：统一别名，"old" → "elderly"（与 ref_generator/style_config 保持一致）
                STAGE_ALIAS = {"old": "elderly", "child": "child", "middle": "middle", "elderly": "elderly"}
                stage = STAGE_ALIAS.get(stage_req)
                enqueue_job(open_id, f"重画阶段 {stage}: {current_topic}", run_visual_setup, current_topic, open_id, stage)

        elif "[TRIGGER_APPROVE_STORYBOARDS]" in chat_reply:
            if current_status == "WAITING_STORYBOARD_APPROVAL":
                mgr.send_text(open_id, "open_id", "✅ 分镜审核通过！开始切分高清 + 视频合成，请耐心等待...")
                enqueue_job(open_id, f"切分高清+合成: {current_topic}", continue_after_storyboard_approval, current_topic, open_id)

        elif "[TRIGGER_REJECT_STORYBOARD:" in chat_reply:
            m = re.search(r"\[TRIGGER_REJECT_STORYBOARD:\s*(\d+)\s*\]", chat_reply)
            if m and current_status == "WAITING_STORYBOARD_APPROVAL":
                bi = int(m.group(1))
                mgr.send_text(open_id, "open_id", f"🔄 收到，正在重新生成第 {bi} 批次宫格图...")
                enqueue_job(
                    open_id,
                    f"重画分镜批次 {bi}: {current_topic}",
                    regenerate_storyboard_batch,
                    current_topic,
                    open_id,
                    bi,
                )

    except Exception as e:
        print(f"  -> [CHAT_ERR] 类型={type(e).__name__} 信息={e}")
        import traceback
        traceback.print_exc()
        # 尝试说一句有帮助的话而不是废话
        s3 = state.get_current_state()
        status_tip = {
            "WAITING_SYNOPSIS_APPROVAL": "您可以直接发送「可以」推进下一步，或直接说出修改意见。",
            "WAITING_CHARACTER_APPROVAL": "您可以发送「可以」开始生产，或发送「重画」并说明哪个阶段。",
            "WAITING_STORYBOARD_APPROVAL": "您可以发送「可以」或「开始切分」进入裁切高清与合成，或说「打回第 N 批」重画宫格。",
        }.get(s3["status"], "可以发送「状态」查看当前进度。")
        mgr.send_text(open_id, "open_id", f"🚨 大脑连线失败，请检查网络或 API Key: {str(e)}\n\n▶️ {status_tip}")

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

    def _startup_orphan_step3_recovery():
        """Hub 进程启动后稍等再尝试：无飞书会话时仅写控制台，避免上次异常退出遗留「有图无成片」。"""
        time.sleep(12)
        try:
            _recover_step3_if_orphaned(None)
        except Exception as ex:
            print(f"[WARN] 启动时 Step3 孤儿自愈异常: {ex}")

    threading.Thread(target=_startup_orphan_step3_recovery, daemon=True).start()

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