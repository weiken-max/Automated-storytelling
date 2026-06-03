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


class ToggleBatchPromptsAction:
    """展开/收起某批次的 16 条提示词（英文原文）

    V4：查看提示词 → 发文字消息（快，无超时风险）；
         修改意见 → 卡片 PATCH（在宫格图下方展示修改后的提示词）。
    提示词同时写入 session 上下文，供后续 PATCH 使用。
    """

    def execute(self, session, data: dict, mgr, **context) -> dict:
        try:
            batch_index = int(data.get("batch_index", 0))
        except (TypeError, ValueError):
            return {"toast": {"type": "error", "content": "批次号无效。"}}
        if batch_index < 1:
            return {"toast": {"type": "error", "content": "批次号无效。"}}

        action = data.get("action", "show")
        open_id = session.open_id

        # ── 收起：清除展开状态，简短提示 ──
        if action == "hide":
            expanded = set(session.get_context("expanded_batches") or [])
            expanded.discard(batch_index)
            session.set_context("expanded_batches", list(expanded))
            self._save_context(session)
            mgr.send_text(open_id, "open_id", f"📋 批次 {batch_index} 提示词已收起。")
            return {"toast": {"type": "info", "content": f"批次 {batch_index} 提示词已收起"}}

        # ── 展开：加载提示词 → 发文字消息 → 存 session 上下文（供后续 PATCH 用）──
        try:
            get_run_id = context.get("get_current_run_id")
            run_id = get_run_id() if get_run_id else ""

            from feishu.pipeline.prompt_ops import (
                load_narrative_final, get_batch_prompts,
            )
            narrative = load_narrative_final(run_id)
            en_prompts = get_batch_prompts(narrative, batch_index)

            if not en_prompts:
                mgr.send_text(open_id, "open_id",
                              f"⚠️ 批次 {batch_index} 未找到提示词，请确认 narrative_v6_final.json 是否存在。")
                return {"toast": {"type": "warning", "content": "未找到提示词"}}

            # 存入 session 上下文（供后续修改意见触发的卡片 PATCH 使用）
            all_translated = session.get_context("translated_prompts") or {}
            all_translated[str(batch_index)] = en_prompts
            session.set_context("translated_prompts", all_translated)

            expanded = set(session.get_context("expanded_batches") or [])
            expanded.add(batch_index)
            session.set_context("expanded_batches", list(expanded))

            self._save_context(session)

            # 构建纯文字消息发给用户（快，不涉及图片上传或卡片 PATCH）
            batch_start = (batch_index - 1) * 16 + 1
            lines = [f"📝 批次 {batch_index} 提示词（英文原文）：\n"]
            for j in range(16):
                sid = f"S_{batch_start + j:03d}"
                prompt = en_prompts.get(sid, "（暂无）")
                lines.append(f"\n[{sid}] {prompt}")

            lines.append(
                "\n\n💡 修改提示词格式：\n"
                "单镜修改：批次 N S_XXX 修改意见\n"
                "整批修改：批次 N 修改意见"
            )

            mgr.send_text(open_id, "open_id", "".join(lines))

        except Exception as e:
            mgr.send_text(open_id, "open_id", f"❌ 加载提示词失败：{e}")
            return {"toast": {"type": "error", "content": f"加载失败: {e}"}}

        return {"toast": {"type": "info", "content": f"批次 {batch_index} 提示词已发送，请查看上方消息"}}

    @staticmethod
    def _save_context(session):
        """持久化 session 上下文到 DB"""
        from feishu.session import SessionStore
        store = SessionStore()
        store.save_context_json(session.session_id, session.context_json)


class RejectBatchWithPromptsAction:
    """使用修改后的提示词打回批次重画"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        topic = data.get("topic", "") or getattr(session, "topic", "")
        try:
            batch_index = int(data.get("batch_index", 0))
        except (TypeError, ValueError):
            return {"toast": {"type": "error", "content": "批次号无效。"}}
        if batch_index < 1:
            return {"toast": {"type": "error", "content": "批次号无效。"}}

        get_run_id = context.get("get_current_run_id")
        run_id = get_run_id() if get_run_id else ""

        # 1. 将暂存的修改写回 narrative_v6_final.json
        revised = session.get_context(f"revised_prompts_batch_{batch_index}") or {}
        if revised:
            from feishu.pipeline.prompt_ops import (
                load_narrative_final, write_back_prompts, save_narrative_final,
            )
            narrative = load_narrative_final(run_id)
            write_back_prompts(narrative, batch_index, revised)
            save_narrative_final(narrative, run_id)

        # 清理 session 中的暂存
        session.set_context(f"revised_prompts_batch_{batch_index}", None)

        # 也清理翻译缓存（让下次展开重新翻译）
        all_translated = session.get_context("translated_prompts") or {}
        all_translated.pop(str(batch_index), None)
        session.set_context("translated_prompts", all_translated)

        # 取消该批次的展开状态
        expanded = set(session.get_context("expanded_batches") or [])
        expanded.discard(batch_index)
        session.set_context("expanded_batches", list(expanded))

        # 2. 入队重画
        enqueue = context.get("enqueue_job")
        regen_fn = context.get("regenerate_storyboard_batch")
        if enqueue and regen_fn and callable(regen_fn):
            extra = "（修改后提示词）" if revised else ""
            enqueue(
                session.open_id,
                f"重画分镜批次 {batch_index}{extra}: {topic}",
                regen_fn, topic, session.open_id, batch_index,
            )
            return {"toast": {"type": "info", "content": f"收到，正在使用修改后提示词重新生成批次 {batch_index}..."}}
        return {"toast": {"type": "error", "content": "缺少执行上下文"}}
