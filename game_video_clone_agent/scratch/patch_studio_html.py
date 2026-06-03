import re
from pathlib import Path

# Paths
html_path = Path("palette_studio.html")
html = html_path.read_text(encoding="utf-8")

# 1. Add storyboardGrids to state
old_storyboards = 'storyboards: [], // 分镜帧底片'
new_storyboards = 'storyboards: [], // 分镜帧底片\n      storyboardGrids: [], // 16 宫格大图批次'
html = html.replace(old_storyboards, new_storyboards)

# 2. Add overlayLargeGrid modal right after closing tag of overlayE1
old_overlay_close = '<!-- ==================== 界面 F: 最终多轨合并与电影放映室 ==================== -->'
new_overlay_modal = """<!-- ==================== 16 宫格大图放大弹窗 ==================== -->
        <div id="overlayLargeGrid" class="hidden fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/90 backdrop-blur-md cursor-zoom-out" onclick="closeLargeGrid()">
          <div class="relative max-w-7xl max-h-[90vh] bg-slate-950 border border-slate-800 rounded-3xl overflow-hidden shadow-2xl flex items-center justify-center" onclick="event.stopPropagation()">
            <img id="largeGridImg" src="" class="max-w-full max-h-[85vh] object-contain" />
            <button onclick="closeLargeGrid()" class="absolute top-4 right-4 w-10 h-10 bg-black/60 hover:bg-slate-900 border border-slate-800 text-white rounded-full flex items-center justify-center font-bold text-lg transition cursor-pointer">✕</button>
          </div>
        </div>

        <!-- ==================== 界面 F: 最终多轨合并与电影放映室 ==================== -->"""
html = html.replace(old_overlay_close, new_overlay_modal)

# 3. Add applyFeedbackBtn to D2 Screen
old_d2_buttons = """          <div class="flex items-center justify-between border-t border-slate-850/60 pt-5">
            <button onclick="triggerShake()" class="px-5 py-2.5 bg-slate-950 border border-slate-850 text-xs font-bold text-indigo-300 hover:text-white rounded-lg transition flex items-center space-x-1">
              <span>🔄 摇一颗新故事</span>
            </button>
            <button onclick="submitD2ToD1()" class="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-xs font-bold text-white rounded-lg transition-all tracking-wider uppercase">
              <span>确认当前方案，进入D1文案处理</span>
            </button>
          </div>"""

new_d2_buttons = """          <div class="flex flex-col sm:flex-row gap-3 items-center justify-between border-t border-slate-850/60 pt-5">
            <button onclick="triggerShake()" class="w-full sm:w-auto px-5 py-2.5 bg-slate-950 border border-slate-850 text-xs font-bold text-indigo-300 hover:text-white rounded-xl transition flex items-center justify-center space-x-1 cursor-pointer">
              <span>🔮 重新摇一颗</span>
            </button>
            <button id="applyFeedbackBtn" onclick="applyD2Feedback()" class="w-full sm:w-auto px-5 py-2.5 bg-amber-600 hover:bg-amber-500 font-bold text-white rounded-xl text-xs transition-all flex items-center justify-center space-x-1 cursor-pointer">
              <span>✍️ 确定修改意见并重写大纲</span>
            </button>
            <button onclick="submitD2ToD1()" class="w-full sm:w-auto px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-xs font-bold text-white rounded-xl transition-all tracking-wider uppercase flex items-center justify-center cursor-pointer">
              <span>确认当前方案，进入D1 ➔</span>
            </button>
          </div>"""
html = html.replace(old_d2_buttons, new_d2_buttons)

