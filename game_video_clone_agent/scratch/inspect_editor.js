    function loadChannelDraft() {
      const draft = localStorage.getItem(`palette_draft_${state.activeChannelId}`) || "";
      const ta = document.getElementById("rawScriptTextarea");
      if (ta) { ta.value = draft; state.rawScript = draft; }
      updateJsonPayloadViewer();
    }

    // ── ✏️ 频道编辑器弹窗 ──
    const CHANNEL_COLORS = [
      "#EF4444","#F59E0B","#10B981","#3B82F6","#8B5CF6",
      "#EC4899","#06B6D4","#F97316","#84CC16","#6366F1"
    ];
    let _editingChannelId = null;

    function openChannelEditor(channelId) {
The above content does NOT show the entire file contents. If you need to view any lines of the file which were not shown to complete your task, call this tool again to view those lines.

      // 安全直出锁标志
      document.getElementById("d1LockBadge").innerText = state.polishEnabled ? "✨ SMART_POLISH_FLOW" : "🔒 ORIGINAL_TEXT_LOCKED";
      document.getElementById("d1LockBadge").className = state.polishEnabled ? "px-2 py-0.5 text-[9px] tracking-widest uppercase font-bold rounded bg-indigo-950 border border-indigo-800 text-indigo-200" : "px-2 py-0.5 text-[9px] tracking-widest uppercase font-bold rounded bg-red-950 border border-red-800/80 text-red-200";

        const editBtn = card.querySelector('.edit-btn');
        if (editBtn) {
          card.addEventListener('mouseenter', () => editBtn.style.opacity = '1');
          card.addEventListener('mouseleave', () => editBtn.style.opacity = '0');
        }
      });
    }

    // ── ⚡ 频道激活（切换提示词上下文 + 触发转场） ──
    function activateChannel(channelId, event) {
      const ch = state.channels.find(c => c.id === channelId);
      if (!ch) return;

      state.activeChannelId = channelId;
      state.modePath = channelId.toUpperCase();
      // 注入该频道专属提示词
      state.presets = getChannelPresets(ch);

      // 转场特效
      if (event) {
        const splash = document.getElementById("splashCircle");
        splash.style.left = `${event.clientX}px`;
        splash.style.top = `${event.clientY}px`;
        splash.style.backgroundColor = ch.color;
        splash.classList.add("active");
        setTimeout(() => {
          navigateTo("C1");
          splash.classList.remove("active");
        }, 900);
      } else {
        navigateTo("C1");
      }
    }

    // ── 🔍 获取当前激活频道对象 ──
    function getActiveChannel() {
      return state.channels.find(c => c.id === state.activeChannelId) || state.channels[0];
    }

    // ── 💾 频道持久化存储 ──
    function saveChannelsToStorage() {
The above content does NOT show the entire file contents. If you need to view any lines of the file which were not shown to complete your task, call this tool again to view those lines.

      rebuildBtn.disabled = true;
      rebuildBtn.innerText = "🎨 生图引擎重绘中...";

      try {
        const res = await pywebview.api.render_single_frame({
            target_id: ast.id,
            prompt: newPrompt,
            seed: state.seed,
            style_lock: true
      "#EC4899","#06B6D4","#F97316","#84CC16","#6366F1"
    ];
    let _editingChannelId = null;

    function openChannelEditor(channelId) {
      if (ta) { ta.value = draft; state.rawScript = draft; }
      updateJsonPayloadViewer();
    }

    // ── ✏️ 频道编辑器弹窗 ──
    const CHANNEL_COLORS = [
      "#EF4444","#F59E0B","#10B981","#3B82F6","#8B5CF6",
      "#EC4899","#06B6D4","#F97316","#84CC16","#6366F1"
    ];
    let _editingChannelId = null;

    function openChannelEditor(channelId) {
      _editingChannelId = channelId;
      const modal = document.getElementById("channelEditorModal");
      const deleteBtn = document.getElementById("chEditorDeleteBtn");

    // ── 💾 频道持久化存储 ──
    function saveChannelsToStorage() {
      localStorage.setItem("palette_channels_v3", JSON.stringify(state.channels));
      // 异步同步到后台（双轨备份，失败不影响前端）
      if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.save_channels) {
        pywebview.api.save_channels(state.channels).catch(() => {});
      }
    }

    // ── 📝 频道草稿隔离读写 ──
The above content does NOT show the entire file contents. If you need to view any lines of the file which were not shown to complete your task, call this tool again to view those lines.

      `).join("");
      document.getElementById("chEditorColor").value = selectedColor;

      if (channelId)
<truncated 493 bytes>
sets(ch);
        const ch = state.channels.find(c => c.id === channelId);
        if (!ch) return;
        document.getElementById("chEditorTitle").innerText = `编辑频道：${ch.name}`;
        document.getElementById("chEditorEmoji").innerText = ch.emoji || '🎬';
        document.getElementById("chEditorEmojiInput").value = ch.emoji || '';
        document.getElementById("chEditorName").value = ch.name;
        const presets = getChannelPresets(ch);
        document.getElementById("chEditorOutline").value   = ch.presets?.outline   || presets.outline || '';
        document.getElementById("chEditorImage").value     = ch.presets?.image     || '';
        document.getElementById("chEditorVoiceover").value = ch.presets?.voiceover || '';
        document.getElementById("chEditorPolish").value    = ch.presets?.polish    || '';
        document.getElementById("chEditorStoryboard").value = ch.presets?.storyboard || '';
        // 原厂频道不显示删除按钮
        deleteBtn.classList.toggle("hidden", !!ch.locked);
        // 有备份时才显示回滚按钮
        if (rollbackBtn) rollbackBtn.classList.toggle("hidden", !ch.presetsBackup);
      } else {
        document.getElementById("chEditorTitle").innerText = "新增创作频道";
        document.getElementById("chEditorEmoji").innerText = "🎬";
        document.getElementById("chEditorEmojiInput").value = "";
      const palette = document.getElementById("chColorPalette");
      let selectedColor = channelId
        ? (state.channels.find(c => c.id === channelId)?.color || CHANNEL_COLORS[0])
        : CHANNEL_COLORS[3];
      palette.innerHTML = CHANNEL_COLORS.map(clr => `
        <button type="button" onclick="selectEditorColor('${clr}')" id="colorDot_${clr.replace('#','')}"
          class="w-8 h-8 rounded-full border-2 transition-all cursor-pointer hover:scale-110"
          style="background:${clr}; border-color: ${clr === selectedColor ? 'white' : 'transparent'}"></button>
      `).join("");
      document.getElementById("chEditorColor").value = selectedColor;

      if (channelId) {
        const ch = state.channels.find(c => c.id === channelId);
        if (!ch) return;
        document.getElementById("chEditorTitle").innerText = `编辑频道：${ch.name}`;
        document.getElementById("chEditorEmoji").innerText = ch.emoji || '🎬';
        document.getElementById("chEditorEmojiInput").value = ch.emoji || '';
        document.getElementById("chEditorName").value = ch.name;
        const presets = getChannelPresets(ch);
        document.getElementById("chEditorOutline").value   = ch.presets?.outline   || presets.outline || '';
        document.getElementById("chEditorImage").value     = ch.presets?.image     || '';
        document.getElementById("chEditorVoiceover").value = c
<truncated 822 bytes>
:         // 有备份时才显示回滚按钮
        document.getElementById(
<truncated 522 bytes>
 = "";
      _editingChannelId = null;
    }

    function saveChannelFromEditor() {
      const name = document.getElementById("chEditorName").value.trim();
      if (!name) { showToast("⚠️ 请填写频道名称！"); return; }
      if (state.channels.length >= 8 && !_editingChannelId) {
        deleteBtn.classList.add("hidden");
        if (rollbackBtn) rollbackBtn.classList.add("hidden");
      }

      modal.classList.remove("hidden");
        if (rollbackBtn) rollbackBtn.classList.toggle("hidden", !ch.presetsBackup);
      } else {
        document.getElementById("chEditorTitle").innerText = "新增创作频道";
        document.getElementById("chEditorEmoji").innerText = "🎬";
        document.getElementById("chEditorEmojiInput").value = "";
        document.getElementById("chEditorName").value = "";
        document.getElementById("chEditorOutline").value = "";
        document.getElementById("chEditorImage").value = "";
        document.getElementById("chEditorVoiceover").value = "";
        document.getElementById("chEditorPolish").value = "";
        document.getElementById("chEditorStoryboard").value = "";
        // 新频道默认「解说/科普」模式（1张背景底图）
        document.querySelectorAll('input[name="chChannelType"]').forEach(r => {
          r.checked = (r.value === "science");
          r.disabled = false;
        });
        document.getElementById("chTypeRow").style.opacity = "1";
        _syncChannelTypeStyle();
        deleteBtn.classList.add("hidden");
        if (rollbackBtn) rollbackBtn.classList.add("hidden");
      }

      modal.classList.remove("hidden");
    }

    // 同步定妆模式选择器高亮边框
    function _syncChannelTypeStyle() {
      const val = document.querySelector('input[name="chChannelType"]:checked')?.value || "science";
      const sciEl = document.getElementById("chTypeLabelScience");
      const draEl = document.getElementById("chTypeLabelDrama");
      if (sciEl) sciEl.style.borderColor = (val === "science") ? "#F59E0B" : "";
      if (draEl) draEl.style.borderColor = (val === "drama")   ? "#6366F1" : "";
    }


    function selectEditorColor(clr) {
      document.getElementById("chEditorColor").value = clr;
      document.querySelectorAll("#chColorPalette button").forEach(btn => {
        const btnClr = btn.style.background;
        btn.style.borderColor = btnClr === clr ? 'white' : 'transparent';
      });
    }

    function closeChannelEditor() {
      document.getElementById("channelEditorModal").classList.add("hidden");
      _editingChannelId = null;
    }

    function saveChannelFromEditor() {
      const name = document.getElementById("chEditorName").value.trim();
      if (!name) { showToast("⚠️ 请填写频道名称！"); return; }
      if (state.channels.length >= 8 && !_editingChannelId) {
        showToast("⚠️ 最多创建 8 个频道！"); return;
      }

      const emoji = document.getElementById("chEditorEmojiInput").value.trim() || "🎬";
      const color = document.getElementById("chEditorColor").value || "#6366F1";
      const outline = document.getElementById("chEditorOutline").value.trim();
      const image = document.getElementById("chEditorImage").value.trim();
      const voiceover = document.getElementById("chEditorVoiceover").v
<truncated 552 bytes>
 !== -1) {
          if (state.channels[idx].presets) {
            state.channels[idx].presetsBackup = JSON.parse(JSON.stringify(state.channels[idx].presets));
          }
          state.channels[idx].name = name;
          state.channels[idx].emoji = emoji;
          // 颖定频道只更新提示词，不更新颜色
          if (!state.channels[idx].locked) {
            state.channels[idx].color = color;
          // ✅ 保存前：备份当前提示词到 presetsBackup（用于回滚）
          if (state.channels[idx].presets) {
            state.channels[idx].presetsBackup = JSON.parse(JSON.stringify(state.channels[idx].presets));
          }
          state.channels[idx].name = name;
