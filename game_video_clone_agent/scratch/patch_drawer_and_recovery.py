from pathlib import Path

html_path = Path("palette_studio.html")
html = html_path.read_text(encoding="utf-8")

# 1. Add CSS Style right before </style>
old_style_end = "  </style>"
new_style = """    /* 侧边审计抽屉展开 */
    #backstageDrawer.open {
      transform: translateX(0);
    }
  </style>"""

assert old_style_end in html, "Could not find </style> in palette_studio.html"
html = html.replace(old_style_end, new_style, 1)
print("1. Added backstageDrawer CSS styles successfully.")


# 2. Add sessionRestoreModal and backstageDrawer right before <!-- 主应用大布局 -->
old_layout_start = "  <!-- 主应用大布局 -->"
new_modals = """  <!-- 全局历史会话恢复模态弹窗 -->
  <div id="sessionRestoreModal" class="fixed inset-0 z-50 hidden flex items-center justify-center p-4 bg-black/85 backdrop-blur-md">
    <div class="w-full max-w-lg bg-[#0D1127] border border-indigo-500/20 rounded-2xl shadow-2xl p-6 text-center space-y-6">
      <div class="w-16 h-16 bg-indigo-500/10 text-indigo-400 rounded-full flex items-center justify-center mx-auto text-3xl border border-indigo-500/20 animate-bounce">
        🎬
      </div>
      <div class="space-y-2">
        <h3 class="text-lg font-bold text-slate-100">🎉 探测到上一次未完成的电影现场！</h3>
        <p class="text-xs text-slate-400 leading-relaxed">
          大导演，系统为您安全恢复了上一次活跃的项目进度。您可以一键重回退出的那一幕，无缝继续大作的创作！
        </p>
      </div>
      
      <div class="bg-slate-950/60 border border-slate-900 rounded-xl p-4 text-left space-y-2.5">
        <div class="flex justify-between items-center text-xs">
          <span class="text-slate-500">活跃批次 ID:</span>
          <span id="restoreRunId" class="font-mono text-indigo-400 font-bold">Run_...</span>
        </div>
        <div class="flex justify-between items-center text-xs">
          <span class="text-slate-500">自愈推荐断点:</span>
          <span id="restoreRecommendStage" class="px-2 py-0.5 rounded bg-indigo-900/40 text-indigo-300 font-bold border border-indigo-800/40 text-[10px]">C 界面</span>
        </div>
      </div>
      
      <div class="pt-2 flex justify-center space-x-4">
        <button onclick="document.getElementById('sessionRestoreModal').classList.add('hidden')" class="px-5 py-2.5 bg-slate-850 hover:bg-slate-800 text-slate-400 font-semibold text-xs rounded-xl transition border border-slate-800 cursor-pointer">
          放弃恢复，开启新片 ✕
        </button>
        <button onclick="restoreSession()" class="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs rounded-xl transition-all shadow-lg shadow-indigo-600/30 flex items-center space-x-1 cursor-pointer">
          <span>🚀 恢复现场并继续</span>
        </button>
      </div>
    </div>
  </div>

  <!-- 📊 右侧抽屉：后台引擎实时审计大盘 -->
  <div id="backstageDrawer" class="fixed top-0 right-0 bottom-0 w-96 bg-[#070A18]/95 border-l border-indigo-950/50 shadow-[-10px_0_30px_rgba(0,0,0,0.5)] z-40 transform translate-x-full transition-transform duration-500 backdrop-blur-xl flex flex-col">
    <!-- Drawer Header -->
    <div class="h-16 px-6 border-b border-slate-900/60 flex items-center justify-between shrink-0">
      <div class="flex items-center space-x-2.5">
        <span class="text-xs font-bold tracking-widest text-slate-100">📊 后台引擎实时审计大盘</span>
      </div>
      <button onclick="toggleBackstageDrawer()" class="text-slate-400 hover:text-slate-200 text-xs cursor-pointer">
        ✕ 关闭
      </button>
    </div>
    
    <!-- Drawer Content -->
    <div class="flex-1 overflow-y-auto p-6 space-y-6 no-scrollbar" id="backstageDrawerContent">
      <p class="text-[10px] text-slate-500 leading-relaxed">
        大盘实时解析活跃 Run 目录下 <code class="font-mono text-indigo-400">后台/</code> 7 大流水线目录审计日志，追踪每一步 LLM/生图 API 小步尝试与详细耗时。当前正在监听中...
      </p>
      
      <div id="backstageStageList" class="space-y-4">
        <!-- 阶段节点数据动态渲染 -->
      </div>
    </div>
  </div>

  <!-- 主应用大布局 -->"""