# 4. Replace handleD1Next() with dynamic grid rendering and redraw JS functions
old_handle_d1_next = """    async function handleD1Next() {
      if (state.storyboards && state.storyboards.length > 0) {
        navigateTo("E");
        showToast("🎞️ 已恢复已生成的分镜底片大网格。");
        return;
      }
      if (state.isRunning) {
        showToast("⏳ 任务正在全力运转中，请勿重复点击！");
        return;
      }
      state.isRunning = true;
      navigateTo("E");
      showToast("🎞️ 正在物理切切旁白并插值生图分镜大宫格...");
      
      // 初始化骨架状态
      for (let i = 0; i < 4; i++) {
        document.getElementById(`framePreviewImg${i}`).innerHTML = `
          <span class="absolute top-2 left-2 px-1.5 py-0.5 bg-black/80 text-[8px] font-bold rounded text-amber-500 font-mono">F-0${i+1}</span>
          <div class="text-[10px] text-slate-700 animate-pulse">Rendering...</div>
        `;
      }
      
      try {
        const res = await pywebview.api.generate_storyboard();
        if (res.status === "success") {
          state.storyboards = res.frames;
          
          // 渲染底片
          state.storyboards.forEach((frm, idx) => {
            document.getElementById(`framePreviewImg${idx}`).innerHTML = `
              <span class="absolute top-2 left-2 px-1.5 py-0.5 bg-black/80 text-[8px] font-bold rounded text-amber-500 font-mono">F-0${idx+1}</span>
              <img src="${frm.image_url}" class="w-full h-full object-cover group-hover:scale-105 transition duration-500" />
            `;
            document.getElementById(`frameTextPreview${idx}`).innerText = frm.text;
            document.getElementById(`frameTime${idx}`).innerText = frm.time_range;
          });
          
          showToast("🎞️ 分镜底片及16宫格切图渲染完毕！");
        } else {
          showCustomModal("⚠️ 生成失败", "底片插值失败，请重试！");
        }
      } catch(err) {
        handleApiError(err, handleD1Next);
      } finally {
        state.isRunning = false;
      }
    }"""

new_handle_d1_next = """    async function handleD1Next() {
      if (state.storyboardGrids && state.storyboardGrids.length > 0) {
        navigateTo("E");
        showToast("🎞️ 已恢复已生成的分镜底片大网格。");
        return;
      }
      if (state.isRunning) {
        showToast("⏳ 任务正在全力运转中，请勿重复点击！");
        return;
      }
      state.isRunning = true;
      navigateTo("E");
      showToast("🎞️ 正在物理切切旁白并插值生图分镜大宫格...");
      
      // 初始化骨架状态
      const container = document.getElementById("storyboardGrid");
      if (container) {
        container.className = "flex items-center justify-center py-20 w-full";
        container.innerHTML = `
          <div class="text-center space-y-4">
            <div class="w-10 h-10 border-4 border-slate-750 border-t-indigo-500 rounded-full animate-spin mx-auto"></div>
            <div class="text-indigo-400 text-xs font-semibold tracking-wider animate-pulse">正在调用大模型极速渲染 16 宫格大图，请稍后...</div>
          </div>
        `;
      }
      
      try {
        const res = await pywebview.api.generate_storyboard();
        if (res.status === "success") {
          state.storyboardGrids = res.grids;
          
          // 渲染底片
          renderStoryboardGrids();
          showToast("🎞️ 16宫格切图大网格渲染完毕！");
        } else {
          showCustomModal("⚠️ 生成失败", res.detail || "底片插值失败，请重试！");
        }
      } catch(err) {
        handleApiError(err, handleD1Next);
      } finally {
        state.isRunning = false;
      }
    }

    function renderStoryboardGrids() {
      const container = document.getElementById("storyboardGrid");
      if (!container) return;
      
      const headerTextEl = container.previousElementSibling ? container.previousElementSibling.querySelector("p") : null;
      if (headerTextEl) {
        headerTextEl.innerHTML = `系统根据旁白句数科学组织了 ${state.storyboardGrids ? state.storyboardGrids.length : 0} 个 16 宫格大图批次。点击单个大图可放大审阅，修改文本框提示词后点击“打回重画”可重新渲染该批次。`;
      }
      
      if (!state.storyboardGrids || state.storyboardGrids.length === 0) {
        container.className = "flex items-center justify-center py-12";
        container.innerHTML = `
          <div class="text-center space-y-3">
            <div class="text-slate-600 text-3xl">📭</div>
            <div class="text-slate-500 text-xs font-mono">暂无分镜大宫格数据，请点击生成</div>
          </div>
        `;
        return;
      }
      
      container.className = "flex flex-col space-y-6 w-full";
      
      let html = "";
      state.storyboardGrids.forEach(grid => {
        html += `
          <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-4 transition-all hover:border-indigo-500/50 duration-300 flex flex-col md:flex-row gap-6">
            <!-- Left Side: Image Preview -->
            <div class="w-full md:w-2/5 flex flex-col justify-between space-y-3">
              <div>
                <div class="flex items-center justify-between mb-2">
                  <span class="px-2.5 py-1 bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 text-[10px] font-bold rounded-lg font-mono">${grid.range_text}</span>
                  <span class="text-[10px] text-slate-500 font-mono">BATCH_${String(grid.batch_index).padStart(3, '0')}</span>
                </div>
                <div onclick="showLargeGridImage('${grid.image_url}')" class="relative group aspect-[16/9] w-full bg-slate-950 rounded-xl border border-slate-850 flex items-center justify-center overflow-hidden cursor-zoom-in">
                  ${grid.image_url ? `
                    <img src="${grid.image_url}" class="w-full h-full object-cover group-hover:scale-[1.03] transition duration-500" />
                    <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-all duration-300">
                      <span class="text-white text-[10px] bg-indigo-650 px-3 py-1.5 rounded-lg shadow-lg font-bold">🔍 点击放大审阅 16 宫格</span>
                    </div>
                  ` : `
                    <div class="text-[10px] text-slate-500 font-mono flex flex-col items-center space-y-2">
                      <div class="w-6 h-6 border-2 border-slate-700 border-t-indigo-500 rounded-full animate-spin"></div>
                      <span>大模型全力绘制 16 宫格中...</span>
                    </div>
                  `}
                </div>
              </div>
              
              <button onclick="handleRegenBatch(${grid.batch_index}, this)" class="w-full py-2.5 bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 hover:text-rose-200 border border-rose-900/50 hover:border-rose-700/50 rounded-xl text-xs font-bold transition-all flex items-center justify-center space-x-2 shadow-sm cursor-pointer">
                <span>🔄 打回当前 16 宫格重画</span>
              </button>
            </div>

            <!-- Right Side: Prompts Editor -->
            <div class="flex-1 flex flex-col space-y-2.5">
              <div class="flex items-center justify-between">
                <span class="text-xs font-semibold text-slate-350">📝 批次提示词微调控制盘</span>
                <span class="text-[9px] text-slate-500">* 支持修改后打回重画</span>
              </div>
              <textarea id="gridPromptArea_${grid.batch_index}" rows="8" class="w-full flex-1 bg-slate-950 border border-slate-850 focus:border-indigo-500/50 rounded-xl p-3.5 text-[11px] text-slate-350 font-mono leading-relaxed focus:outline-none resize-none scrollbar-thin">${grid.prompt}</textarea>
            </div>
          </div>
        `;
      });
      
      container.innerHTML = html;
    }

    function showLargeGridImage(url) {
      if (!url) return;
      document.getElementById("largeGridImg").src = url;
      document.getElementById("overlayLargeGrid").classList.remove("hidden");
    }
    
    function closeLargeGrid() {
      document.getElementById("overlayLargeGrid").classList.add("hidden");
      document.getElementById("largeGridImg").src = "";
    }

    async function handleRegenBatch(batchIndex, btn) {
      if (state.isRunning) {
        showToast("⏳ 任务正在全力运转中，请勿重复点击！");
        return;
      }
      
      const textarea = document.getElementById(`gridPromptArea_${batchIndex}`);
      if (!textarea) return;
      
      const promptsStr = textarea.value;
      
      state.isRunning = true;
      const oldBtnHtml = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = `
        <div class="w-3.5 h-3.5 border-2 border-rose-300 border-t-transparent rounded-full animate-spin"></div>
        <span>正在重画中...</span>
      `;
      
      showToast(`🔄 正在重新调用大模型绘制第 ${batchIndex} 批次 16 宫格...`);
      
      try {
        const res = await pywebview.api.regenerate_single_batch({
          batch_index: batchIndex,
          prompts: promptsStr
        });
        
        if (res.status === "success") {
          showToast(`✅ 第 ${batchIndex} 批次分镜重画绘制成功！`);
          const targetIndex = state.storyboardGrids.findIndex(g => g.batch_index === batchIndex);
          if (targetIndex !== -1) {
            state.storyboardGrids[targetIndex] = res.grid;
          }
          renderStoryboardGrids();
        } else {
          showCustomModal("⚠️ 重画失败", res.detail || "请求失败，请重试！");
        }
      } catch (err) {
        handleApiError(err, () => handleRegenBatch(batchIndex, btn));
      } finally {
        state.isRunning = false;
        btn.disabled = false;
        btn.innerHTML = oldBtnHtml;
      }
    }

    async function applyD2Feedback() {
      if (state.isRunning) {
        showToast("⏳ 任务正在全力运转中，请勿重复点击！");
        return;
      }
      
      const feedbackInput = document.getElementById("d2FeedbackInput");
      const feedback = feedbackInput.value.trim();
      if (!feedback) {
        showToast("⚠️ 请先写入您的具体修改意见（例如：加一个猫咪助手）！");
        return;
      }
      
      state.isRunning = true;
      showToast("🧠 正在根据您的修改建议由编剧大模型重新雕琢大纲...");
      
      const btn = document.getElementById("applyFeedbackBtn");
      const oldHtml = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = `
        <div class="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
        <span>重写大纲中...</span>
      `;
      
      try {
        const res = await pywebview.api.compile_story({
          app_id: "palette-cinema-id",
          mode_path: "BLUE",
          original_text: state.rawScript,
          pipeline_config: {
            polish_flow: { 
              enabled: true, 
              system_prompt: state.presets.outline,
              feedback: feedback
            },
            voiceover_flow: { system_prompt: state.presets.voiceover },
            render_flow: { 
              style_presets: state.presets.image, 
              seed: 12345,
              cast_prompt: state.presets.cast_prompt,
              storyboard_prompt: state.presets.storyboard_prompt
            }
          }
        });
        
        if (res.status === "success") {
          state.rawScript = res.data.compiled_voiceover;
          document.getElementById("shakeOutlineContent").innerText = res.data.compiled_voiceover;
          feedbackInput.value = "";
          showToast("🎉 大纲重写成功！大模型已完美吸纳您的意见！");
        } else {
          showCustomModal("⚠️ 后端排队中", "重写大纲失败，请重试！");
        }
      } catch(err) {
        handleApiError(err, applyD2Feedback);
      } finally {
        state.isRunning = false;
        btn.disabled = false;
        btn.innerHTML = oldHtml;
      }
    }"""