assert old_layout_start in html, "Could not find layout start in palette_studio.html"
html = html.replace(old_layout_start, new_modals, 1)
print("2. Added modals and backstageDrawer successfully.")


# 3. Add backstage monitor button to header
old_badge = '<div id="connectionBadge" class="flex items-center space-x-2 text-[10px] font-mono tracking-widest px-3 py-1.5 rounded bg-slate-900 border border-slate-800 text-red-400">'
if old_badge not in html:
    # Try alternate classes or search connectionBadge
    print("WARNING: Exact connectionBadge not found, trying alternate matching...")
    import re
    pattern = r'(<div id="connectionBadge".*?>)'
    html, count = re.subn(pattern, r"""<!-- 📊 后台监控大盘按钮 -->
          <button id="backstageMonitorBtn" onclick="toggleBackstageDrawer()" class="flex items-center space-x-2 text-[10px] font-mono tracking-widest px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-indigo-400 hover:text-indigo-300 hover:border-indigo-500/30 transition shadow-inner cursor-pointer mr-2">
            <span class="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-ping"></span>
            <span>📊 后台引擎监控</span>
          </button>
          \1""", html, 1)
    print(f"Header button replacement count: {count}")
else:
    new_badge = """<!-- 📊 后台监控大盘按钮 -->
          <button id="backstageMonitorBtn" onclick="toggleBackstageDrawer()" class="flex items-center space-x-2 text-[10px] font-mono tracking-widest px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-indigo-400 hover:text-indigo-300 hover:border-indigo-500/30 transition shadow-inner cursor-pointer mr-2">
            <span class="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-ping"></span>
            <span>📊 后台引擎监控</span>
          </button>
          <div id="connectionBadge" class="flex items-center space-x-2 text-[10px] font-mono tracking-widest px-3 py-1.5 rounded bg-slate-900 border border-slate-800 text-red-400">"""
    html = html.replace(old_badge, new_badge, 1)
    print("3. Added backstage monitor button to header successfully.")


# 4. Modify event listener to trigger session recovery
old_listener = "window.addEventListener('pywebviewready', function() { checkApiConnection(); });"
new_listener = """window.addEventListener('pywebviewready', function() { 
      checkApiConnection(); 
      detectRestorableSession();
    });"""

assert old_listener in html, "Could not find event listener in palette_studio.html"
html = html.replace(old_listener, new_listener, 1)
print("4. Updated pywebviewready event listener successfully.")


# 5. Add all JS functions after onBackendProgress
old_progress = """    function onBackendProgress(stage, percent, message) {
      console.log('[Bridge] ' + stage + ' ' + percent + '% - ' + message);
      var logEl = document.getElementById('assistantLogText');
      if (logEl && message) { logEl.innerText = message; }
    }"""