html = html.replace(old_handle_d1_next, new_handle_d1_next)

# 5. Replace performSessionRecovery(res) and forceGenerateStoryboard()
old_recovery = """      // 3. 恢复分镜
      if (res.frames && res.frames.length > 0) {
        state.storyboards = res.frames;
        state.storyboards.forEach((frm, idx) => {
          const imgEl = document.getElementById(`framePreviewImg${idx}`);
          const txtEl = document.getElementById(`frameTextPreview${idx}`);
          const timeEl = document.getElementById(`frameTime${idx}`);
          if (imgEl && frm.image_url) {
            imgEl.innerHTML = `
              <span class="absolute top-2 left-2 px-1.5 py-0.5 bg-black/80 text-[8px] font-bold rounded text-amber-500 font-mono">F-0${idx+1}</span>
              <img src="${frm.image_url}" class="w-full h-full object-cover group-hover:scale-105 transition duration-500" />
            `;
          }
          if (txtEl) txtEl.innerText = frm.text;
          if (timeEl) timeEl.innerText = frm.time_range;
        });
      }
      
      // 4. 恢复视频
      if (res.video_url) {
        state.relativeVideoPath = res.relative_video_path;
        state.videoUrl = res.video_url;
        
        const vPlayer = document.getElementById("epicVideoPlayer");
        const vPlaceholder = document.getElementById("videoPlaceholder");
        if (vPlaceholder) vPlaceholder.classList.add("hidden");
        if (vPlayer) {
          vPlayer.src = res.video_url;
          vPlayer.classList.remove("hidden");
        }
      }
      
      navigateTo(res.stage);
      showToast(`🎉 成功为您自动恢复至 [${res.stage} 界面]！`);
    }

    // ── 🔄 分镜强行重新生成大宫格逻辑 ──
    async function forceGenerateStoryboard() {
      showCustomModal(
        "⚠️ 重新生成分镜确认",
        "重新生成分镜将丢弃现有的分镜图片，并重新消耗Token与显卡显存调用生图流水线。确定要继续吗？",
        "确定重新生成",
        true,
        async () => {
          state.storyboards = null;
          await handleD1Next();
        }
      );
    }"""

new_recovery = """      // 3. 恢复分镜
      if (res.grids && res.grids.length > 0) {
        state.storyboardGrids = res.grids;
        renderStoryboardGrids();
      } else if (res.frames && res.frames.length > 0) {
        state.storyboards = res.frames;
      }
      
      // 4. 恢复视频
      if (res.video_url) {
        state.relativeVideoPath = res.relative_video_path;
        state.videoUrl = res.video_url;
        
        const vPlayer = document.getElementById("epicVideoPlayer");
        const vPlaceholder = document.getElementById("videoPlaceholder");
        if (vPlaceholder) vPlaceholder.classList.add("hidden");
        if (vPlayer) {
          vPlayer.src = res.video_url;
          vPlayer.classList.remove("hidden");
        }
      }
      
      navigateTo(res.stage);
      showToast(`🎉 成功为您自动恢复至 [${res.stage} 界面]！`);
    }

    // ── 🔄 分镜强行重新生成大宫格逻辑 ──
    async function forceGenerateStoryboard() {
      showCustomModal(
        "⚠️ 重新生成分镜确认",
        "重新生成分镜将丢弃现有的分镜大宫格图片，并重新消耗Token与显卡显存调用生图流水线。确定要继续吗？",
        "确定重新生成",
        true,
        async () => {
          state.storyboards = null;
          state.storyboardGrids = null;
          await handleD1Next();
        }
      );
    }"""
html = html.replace(old_recovery, new_recovery)

# 6. Replace performSessionRecovery typo of voiceoverTextarea
old_typo = 'document.getElementById("voiceoverTextarea").value = res.synopsis.synopsis || "";'
new_correct = """const rawScriptEl = document.getElementById("rawScriptTextarea");
        if (rawScriptEl) {
          rawScriptEl.value = res.synopsis.synopsis || "";
        }
        
        const d1VoiceoverEl = document.getElementById("d1VoiceoverOutput");
        if (d1VoiceoverEl) {
          d1VoiceoverEl.innerText = res.synopsis.synopsis || "";
        }"""
html = html.replace(old_typo, new_correct)