new_js = """    function onBackendProgress(stage, percent, message) {
      console.log('[Bridge] ' + stage + ' ' + percent + '% - ' + message);
      var logEl = document.getElementById('assistantLogText');
      if (logEl && message) { logEl.innerText = message; }
    }

    // ── 📊 后台大盘实时审计面板逻辑 ──
    let backstageInterval = null;
    
    function toggleBackstageDrawer() {
      const drawer = document.getElementById("backstageDrawer");
      drawer.classList.toggle("open");
      
      const isOpen = drawer.classList.contains("open");
      if (isOpen) {
        updateBackstageDrawer();
        if (!backstageInterval) {
          backstageInterval = setInterval(updateBackstageDrawer, 2000);
        }
      } else {
        if (backstageInterval) {
          clearInterval(backstageInterval);
          backstageInterval = null;
        }
      }
    }
    
    async function updateBackstageDrawer() {
      if (typeof pywebview === 'undefined' || !pywebview.api) return;
      try {
        const res = await pywebview.api.get_realtime_audit_logs();
        if (res.status === "success") {
          renderBackstageData(res.stages);
        }
      } catch (err) {
        console.error("Failed to fetch backstage audit logs:", err);
      }
    }
    
    function renderBackstageData(stages) {
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
        let titleColor = "text-slate-300";
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
          callsHtml += `<div class="text-[10px] text-slate-500 italic pl-1 font-light">等待前置流水线推进以唤醒此节点...</div>`;
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
    }

    // ── 🔄 历史会话检测与一键断点恢复逻辑 ──
    let restorableSessionData = null;
    
    async function detectRestorableSession() {
      if (typeof pywebview === 'undefined' || !pywebview.api) return;
      try {
        const res = await pywebview.api.get_restorable_session();
        if (res.status === "success" && res.run_id) {
          restorableSessionData = res;
          
          document.getElementById("restoreRunId").innerText = res.run_id;
          
          let cnStage = "C 剧本编写";
          if (res.stage === "D1") cnStage = "D1 定妆照展示";
          else if (res.stage === "E") cnStage = "E 分镜底片大网格";
          else if (res.stage === "F") cnStage = "F 最终多轨合并与电影放映室";
          
          document.getElementById("restoreRecommendStage").innerText = cnStage;
          document.getElementById("sessionRestoreModal").classList.remove("hidden");
        }
      } catch (err) {
        console.error("Failed to detect restorable session:", err);
      }
    }
    
    function restoreSession() {
      if (!restorableSessionData) return;
      document.getElementById("sessionRestoreModal").classList.add("hidden");
      performSessionRecovery(restorableSessionData);
    }
    
    function performSessionRecovery(res) {
      if (!res) return;
      showToast("🔄 正在从后台读取项目进度并全盘治愈状态树...");
      
      // 1. 恢复基本变量
      state.modePath = res.mode_path;
      state.seed = res.seed;
      state.extractedEntities = res.entities;
      state.polishEnabled = res.polish_enabled;
      
      // 同步顶部状态灯
      document.getElementById("activeStateBadge").innerText = `STATUS: SCREEN_${res.stage}`;
      
      // 2. 恢复剧本大纲
      if (res.synopsis) {
        state.rawScript = res.synopsis.synopsis || "";
        
        const rawScriptEl = document.getElementById("rawScriptTextarea");
        if (rawScriptEl) {
          rawScriptEl.value = res.synopsis.synopsis || "";
        }
        
        const d1VoiceoverEl = document.getElementById("d1VoiceoverOutput");
        if (d1VoiceoverEl) {
          d1VoiceoverEl.innerText = res.synopsis.synopsis || "";
        }
      }
      
      // 3. 恢复定妆卡片
      if (res.assets && res.assets.length > 0) {
        state.assets = res.assets;
        state.assets.forEach((ast, idx) => {
          const nameEl = document.getElementById(`cardName${idx}`);
          const promptEl = document.getElementById(`cardPrompt${idx}`);
          const imgEl = document.getElementById(`cardImg${idx}`);
          
          if (nameEl) nameEl.innerText = ast.name || "";
          if (promptEl) promptEl.innerText = ast.prompt || "";
          if (imgEl && ast.image_url) {
            imgEl.innerHTML = `<img src="${ast.image_url}" class="w-full h-full object-cover group-hover:scale-105 transition duration-500" />`;
          }
        });
      }
      
      // 4. 恢复分镜 (v4.0 16宫格模式)
      if (res.grids && res.grids.length > 0) {
        state.storyboardGrids = res.grids;
        renderStoryboardGrids();
      } else if (res.frames && res.frames.length > 0) {
        state.storyboards = res.frames;
      }
      
      // 5. 恢复最终视频
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

    // ── ✍️ D2 大纲意见反馈重写逻辑 ──
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

assert old_progress in html, "Could not find onBackendProgress function in palette_studio.html"
html = html.replace(old_progress, new_js, 1)
print("5. Added all JS logic including applyD2Feedback and backstage audit logs successfully.")

html_path.write_text(html, encoding="utf-8")
print("SUCCESS: patch_drawer_and_recovery.py script ran completely!")