# 7. Redesign renderBackstageData
old_backstage = """    function renderBackstageData(stages) {
      const listEl = document.getElementById("backstageStageList");
      if (!listEl) return;
      
      listEl.innerHTML = "";
      
      stages.forEach((stage, idx) => {
        let totalDuration = 0;
        let attemptsCount = stage.calls.length;
        stage.calls.forEach(c => totalDuration += c.duration);
        
        let statusBadge = "";
        let borderClass = "border-slate-900";
        let bgClass = "bg-slate-950/20";
        let titleColor = "text-slate-300";
        
        if (stage.status === "success") {
          statusBadge = `<span class="px-1.5 py-0.5 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-900/60 text-[9px] font-bold">✅ 成功</span>`;
          borderClass = "border-emerald-950/50";
          bgClass = "bg-emerald-950/5";
          titleColor = "text-emerald-300";
        } else if (stage.status === "failed") {
          statusBadge = `<span class="px-1.5 py-0.5 rounded bg-rose-950/80 text-rose-400 border border-rose-900/60 text-[9px] font-bold">❌ 失败</span>`;
          borderClass = "border-rose-950/50";
          bgClass = "bg-rose-950/5";
          titleColor = "text-rose-300";
        } else if (stage.status === "running") {
          statusBadge = `<span class="px-1.5 py-0.5 rounded bg-amber-950/80 text-amber-400 border border-amber-900/60 text-[9px] font-bold animate-pulse">⏳ 运行中</span>`;
          borderClass = "border-amber-950/50";
          bgClass = "bg-amber-950/5";
          titleColor = "text-amber-300";
        } else {
          statusBadge = `<span class="px-1.5 py-0.5 rounded bg-slate-900 text-slate-500 border border-slate-800 text-[9px] font-bold">💤 等待</span>`;
        }
        
        const stageEl = document.createElement("div");
        stageEl.className = `p-3 rounded-xl border ${borderClass} ${bgClass} space-y-2.5 transition-all`;
        
        let headerHtml = `
          <div class="flex justify-between items-center cursor-pointer" onclick="document.getElementById('stageCalls_${idx}').classList.toggle('hidden')">
            <div class="space-y-0.5">
              <div class="text-[10px] text-slate-500 font-mono">PHASE 0${idx+1}</div>
              <div class="text-xs font-bold ${titleColor}">${stage.name}</div>
            </div>
            <div class="flex items-center space-x-2">
              ${statusBadge}
              <span class="text-[10px] text-slate-600 font-mono">▼</span>
            </div>
          </div>
        `;
        
        let callsHtml = `<div id="stageCalls_${idx}" class="hidden pt-2 border-t border-slate-900/60 space-y-2">`;
        if (stage.calls.length === 0) {
          callsHtml += `<div class="text-[10px] text-slate-655 italic pl-1">暂无调用指标...</div>`;
        } else {
          stage.calls.forEach(call => {
            const callOkMark = call.ok 
              ? `<span class="text-emerald-400">✅</span>` 
              : `<span class="text-rose-400">❌</span>`;
              
            const callTime = call.time ? call.time.split("T")[1].slice(0, 8) : "";
            
            callsHtml += `
              <div class="p-2 rounded bg-slate-950/60 border border-slate-900 space-y-1">
                <div class="flex justify-between items-center text-[10px]">
                  <span class="font-medium text-slate-300 font-mono text-[9px] bg-slate-900 px-1.5 py-0.5 rounded">${callTime}</span>
                  <span class="font-bold text-slate-400">${call.step_cn}</span>
                  <span>${callOkMark}</span>
                </div>
                <div class="flex justify-between items-center text-[9px] text-slate-500 font-mono">
                  <span>模型: ${call.model || '-'}</span>
                  <span>耗时: ${call.duration.toFixed(2)}s (第 ${call.attempt} 次)</span>
                </div>
            `;
            if (call.error) {
              callsHtml += `
                <div class="text-[9px] text-rose-400/90 font-mono bg-rose-950/20 p-1.5 rounded border border-rose-900/30 overflow-x-auto whitespace-pre">
                  Error: ${call.error}
                </div>
              `;
            }
            callsHtml += `</div>`;
          });
        }
        
        if (stage.calls.length > 0) {
          headerHtml += `
            <div class="flex justify-between items-center text-[9px] text-slate-500 font-mono pt-1">
              <span>总耗时: ${totalDuration.toFixed(2)}秒</span>
              <span>请求数: ${attemptsCount}次</span>
            </div>
          `;
        }
        
        callsHtml += `</div>`;
        stageEl.innerHTML = headerHtml + callsHtml;
        listEl.appendChild(stageEl);
      });
    }"""

new_backstage = """    function renderBackstageData(stages) {
      const listEl = document.getElementById("backstageStageList");
      if (!listEl) return;
      
      listEl.innerHTML = "";
      
      stages.forEach((stage, idx) => {
        let totalDuration = 0;
        let attemptsCount = stage.calls.length;
        stage.calls.forEach(c => totalDuration += c.duration);
        
        let statusBadge = "";
        let borderClass = "border-slate-850/60";
        let bgClass = "bg-slate-900/10";
        let titleColor = "text-slate-355";
        let pulseClass = "";
        
        // Emojis for each phase
        const stageIcons = ["📝", "🎭", "🎙️", "🔊", "📐", "🎨", "🎬"];
        const icon = stageIcons[idx] || "📽️";
        
        if (stage.status === "success") {
          statusBadge = `<span class="px-2 py-0.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[9px] font-bold flex items-center space-x-1"><span>●</span> <span>已就绪</span></span>`;
          borderClass = "border-emerald-500/25";
          bgClass = "bg-emerald-500/[0.02]";
          titleColor = "text-emerald-300 font-semibold";
        } else if (stage.status === "failed") {
          statusBadge = `<span class="px-2 py-0.5 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20 text-[9px] font-bold flex items-center space-x-1"><span>●</span> <span>失败</span></span>`;
          borderClass = "border-rose-500/25";
          bgClass = "bg-rose-500/[0.02]";
          titleColor = "text-rose-300 font-semibold";
        } else if (stage.status === "running") {
          statusBadge = `<span class="px-2 py-0.5 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[9px] font-bold animate-pulse flex items-center space-x-1"><span>●</span> <span>运行中</span></span>`;
          borderClass = "border-amber-500/40";
          bgClass = "bg-amber-500/[0.04]";
          titleColor = "text-amber-300 font-semibold";
          pulseClass = "shadow-[0_0_15px_rgba(245,158,11,0.08)] scale-[1.01]";
        } else {
          statusBadge = `<span class="px-2 py-0.5 rounded-lg bg-slate-800/40 text-slate-500 border border-slate-800 text-[9px] font-semibold flex items-center space-x-1"><span>●</span> <span>等待中</span></span>`;
        }
        
        const stageEl = document.createElement("div");
        stageEl.className = `p-4 rounded-2xl border ${borderClass} ${bgClass} ${pulseClass} space-y-3 transition-all duration-300 hover:border-indigo-500/30`;
        
        let headerHtml = `
          <div class="flex justify-between items-start cursor-pointer" onclick="document.getElementById('stageCalls_${idx}').classList.toggle('hidden')">
            <div class="space-y-1">
              <div class="text-[9px] text-slate-500 font-mono tracking-widest uppercase">STAGE 0${idx+1}</div>
              <div class="text-xs ${titleColor} flex items-center space-x-1.5">
                <span class="text-sm select-none">${icon}</span>
                <span>${stage.name}</span>
              </div>
            </div>
            <div class="flex items-center space-x-2">
              ${statusBadge}
              <span class="text-[9px] text-slate-600 font-mono select-none">▼</span>
            </div>
          </div>
        `;
        
        let callsHtml = `<div id="stageCalls_${idx}" class="hidden pt-3 border-t border-slate-850/50 space-y-2.5">`;
        if (stage.calls.length === 0) {
          callsHtml += `<div class="text-[10px] text-slate-655 italic pl-1 font-light">等待前置流水线推进以唤醒此节点...</div>`;
        } else {
          stage.calls.forEach((call, callIdx) => {
            const callOkMark = call.ok 
              ? `<span class="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[8px] font-bold">OK</span>` 
              : `<span class="px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/20 text-[8px] font-bold">ERROR</span>`;
              
            const callTime = call.time ? call.time.split("T")[1].slice(0, 8) : "";
            
            callsHtml += `
              <div class="p-3 rounded-xl bg-slate-950/60 border border-slate-900 space-y-2">
                <div class="flex justify-between items-center text-[10px]">
                  <span class="font-bold text-slate-400 font-mono text-[9px] bg-slate-900 px-1.5 py-0.5 rounded border border-slate-850">${callTime}</span>
                  <span class="font-bold text-indigo-300 text-[10px] tracking-wide">${call.step_cn}</span>
                  <span>${callOkMark}</span>
                </div>
                <div class="flex justify-between items-center text-[9px] text-slate-500 font-mono">
                  <span>🤖 模型: ${call.model || '-'}</span>
                  <span>⚡ 耗时: ${call.duration.toFixed(2)}s (第 ${call.attempt} 次)</span>
                </div>
            `;
            if (call.error) {
              callsHtml += `
                <div class="text-[9px] text-rose-400/90 font-mono bg-rose-950/20 p-2 rounded-lg border border-rose-900/30 overflow-x-auto whitespace-pre leading-relaxed">
                  Error Detail: ${call.error}
                </div>
              `;
            }
            callsHtml += `</div>`;
          });
        }
        
        if (stage.calls.length > 0) {
          headerHtml += `
            <div class="flex justify-between items-center text-[9px] text-slate-500 font-mono pt-2 border-t border-slate-850/20">
              <span>⏱️ 累计开销: <span class="text-indigo-400 font-semibold">${totalDuration.toFixed(2)}s</span></span>
              <span>📡 调用次数: <span class="text-slate-400 font-semibold">${attemptsCount}次</span></span>
            </div>
          `;
        }
        
        callsHtml += `</div>`;
        stageEl.innerHTML = headerHtml + callsHtml;
        listEl.appendChild(stageEl);
      });
    }"""
html = html.replace(old_backstage, new_backstage)

# 8. Add defensive checks inside other recovery fields in case elements are missing
html_path.write_text(html, encoding="utf-8")
print("SUCCESS: HTML Patcher script ran completely!")
