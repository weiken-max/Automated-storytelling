
    // ── 🎨 全局状态定义 ──
    const state = {
      appState: "SCREEN_A",
      selectedColor: "",
      modePath: "RED", 
      polishEnabled: false,
      channels: [],
      activeChannelId: "ch_drama",

      // 后台真实提示词预设组装库入库
      presets: {
        cast: "[character]\nA cute cartoon stickman style representation of {entity}. Flat colors, strong outline, white background.\n\n[scene]\nA flat 2D vector style minimalist cartoon background scenery depicting {entity}. Flat shades, no character.\n\n[prop]\nA flat 2D vector icon cartoon object depicting {entity}. Primitive shape, flat color fill, white background.",
        image: "High-quality 2D vector cartoon, bold black outlines, vibrant flat colors with soft cel-shading. Style inspired by Cyanide and Happiness but with professional lighting and detailed illustrated backgrounds. Character proportions: stick figure limbs, round bean heads.",
        polish: "你是一位专业的资深编剧与剧本医生。\n任务：请阅读用户提供的原始素材（梗概、片段或小说节选均可），在【完全保留用户原始创意、情节走向和核心设定】的前提下，进行专业润色，并补充与盲盒梗概同规格的结构化字段。\n\n润色要求：\n1. 语言风格：使文字更具画面感（Visual Thinking），多用具象动词，少用空泛形容词；**禁止**强行套用「阶层跃迁」「利益算计」等固定套路，除非用户原文已包含类似内核。\n2. 节奏与体量：优化起承转合与悬念，整体梗概总长度须符合后续约 1700 字旁白体量的信息密度，且 synopsis 与 synopsis_acts 拼接总字符数不得超过 1500（汉字+标点）。\n3. 分幕结构：必须输出 synopsis_acts 数组，长度恰好为 6；每幕为连续叙事，幕内不要写「第X幕」小标题，按时间顺序串成一条故事线。\n4. **行业潜规则 industry_rules**：与盲盒大纲一致，输出 1～4 条数组，概括本作可被影像化的矛盾机制或环境张力（非教条）。\n\n输出：**仅** JSON（键名固定）：\n{\n  \"synopsis_acts\": [共6个字符串，依次为第1幕…第6幕],\n  \"synopsis\": \"将 synopsis_acts 用两个换行符拼接的全文，与各幕一致\",\n  \"short_title\": \"12字以内的短片标题，用于飞书卡片抬头\",\n  \"era\": \"时代背景\",\n  \"identity\": \"主角身份或称谓\",\n  \"industry_rules\": [\"……\"]\n}",
        voiceover: "你是一个极其冷峻、犀利的短视频旁白文案大师。\n任务：按用户指示写出**一段**沉浸式旁白（不是全文，只是连续叙事中的一段）。\n\n【写作铁律】\n1. **一镜到底**：禁止使用段落小标题（如 Level、第一阶段）。用时间流逝、场景升级、数字与利益推进。\n2. **第二人称**：全程使用「你」，极简冷峻，少用形容词。\n3. **纯净文本**：禁止 <subshot>、禁止 [CUT]、禁止任何分镜标签。\n4. **本段体量**：本段目标约 {seg_target} 字（允许 ±10%）。\n\n输出要求：**只输出旁白正文**，不要标题、不要 JSON、不要代码围栏、不要解释。",
        outline: "你是一个极其冷酷的现实主义编剧与行业规则解剖师。\n任务：根据用户给出的主题，设计一个充满【利益算计】、【阶层跃迁】与【人性异化】的第二人称人生副本梗概。\n\n要求：\n1. **隐性阶层结构**：故事在底层逻辑上必须包含清晰的跃迁轨迹（入局 -> 进阶 -> 掌权 -> 巅峰与反噬），但绝不使用任何等级或Level标签。\n2. **核心科普（潜规则拆解）**：将该行业的核心运作机制、灰产逻辑或权力分配规则，作为主角晋升的关键武器。不要枯燥说教，要通过主角的“具体决定”和“利益交换”来展现。\n3. **数字与代价**：故事推进必须伴随具体的数字（金钱、份额、时间）以及主角为了权力所抛弃的底线。\n4. **结局闭环**：巅峰时刻必须伴随绝对的冷酷与孤独，主角最终要彻底沦为庞大系统的“宿命囚徒”或面临命运的黑色幽默式反噬。\n5. **分幕结构（硬性）**：必须输出 synopsis_acts 数组，长度恰好为 6，每个元素对应一幕的连续叙事；幕内不要用「第X幕」等小标题；时间顺序从第 1 幕到最后一幕衔接成一条故事线。\n6. **总字数**：`synopsis` 与 `synopsis_acts` 拼接后的总字符数（汉字+标点）不得超过 1500，逻辑必须极其严密。\n\n请输出 JSON 格式（键名固定）：\n{\n  \"synopsis_acts\": [共6个字符串，依次为第1幕…第6幕梗概正文],\n  \"synopsis\": \"将 synopsis_acts 用两个换行符拼接成的全文，必须与各幕内容完全一致\",\n  \"era\": \"时代背景\",\n  \"identity\": \"主角的终极身份\",\n  \"industry_rules\": [\"（揭露的1-2个行业深层潜规则）\"]\n}"
      },

      // 后台返回的真实编译结果
      compiledVoiceover: "",
      extractedEntities: [],
      assets: [],      // 定妆照卡片
      storyboards: [], // 分镜帧底片
      relativeVideoPath: "", // 合成视频在 Runs 下的相对路径，如 "Run_xxx/output/narrative_v6_final_epic.mp4"
      
      // 后画后悔药对比备份
      assetHistory: {}, // {card_id: {new_url, old_url}}
      frameHistory: {}, // {frame_idx: {new_url, old_url}}
    };

    // ── 🔌 连接保活状态灯 ──
    function checkApiConnection() {
      fetch("http://127.0.0.1:8000/api/health")
        .then(res => res.json())
        .then(data => {
          if (data.status === "success") {
            document.getElementById("connectionBadge").className = "flex items-center space-x-2 text-[10px] font-mono tracking-widest px-3 py-1.5 rounded bg-slate-900 border border-slate-800 text-emerald-400";
            document.getElementById("badgeLight").className = "w-2 h-2 rounded-full bg-emerald-500 animate-pulse";
            document.getElementById("badgeText").innerText = "STATUS: LIVE (API CONNECTED)";
          }
        })
        .catch(err => {
          document.getElementById("connectionBadge").className = "flex items-center space-x-2 text-[10px] font-mono tracking-widest px-3 py-1.5 rounded bg-slate-900 border border-slate-800 text-red-500";
          document.getElementById("badgeLight").className = "w-2 h-2 rounded-full bg-red-500 animate-pulse";
          document.getElementById("badgeText").innerText = "STATUS: OFFLINE (API DISCONNECTED)";
        });
    }
    
    // 初始化定时检测
    setInterval(checkApiConnection, 5000);
    checkApiConnection();
    
    // 监听 pywebviewready 以触发历史会话自愈检测
    window.addEventListener('pywebviewready', function() { 
      detectRestorableSession();
    });

    // ── 🎨 频道预设库及通道控制 JS ──
    const DEFAULT_PRESETS = {
      cast: "[character]\\nCyanide and Happiness stick figure character sheet of {entity}. Three-view layout (front/side/back). Simple round bean head, stick limbs, flat colors, bold black outlines. Pure white background, no shadows.\\n\\n[scene]\\nFlat 2D vector background scenery depicting {entity}. Clean composition, no characters, minimalist color palette. Pure white background.\\n\\n[prop]\\nFlat 2D vector icon object: {entity}. Primitive shape, flat color fill, bold outline. White background.",
      image: "High-quality 2D vector cartoon, bold black outlines, vibrant flat colors with soft cel-shading. Style inspired by Cyanide and Happiness but with professional lighting and detailed illustrated backgrounds. Character proportions: stick figure limbs, round bean heads.",
      polish: "你是一位专业的资深编剧与剧本医生。\\n任务：请阅读用户提供的原始素材（梗概、片段或小说节选均可），在【完全保留用户原始创意、情节走向和核心设定】的前提下，进行专业润色，并补充与盲盒梗概同规格的结构化字段。\\n\\n润色要求：\\n1. 语言风格：使文字更具画面感（Visual Thinking），多用具象动词，少用空泛形容词；**禁止**强行套用「阶层跃迁」「利益算计」等固定套路，除非用户原文已包含类似内核。\\n2. 节奏与体量：优化起承转合与悬念，整体梗概总长度须符合后续约 1700 字旁白体量的信息密度，且 synopsis 与 synopsis_acts 拼接总字符数不得超过 1500（汉字+标点）。\\n3. 分幕结构：必须输出 synopsis_acts 数组，长度恰好为 6；每幕为连续叙事，幕内不要写「第X幕」小标题，按时间顺序串成一条故事线。\\n4. **行业潜规则 industry_rules**：与盲盒大纲一致，输出 1～4 条数组，概括本作可被影像化的矛盾机制或环境张力（非教条）。\\n\\n输出：**仅** JSON（键名固定）：\\n{\\n  \\\"synopsis_acts\\\": [共6个字符串，依次为第1幕…第6幕],\\n  \\\"synopsis\\\": \\\"将 synopsis_acts 用两个换行符拼接的全文，与各幕一致\\\",\\n  \\\"short_title\\\": \\\"12字以内的短片标题，用于飞书卡片抬头\\\",\\n  \\\"era\\\": \\\"时代背景\\\",\\n  \\\"identity\\\": \\\"主角身份或称谓\\\",\\n  \\\"industry_rules\\\": [\\\"……\\\"]\\n}",
      voiceover: "你是一个极其冷峻、犀利的短视频旁白文案大师。\\n任务：按用户指示写出**一段**沉浸式旁白（不是全文，只是连续叙事中的一段）。\\n\\n【写作铁律】\\n1. **一镜到底**：禁止使用段落小标题（如 Level、第一阶段）。用时间流逝、场景升级、数字与利益推进。\\n2. **第二人称**：全程使用「你」，极简冷峻，少用形容词。\\n3. **纯净文本**：禁止 <subshot>、禁止 [CUT]、禁止任何分镜标签。\\n4. **本段体量**：本段目标约 {seg_target} 字（允许 ±10%）。\\n\\n输出要求：**只输出旁白正文**，不要标题、不要 JSON、不要代码围栏、不要解释。",
      outline: "你是一个极其冷酷的现实主义编剧与行业规则解剖师。\\n任务：根据用户给出的主题，设计一个充满【利益算计】、【阶层跃迁】与【人性异化】的第二人称人生副本梗概。\\n\\n要求：\\n1. **隐性阶层结构**：故事在底层逻辑上必须包含清晰的跃迁轨迹（入局 -> 进阶 -> 掌权 -> 巅峰与反噬），但绝不使用任何等级或Level标签。\\n2. **核心科普（潜规则拆解）**：将该行业的核心运作机制、灰产逻辑或权力分配规则，作为主角晋升的关键武器。不要枯燥说教，要通过主角的“具体决定”和“利益交换”来展现。\\n3. **数字与代价**：故事推进必须伴随具体的数字（金钱、份额、时间）以及主角为了权力所抛弃的底线。\\n4. **结局闭环**：巅峰时刻必须伴随绝对的冷酷与孤独，主角最终要彻底沦为庞大系统的“宿命囚徒”或面临命运 of 黑色幽默式反噬。\\n5. **分幕结构（硬性）**：必须输出 synopsis_acts 数组，长度恰好为 6，每个元素对应一幕的连续叙事；幕内不要用「第X幕」等小标题；时间顺序从第 1 幕到最后一幕衔接成一条故事线。\\n6. **总字数**：`synopsis` 与 `synopsis_acts` 拼接后的总字符数（汉字+标点）不得超过 1500，逻辑必须极其严密。\\n\\n请输出 JSON 格式（键名固定）：\\n{\\n  \\\"synopsis_acts\\\": [共6个字符串，依次为第1幕…第6幕],\\n  \\\"synopsis\\\": \\\"将 synopsis_acts 用两个换行符拼接的全文，必须与各幕内容完全一致\\\",\\n  \\\"era\\\": \\\"时代背景\\\",\\n  \\\"identity\\\": \\\"主角的终极身份\\\",\\n  \\\"industry_rules\\\": [\\\"（揭露的1-2个行业深层潜规则）\\\"]\\n}",
      storyboard: "【画画表现】\\nCyanide and Happiness stick figure. Style inspired by comic cartoon, 2D vector, bold black outlines, vivid flat color fills, white background."
    };

    const DEFAULT_CHANNELS = [
      {
        id: "ch_drama",
        channelType: "drama",
        name: "剧情故事",
        emoji: "🎭",
        color: "#EF4444",
        locked: true,
        presets: null
      },
      {
        id: "ch_science",
        channelType: "science",
        name: "硬核科普",
        emoji: "🔬",
        color: "#F59E0B",
        locked: true,
        presets: {
          outline: "你是一个极其冷酷的现实主义编剧与行业规则解剖师。\\n任务：根据用户给出的主题，设计一个充满利益算计、阶层跃迁与人性异化的第二人称人生副本梗概。\\n分幕结构硬性：输出 synopsis_acts 数组，长度恰好为 6。总字数不超过 1500。\\n输出 JSON：\\n{\"synopsis_acts\":[6个字符串],\"synopsis\":\"全文\",\"era\":\"时代\",\"identity\":\"主角终极身份\",\"industry_rules\":[\"潜规则\"]}",
          storyboard: "【画画表现】\\nCyanide and Happiness stick figure. Style inspired by comic cartoon, 2D vector, bold black outlines, vivid flat color fills, white background."
        }
      }
    ];

    function initChannels() {
      const stored = localStorage.getItem("palette_channels_v3");
      if (stored) {
        try {
          state.channels = JSON.parse(stored);
        } catch (e) {
          state.channels = JSON.parse(JSON.stringify(DEFAULT_CHANNELS));
        }
      } else {
        state.channels = JSON.parse(JSON.stringify(DEFAULT_CHANNELS));
      }
      
      state.channels.forEach(ch => {
        if (!ch.channelType) {
          ch.channelType = (ch.id === "ch_drama") ? "drama" : "science";
        }
      });

      const ch = state.channels.find(c => c.id === state.activeChannelId) || state.channels[0];
      if (ch) {
        state.presets = getChannelPresets(ch);
      }
    }

    function getChannelPresets(channel) {
      if (!channel.presets) return { ...DEFAULT_PRESETS };
      return {
        image:      channel.presets.image      || DEFAULT_PRESETS.image,
        polish:     channel.presets.polish     || DEFAULT_PRESETS.polish,
        voiceover:  channel.presets.voiceover  || DEFAULT_PRESETS.voiceover,
        outline:    channel.presets.outline    || DEFAULT_PRESETS.outline,
        storyboard: channel.presets.storyboard || DEFAULT_PRESETS.storyboard,
        cast:       channel.presets.cast       || DEFAULT_PRESETS.cast
      };
    }

    function renderChannelGrid() {
      const grid = document.getElementById("channelGrid");
      const addBtn = document.getElementById("addChannelBtn");
      if (addBtn) addBtn.style.display = state.channels.length >= 8 ? "none" : "";
      
      if (!grid) return;
      
      if (!state.channels || state.channels.length === 0) {
        grid.innerHTML = `
          <div class="col-span-full text-center py-8 text-slate-500 text-xs font-mono">
            暂无频道，请点击下方新增按钮创建
          </div>
        `;
        return;
      }
      
      grid.innerHTML = state.channels.map(ch => {
        const isLocked = !!ch.locked;
        const badge = isLocked 
          ? `<span class="px-2 py-0.5 rounded bg-slate-950/80 border border-slate-800 text-slate-500 text-[8px]">🔒 原厂</span>`
          : `<span class="px-2 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-[8px]">🎨 自建</span>`;
        
        return `
          <div onclick="activateChannel('${ch.id}', event)" 
               class="group relative p-5 bg-[#080C1E]/80 border border-slate-850 hover:border-indigo-500/50 rounded-2xl cursor-pointer transition-all duration-300 hover:scale-[1.02] flex flex-col justify-between min-h-[140px] shadow-lg hover:shadow-indigo-500/5">
            <div class="flex justify-between items-start">
              <span class="text-3xl">${ch.emoji || '🎬'}</span>
              ${badge}
            </div>
            
            <div class="mt-4 space-y-2">
              <h3 class="text-sm font-bold text-slate-200 group-hover:text-indigo-300 transition">${ch.name}</h3>
              <div class="flex justify-between items-center text-[10px] text-slate-500">
                <span>${ch.channelType === 'drama' ? '🎭 剧情模式' : '🧪 科普模式'}</span>
                <button onclick="event.stopPropagation(); openChannelEditor('${ch.id}')" 
                        class="px-2 py-1 bg-slate-900 border border-slate-800 hover:border-indigo-500/40 text-slate-400 hover:text-indigo-300 text-[9px] rounded-lg transition-all flex items-center space-x-1 cursor-pointer">
                  <span>⚙️ 🎬 提示词</span>
                </button>
              </div>
            </div>
          </div>
        `;
      }).join("");
    }

    function activateChannel(channelId, event) {
      const ch = state.channels.find(c => c.id === channelId);
      if (!ch) return;

      state.activeChannelId = channelId;
      state.modePath = (ch.channelType === "drama") ? "CH_DRAMA" : ch.id.toUpperCase();
      state.presets = getChannelPresets(ch);

      loadChannelDraft();

      if (event) {
        const splash = document.getElementById("splashCircle");
        if (splash) {
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
      } else {
        navigateTo("C1");
      }
    }

    function loadChannelDraft() {
      const draft = localStorage.getItem(`palette_draft_${state.activeChannelId}`) || "";
      const ta = document.getElementById("rawScriptTextarea");
      if (ta) {
        ta.value = draft;
        state.rawScript = draft;
      }
      updateJsonPayloadViewer();
    }

    function getActiveChannel() {
      return state.channels.find(c => c.id === state.activeChannelId) || state.channels[0];
    }

    function saveChannelsToStorage() {
      localStorage.setItem("palette_channels_v3", JSON.stringify(state.channels));
      if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.save_channels) {
        pywebview.api.save_channels(state.channels).catch(() => {});
      }
    }

    const CHANNEL_COLORS = [
      "#EF4444","#F59E0B","#10B981","#3B82F6","#8B5CF6",
      "#EC4899","#06B6D4","#F97316","#84CC16","#6366F1"
    ];
    let _editingChannelId = null;

    function openChannelEditor(channelId) {
      _editingChannelId = channelId;
      const modal = document.getElementById("channelEditorModal");
      const deleteBtn = document.getElementById("chEditorDeleteBtn");
      const rollbackBtn = document.getElementById("chEditorRollbackBtn");
      
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
        document.getElementById("chEditorOutline").value    = ch.presets?.outline    || presets.outline || '';
        document.getElementById("chEditorImage").value      = ch.presets?.image      || '';
        document.getElementById("chEditorVoiceover").value  = ch.presets?.voiceover  || '';
        document.getElementById("chEditorPolish").value     = ch.presets?.polish     || '';
        document.getElementById("chEditorStoryboard").value = ch.presets?.storyboard || '';
        document.getElementById("chEditorCast").value       = ch.presets?.cast       || '';
        
        const chType = ch.channelType || "science";
        document.querySelectorAll('input[name="chChannelType"]').forEach(r => {
          r.checked = (r.value === chType);
          r.disabled = !!ch.locked;
        });
        document.getElementById("chTypeRow").style.opacity = ch.locked ? "0.55" : "1";
        _syncChannelTypeStyle();
        
        deleteBtn.classList.toggle("hidden", !!ch.locked);
        rollbackBtn.classList.toggle("hidden", !ch.presetsBackup);
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
        document.getElementById("chEditorCast").value = "";
        
        document.querySelectorAll('input[name="chChannelType"]').forEach(r => {
          r.checked = (r.value === "science");
          r.disabled = false;
        });
        document.getElementById("chTypeRow").style.opacity = "1";
        _syncChannelTypeStyle();
        
        deleteBtn.classList.add("hidden");
        rollbackBtn.classList.add("hidden");
      }
      
      modal.classList.remove("hidden");
    }

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
      const voiceover = document.getElementById("chEditorVoiceover").value.trim();
      const polish = document.getElementById("chEditorPolish").value.trim();
      const storyboard = document.getElementById("chEditorStoryboard").value.trim();
      const cast = document.getElementById("chEditorCast").value.trim();
      const channelType = document.querySelector('input[name="chChannelType"]:checked')?.value || "science";
      
      const hasCustomPresets = outline || image || voiceover || polish || storyboard || cast;
      
      if (_editingChannelId) {
        const idx = state.channels.findIndex(c => c.id === _editingChannelId);
        if (idx !== -1) {
          if (state.channels[idx].presets) {
            state.channels[idx].presetsBackup = JSON.parse(JSON.stringify(state.channels[idx].presets));
          }
          state.channels[idx].name = name;
          state.channels[idx].emoji = emoji;
          if (!state.channels[idx].locked) {
            state.channels[idx].color = color;
            state.channels[idx].channelType = channelType;
            state.channels[idx].presets = hasCustomPresets ? { outline, image, voiceover, polish, storyboard, cast } : null;
          } else {
            state.channels[idx].presets = hasCustomPresets ? { outline, image, voiceover, polish, storyboard, cast } : null;
          }
        }
        showToast(`✅ 频道「${name}」已更新！`);
      } else {
        const newId = "ch_custom_" + Date.now();
        state.channels.push({
          id: newId,
          channelType,
          name,
          emoji,
          color,
          locked: false,
          presets: hasCustomPresets ? { outline, image, voiceover, polish, storyboard, cast } : null
        });
        showToast(`🎉 频道「${name}」已创建！`);
      }
      
      if (_editingChannelId === state.activeChannelId) {
        const ch = state.channels.find(c => c.id === _editingChannelId);
        if (ch) state.presets = getChannelPresets(ch);
      }
      
      saveChannelsToStorage();
      closeChannelEditor();
      renderChannelGrid();
    }

    function rollbackChannelPresets() {
      if (!_editingChannelId) return;
      const ch = state.channels.find(c => c.id === _editingChannelId);
      if (!ch || !ch.presetsBackup) {
        showToast("⚠️ 没有可回滚的备份版本！");
        return;
      }
      const bak = ch.presetsBackup;
      document.getElementById("chEditorOutline").value    = bak.outline    || '';
      document.getElementById("chEditorImage").value      = bak.image      || '';
      document.getElementById("chEditorVoiceover").value  = bak.voiceover  || '';
      document.getElementById("chEditorPolish").value     = bak.polish     || '';
      document.getElementById("chEditorStoryboard").value = bak.storyboard || '';
      document.getElementById("chEditorCast").value       = bak.cast       || '';
      showToast("🔙 提示词已还原至上一个保存版本！");
    }

    function confirmDeleteChannel() {
      const ch = state.channels.find(c => c.id === _editingChannelId);
      if (!ch || ch.locked) { showToast("🔒 原厂频道受保护，不可删除！"); return; }
      showCustomModal(
        "🗑️ 确认删除频道",
        `即将删除频道「${ch.name}」，该频道的专属提示词与草稿将一并清除，此操作不可撤销。`,
        "确认删除",
        true,
        () => deleteChannel(_editingChannelId)
      );
    }

    function deleteChannel(channelId) {
      const ch = state.channels.find(c => c.id === channelId);
      if (!ch || ch.locked) return;
      state.channels = state.channels.filter(c => c.id !== channelId);
      localStorage.removeItem(`palette_draft_${channelId}`);
      saveChannelsToStorage();
      closeChannelEditor();
      renderChannelGrid();
      showToast(`🗑️ 频道「${ch.name}」已删除。`);
    }

    // ── 📝 自动草稿箱机制 ──
    window.addEventListener("load", () => {
      initChannels();
      renderChannelGrid();
      loadChannelDraft();
      
      // 初始化提示词文本区内容
      document.getElementById("promptText-image").value = state.presets.image;
      document.getElementById("promptText-polish").value = state.presets.polish;
      document.getElementById("promptText-voiceover").value = state.presets.voiceover;
      document.getElementById("promptText-outline").value = state.presets.outline;
      
      updateJsonPayloadViewer();
    });

    function syncRawScriptToState() {
      const text = document.getElementById("rawScriptTextarea").value;
      state.rawScript = text;
      localStorage.setItem(`palette_draft_${state.activeChannelId}`, text);
      updateJsonPayloadViewer();
    }

    function syncPromptToState(cat) {
      const text = document.getElementById(`promptText-${cat}`).value;
      state.presets[cat] = text;
      localStorage.setItem("palette_draft_presets", JSON.stringify(state.presets));
      updateJsonPayloadViewer();
    }

    // ── 🛠️ 弹窗与吐司通知 ──
    function showToast(text, duration = 3000) {
      const toast = document.getElementById("toastNotification");
      document.getElementById("toastText").innerText = text;
      toast.classList.remove("hidden");
      setTimeout(() => toast.classList.add("hidden"), duration);
    }

    function showCustomModal(title, desc, primaryText = "我知道了", showCancel = false, primaryCallback = null) {
      document.getElementById("modalTitle").innerText = title;
      document.getElementById("modalDesc").innerText = desc;
      
      const pBtn = document.getElementById("modalPrimaryBtn");
      pBtn.innerText = primaryText;
      pBtn.onclick = () => {
        closeCustomModal();
        if (primaryCallback) primaryCallback();
      };

      const sBtn = document.getElementById("modalSecBtn");
      if (showCancel) {
        sBtn.classList.remove("hidden");
      } else {
        sBtn.classList.add("hidden");
      }

      document.getElementById("customModal").classList.remove("hidden");
    }

    function closeCustomModal() {
      document.getElementById("customModal").classList.add("hidden");
    }

    // ── 🔄 页面导航状态机 ──
    function navigateTo(targetState) {
      const screens = ["screenA", "screenB", "screenC1", "screenC2", "screenD1", "screenD2", "screenE", "screenF"];
      screens.forEach(s => document.getElementById(s).classList.add("hidden"));
      
      document.getElementById(`screen${targetState}`).classList.remove("hidden");
      state.appState = `SCREEN_${targetState}`;
      document.getElementById("activeStateBadge").innerText = `STATUS: SCREEN_${targetState}`;
      
      // 色彩模式的UI自适应
      if (targetState === "C1") {
        const indicator = document.getElementById("c1ModeIndicator");
        const launchBtn = document.getElementById("c1LaunchBtn");
        
        if (state.modePath === "RED") {
          indicator.className = "w-3 h-3 rounded-full bg-red-500";
          launchBtn.className = "px-8 py-3.5 bg-red-650 hover:bg-red-500 font-bold text-white rounded-xl shadow-lg transition-all flex items-center space-x-2 tracking-wider text-xs uppercase";
          document.getElementById("c1ManualInputArea").classList.remove("hidden");
          document.getElementById("c1ShakeArea").classList.add("hidden");
        } else if (state.modePath === "YELLOW") {
          indicator.className = "w-3 h-3 rounded-full bg-yellow-500";
          launchBtn.className = "px-8 py-3.5 bg-yellow-600 hover:bg-yellow-500 font-bold text-white rounded-xl shadow-lg transition-all flex items-center space-x-2 tracking-wider text-xs uppercase";
          document.getElementById("c1ManualInputArea").classList.remove("hidden");
          document.getElementById("c1ShakeArea").classList.add("hidden");
        } else if (state.modePath === "BLUE") {
          indicator.className = "w-3 h-3 rounded-full bg-blue-500";
          launchBtn.className = "px-8 py-3.5 bg-blue-600 hover:bg-blue-500 font-bold text-white rounded-xl shadow-lg transition-all flex items-center space-x-2 tracking-wider text-xs uppercase";
          document.getElementById("c1ManualInputArea").classList.add("hidden");
          document.getElementById("c1ShakeArea").classList.remove("hidden");
        }
      }
    }

    function handleColorClick(event, color, colorHex, title) {
      state.selectedColor = colorHex;
      state.modePath = color.toUpperCase();
      document.getElementById("selectedModeTitle").innerText = title;
      
      // 触发吞没特效
      const splash = document.getElementById("splashCircle");
      splash.style.left = `${event.clientX}px`;
      splash.style.top = `${event.clientY}px`;
      splash.style.backgroundColor = colorHex;
      splash.classList.add("active");
      
      setTimeout(() => {
        navigateTo("B");
        splash.classList.remove("active");
      }, 1000);
    }

    function resetToHome() {
      navigateTo("A");
    }

    // ── 📝 载入精选故事剧本 Demo ──
    function loadDemoScript() {
      let script = "";
      if (state.modePath === "RED") {
        script = "在 2098 年的霓虹雨夜，老钟表匠擦拭着手里的一枚神秘发光怀表。表盘的指针发生了诡异的逆向旋转，记忆深处的星空誓言再次浮现在眼前。他要在机械坊彻底被大财阀吞噬前，完成最后的时光锁定装置。";
      } else {
        script = "我们每天看到的太阳光，实际上需要穿过极其庞大、密集的太阳内部粒子堆。光子在太阳内部通过『随机漫步』不断折射碰撞，最终在经历约十万年的艰难求索后，才在短短 8 分钟内跨越真空，抵达我们的双眼。";
      }
      document.getElementById("rawScriptTextarea").value = script;
      state.rawScript = script;
      syncRawScriptToState();
      showToast("🎬 电影精选剧本 Demo 已成功载入！");
    }

    // ── 🔒 剧本锁定开关切换 ──
    function togglePolishSwitch() {
      const toggle = document.getElementById("polishToggle");
      state.polishEnabled = toggle.checked;
      
      const tag = document.getElementById("polishStatusTag");
      const desc = document.getElementById("polishDesc");
      
      if (toggle.checked) {
        tag.innerText = "✨ 润色已开启 (智能修饰)";
        tag.className = "px-2 py-0.5 bg-indigo-900 border border-indigo-800 text-[9px] text-indigo-300 rounded";
        desc.innerText = "智能修饰模式：允许大模型对您的原文大纲进行扩写润色，丰富文学色彩，产生更高级的电影分镜。";
      } else {
        tag.innerText = "已关闭 (原稿锁死)";
        tag.className = "px-2 py-0.5 bg-slate-900 border border-slate-800 text-[9px] text-slate-400 rounded";
        desc.innerText = "锁死直出模式：系统将直接物理切片分析您的文字，大模型生成旁白时绝不篡改、增删任何字词，原汁原味透传！";
      }
      
      updateJsonPayloadViewer();
    }

    // ── 🔌 C2 大模型 Prompt 调试组装逻辑 ──
    function switchPromptCategory(cat) {
      const cats = ["image", "polish", "voiceover", "outline"];
      cats.forEach(c => {
        document.getElementById(`promptArea-${c}`).classList.add("hidden");
        document.getElementById(`catBtn-${c}`).className = "w-full text-left p-4 rounded-xl border border-slate-900 bg-slate-950/20 text-slate-400 hover:text-slate-200 transition-all flex flex-col space-y-1";
      });
      
      document.getElementById(`promptArea-${cat}`).classList.remove("hidden");
      document.getElementById(`catBtn-${cat}`).className = "w-full text-left p-4 rounded-xl border border-indigo-500/20 bg-indigo-950/20 text-slate-200 transition-all flex flex-col space-y-1";
    }

    function appendPromptTag(tag) {
      const area = document.getElementById("promptText-image");
      if (area.value.trim().endsWith(",")) {
        area.value = area.value.trim() + " " + tag;
      } else if (area.value.trim() === "") {
        area.value = tag;
      } else {
        area.value = area.value.trim() + ", " + tag;
      }
      syncPromptToState("image");
    }

    function resetSelectedPrompt(cat) {
      let defaults = {
        image: "High-quality 2D vector cartoon, bold black outlines, vibrant flat colors with soft cel-shading. Style inspired by Cyanide and Happiness but with professional lighting and detailed illustrated backgrounds. Character proportions: stick figure limbs, round bean heads.",
        polish: "你是一位专业的资深编剧与剧本医生。\n任务：请阅读用户提供的原始素材（梗概、片段或小说节选均可），在【完全保留用户原始创意、情节走向和核心设定】的前提下，进行专业润色，并补充与盲盒梗概同规格 of 结构化字段。\n\n润色要求：\n1. 语言风格：使文字更具画面感（Visual Thinking），多用具象动词，少用空泛形容词；**禁止**强行套用「阶层跃迁」「利益算计」等固定套路，除非用户原文已包含类似内核。\n2. 节奏与体量：优化起承转合与悬念，整体梗概总长度须符合后续约 1700 字旁白体量的信息密度，且 synopsis 与 synopsis_acts 拼接总字符数不得超过 1500（汉字+标点）。\n3. 分幕结构：必须输出 synopsis_acts 数组，长度恰好为 6；每幕为连续叙事，幕内不要写「第X幕」小标题，按时间顺序串成一条故事线。\n4. **行业潜规则 industry_rules**：与盲盒大纲一致，输出 1～4 条数组，概括本作可被影像化的矛盾机制或环境张力（非教条）。\n\n输出：**仅** JSON（键名固定）：\n{\n  \"synopsis_acts\": [共6个字符串，依次为第1幕…第6幕],\n  \"synopsis\": \"将 synopsis_acts 用两个换行符拼接的全文，与各幕一致\",\n  \"short_title\": \"12字以内的短片标题，用于飞书卡片抬头\",\n  \"era\": \"时代背景\",\n  \"identity\": \"主角身份或称谓\",\n  \"industry_rules\": [\"……\"]\n}",
        voiceover: "你是一个极其冷峻、犀利的短视频旁白文案大师。\n任务：按用户指示写出**一段**沉浸式旁白（不是全文，只是连续叙事中的一段）。\n\n【写作铁律】\n1. **一镜到底**：禁止使用段落小标题（如 Level、第一阶段）。用时间流逝、场景升级、数字与利益推进。\n2. **第二人称**：全程使用「你」，极简冷峻，少用形容词。\n3. **纯净文本**：禁止 <subshot>、禁止 [CUT]、禁止任何分镜标签。\n4. **本段体量**：本段目标约 {seg_target} 字（允许 ±10%）。\n\n输出要求：**只输出旁白正文**，不要标题、不要 JSON、不要代码围栏、不要解释。",
        outline: "你是一个极其冷酷的现实主义编剧与行业规则解剖师。\n任务：根据用户给出的主题，设计一个充满【利益算计】、【阶层跃迁】与【人性异化】的第二人称人生副本梗概。\n\n要求：\n1. **隐性阶层结构**：故事在底层逻辑上必须包含清晰的跃迁轨迹（入局 -> 进阶 -> 掌权 -> 巅峰与反噬），但绝不使用任何等级或Level标签。\n2. **核心科普（潜规则拆解）**：将该行业的核心运作机制、灰产逻辑或权力分配规则，作为主角晋升的关键武器。不要枯燥说教，要通过主角的“具体决定”和“利益交换”来展现。\n3. **数字与代价**：故事推进必须伴随具体的数字（金钱、份额、时间）以及主角为了权力所抛弃的底线。\n4. **结局闭环**：巅峰时刻必须伴随绝对的冷酷与孤独，主角最终要彻底沦为庞大系统的“宿命囚徒”或面临命运的黑色幽默式反噬。\n5. **分幕结构（硬性）**：必须输出 synopsis_acts 数组，长度恰好为 6，每个元素对应一幕的连续叙事；幕内不要用「第X幕」等小标题；时间顺序从第 1 幕到最后一幕衔接成一条故事线。\n6. **总字数**：`synopsis` 与 `synopsis_acts` 拼接后的总字符数（汉字+标点）不得超过 1500，逻辑必须极其严密。\n\n请输出 JSON 格式（键名固定）：\n{\n  \"synopsis_acts\": [共6个字符串，依次为第1幕…第6幕梗概正文],\n  \"synopsis\": \"将 synopsis_acts 用两个换行符拼接成的全文，必须与各幕内容完全一致\",\n  \"era\": \"时代背景\",\n  \"identity\": \"主角的终极身份\",\n  \"industry_rules\": [\"（揭露的1-2个行业深层潜规则）\"]\n}"
      };
      
      document.getElementById(`promptText-${cat}`).value = defaults[cat];
      state.presets[cat] = defaults[cat];
      syncPromptToState(cat);
      showToast("🔄 参数已重置为出厂默认设置。");
    }

    function savePresets() {
      showToast("💾 大模型系统提示词参数已全部同步！");
      setTimeout(() => navigateTo("C1"), 800);
    }

    function updateJsonPayloadViewer() {
      const payload = {
        app_id: "palette-cinema-id",
        mode_path: state.modePath,
        original_text: state.rawScript || "等待输入...",
        pipeline_config: {
          polish_flow: {
            enabled: state.polishEnabled,
            system_prompt: state.polishEnabled ? state.presets.polish : "",
            immutable_lock: !state.polishEnabled
          },
          voiceover_flow: {
            system_prompt: state.presets.voiceover
          },
          render_flow: {
            style_presets: state.presets.image,
            seed: state.seed,
            cast_prompt: state.presets.cast,
            storyboard_prompt: state.presets.storyboard
          }
        }
      };
      document.getElementById("jsonPayloadViewer").innerText = JSON.stringify(payload, null, 2);
    }

    // ── 🎲 摇一摇盲盒 ──
    async function triggerShake() {
      showToast("🔮 选题盲盒抽取中...");
      
      // 摇晃球动画
      const ball = document.getElementById("shakeBallIcon");
      ball.classList.add("animate-bounce");
      
      try {
        const res = await pywebview.api.compile_story({
            app_id: "palette-cinema-id",
            mode_path: "BLUE",
            original_text: "请为为我随机生成一个赛博朋克废土风格的电影梗概故事大纲。",
            pipeline_config: {
              polish_flow: { enabled: true, system_prompt: state.presets.outline },
              voiceover_flow: { system_prompt: state.presets.voiceover },
              render_flow: { style_presets: state.presets.image, seed: 12345 }
            }
          });
        if (res.status === "success") {
          state.rawScript = res.data.compiled_voiceover;
          document.getElementById("shakeOutlineContent").innerText = res.data.compiled_voiceover;
          navigateTo("D2");
        } else {
          showCustomModal("⚠️ 后端排队中", "选题抽取失败，请重试！");
        }
      } catch(err) {
        handleApiError(err, triggerShake);
      } finally {
        ball.classList.remove("animate-bounce");
      }
    }

    function submitD2ToD1() {
      const feedback = document.getElementById("d2FeedbackInput").value;
      if (feedback.trim()) {
        showToast("💡 大纲修订建议已录入...");
      }
      setTimeout(() => {
        handleC1Launch(state.rawScript);
      }, 800);
    }

    // ── ⚡ 核心 Pipeline 处理 ──
    async function handleC1Launch(directText = null) {
      const text = directText || state.rawScript;
      if (!text.trim()) {
        showCustomModal("⚠️ 提示", "大导演，剧本内容不能为空哦，请输入您的创意大纲！");
        return;
      }

      navigateTo("D1");
      
      // 开启双进度条模拟 + 真实交互
      const p1Bar = document.getElementById("p1Bar");
      const p1Val = document.getElementById("p1Val");
      const p2Bar = document.getElementById("p2Bar");
      const p2Val = document.getElementById("p2Val");
      const logText = document.getElementById("assistantLogText");
      
      p1Bar.style.width = "0%";
      p1Val.innerText = "0%";
      p2Bar.style.width = "0%";
      p2Val.innerText = "0%";

      // 安全直出锁标志
      document.getElementById("d1LockBadge").innerText = state.polishEnabled ? "✨ SMART_POLISH_FLOW" : "🔒 ORIGINAL_TEXT_LOCKED";
      document.getElementById("d1LockBadge").className = state.polishEnabled ? "px-2 py-0.5 text-[9px] tracking-widest uppercase font-bold rounded bg-indigo-950 border border-indigo-800 text-indigo-200" : "px-2 py-0.5 text-[9px] tracking-widest uppercase font-bold rounded bg-red-950 border border-red-800/80 text-red-200";

      try {
        // [第1步] 发送文本编译请求
        logText.innerText = "[第1步] 正在呼唤大模型提炼大纲并编译解说旁白文本 (预计 5 秒)...";
        p1Bar.style.width = "40%";
        p1Val.innerText = "40%";

        const cData = await pywebview.api.compile_story({
            app_id: "palette-cinema-id",
            mode_path: state.modePath,
            original_text: text,
            pipeline_config: {
              polish_flow: {
                enabled: state.polishEnabled,
                system_prompt: state.polishEnabled ? state.presets.polish : "",
                immutable_lock: !state.polishEnabled
              },
              voiceover_flow: { system_prompt: state.presets.voiceover },
              render_flow: { 
                style_presets: state.presets.image, 
                seed: state.seed,
                cast_prompt: state.presets.cast,
                storyboard_prompt: state.presets.storyboard
              }
            }
          });
        if (cData.status !== "success") {
          throw new Error(cData.detail || "剧本编译失败");
        }

        state.compiledVoiceover = cData.data.compiled_voiceover;
        state.extractedEntities = cData.data.extracted_entities;

        p1Bar.style.width = "100%";
        p1Val.innerText = "100%";
        document.getElementById("p1StatusDot").className = "w-2.5 h-2.5 rounded-full bg-emerald-500";
        document.getElementById("p1StatusText").className = "text-emerald-400";
        document.getElementById("p1StatusText").innerText = "1. 第三人称解说词文本已就绪！";
        
        document.getElementById("d1VoiceoverOutput").innerText = state.compiledVoiceover;

        // [第2步] 生成定妆卡片
        logText.innerText = "[第2步] 解说词已全部编译就绪！正在物理派生生图引擎绘制 3 大核心资产 (预计 20 秒)...";
        document.getElementById("p2StatusDot").className = "w-2.5 h-2.5 rounded-full bg-indigo-500 animate-ping";
        document.getElementById("p2StatusText").className = "text-slate-350";
        p2Bar.style.width = "20%";
        p2Val.innerText = "20%";

        // 定时改变生图日志
        let logSec = 0;
        const logTimer = setInterval(() => {
          logSec += 3;
          if (logSec === 3) logText.innerText = `[第2步] 正在由画画引擎全力绘制【${state.extractedEntities[0] || '角色'}】定妆三视图...`;
          else if (logSec === 9) logText.innerText = `[第2步] 正在绘制【${state.extractedEntities[1] || '场景'}】电影大场景立绘...`;
          else if (logSec === 15) logText.innerText = `[第2步] 正在绘制【${state.extractedEntities[2] || '道具'}】线索道具图...`;
          
          let curPercent = Math.min(85, 20 + logSec * 3);
          p2Bar.style.width = `${curPercent}%`;
          p2Val.innerText = `${curPercent}%`;
        }, 1500);

        const aData = await pywebview.api.generate_assets({
            entities: state.extractedEntities,
            global_style_prompt: state.presets.image,
            seed: state.seed
          });
        clearInterval(logTimer);
        if (aData.status !== "success") {
          throw new Error(aData.detail || "定妆照生图失败");
        }

        state.assets = aData.assets;

        // 渲染定妆照卡片
        state.assets.forEach((ast, idx) => {
          document.getElementById(`cardName${idx}`).innerText = ast.name;
          document.getElementById(`cardPrompt${idx}`).innerText = ast.prompt;
          document.getElementById(`cardImg${idx}`).innerHTML = `<img src="${ast.image_url}" class="w-full h-full object-cover group-hover:scale-105 transition duration-500" />`;
        });

        p2Bar.style.width = "100%";
        p2Val.innerText = "100%";
        document.getElementById("p2StatusDot").className = "w-2.5 h-2.5 rounded-full bg-emerald-500";
        document.getElementById("p2StatusText").className = "text-emerald-400";
        document.getElementById("p2StatusText").innerText = "2. 角色及美术场景定妆大画卡集已绘制成功！";
        
        logText.innerText = "🎉 恭喜！大纲编译及资产三视图绘制圆满通过，大卡片画廊已解锁！";
        document.getElementById("d1ResultArea").classList.remove("hidden");
        
        // 允许下一步
        const nBtn = document.getElementById("d1NextBtn");
        nBtn.disabled = false;
        nBtn.className = "px-8 py-3.5 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl shadow-lg transition-all text-xs tracking-wider uppercase";

      } catch(err) {
        handleApiError(err, () => handleC1Launch(text));
      }
    }

    // ── 🎭 D1.1 定妆细节精修逻辑 (支持新旧后悔药) ──
    let activeCardIndex = 0;
    let activeD1_1PreviewMode = "new";

    function openD1_1(index) {
      activeCardIndex = index;
      activeD1_1PreviewMode = "new";
      const ast = state.assets[index];
      
      document.getElementById("d1_1_Title").innerText = `定妆画资产细节深度精整 - [${ast.name}] (D1.1)`;
      document.getElementById("d1_1_PromptInput").value = ast.prompt;
      
      // 页签重置
      document.getElementById("previewTab-new").className = "px-2 py-1 bg-indigo-600 text-[10px] text-white rounded font-bold";
      document.getElementById("previewTab-old").className = "px-2 py-1 text-[10px] text-slate-400 hover:text-slate-200 rounded";

      // 画布
      document.getElementById("d1_1_PreviewArea").innerHTML = `<img id="d1_1_preview_img" src="${ast.image_url}" class="max-w-full max-h-[300px] object-contain rounded-lg shadow-xl" />`;
      
      // 后悔药机制备份
      if (!state.assetHistory[ast.id]) {
        state.assetHistory[ast.id] = {
          new_url: ast.image_url,
          old_url: ast.image_url
        };
      }

      document.getElementById("overlayD1_1").classList.remove("hidden");
    }

    function switchD1_1PreviewMode(mode) {
      activeD1_1PreviewMode = mode;
      const ast = state.assets[activeCardIndex];
      const hist = state.assetHistory[ast.id];
      
      const tabNew = document.getElementById("previewTab-new");
      const tabOld = document.getElementById("previewTab-old");
      const img = document.getElementById("d1_1_preview_img");

      if (mode === "new") {
        tabNew.className = "px-2 py-1 bg-indigo-600 text-[10px] text-white rounded font-bold";
        tabOld.className = "px-2 py-1 text-[10px] text-slate-400 hover:text-slate-200 rounded";
        img.src = hist.new_url;
      } else {
        tabOld.className = "px-2 py-1 bg-indigo-600 text-[10px] text-white rounded font-bold";
        tabNew.className = "px-2 py-1 text-[10px] text-slate-400 hover:text-slate-200 rounded";
        img.src = hist.old_url;
      }
    }

    async function rebuildAssetCard() {
      const ast = state.assets[activeCardIndex];
      const newPrompt = document.getElementById("d1_1_PromptInput").value;
      
      const rebuildBtn = document.getElementById("rebuildAssetBtn");
      rebuildBtn.disabled = true;
      rebuildBtn.innerText = "🎨 生图引擎重绘中...";

      try {
        const res = await pywebview.api.render_single_frame({
            target_id: ast.id,
            prompt: newPrompt,
            seed: state.seed,
            style_lock: true
          });
        if (res.status === "success") {
          // 更新后悔药
          state.assetHistory[ast.id].old_url = ast.image_url;
          state.assetHistory[ast.id].new_url = res.render_url;
          
          ast.image_url = res.render_url;
          ast.prompt = newPrompt;
          
          // 更新前端卡片
          document.getElementById(`cardPrompt${activeCardIndex}`).innerText = newPrompt;
          document.getElementById(`cardImg${activeCardIndex}`).innerHTML = `<img src="${res.render_url}" class="w-full h-full object-cover group-hover:scale-105 transition duration-500" />`;
          
          // 更新弹窗图
          switchD1_1PreviewMode("new");
          showToast("✨ 定妆卡片局部重绘成功！");
        } else {
          showCustomModal("⚠️ 生图失败", "重绘失败，请重试！");
        }
      } catch(err) {
        handleApiError(err, rebuildAssetCard);
      } finally {
        rebuildBtn.disabled = false;
        rebuildBtn.innerText = "💡 确定更新并进行局部重画";
      }
    }

    function closeD1_1(event) {
      if (event.target.id === "overlayD1_1") {
        closeD1_1_Force();
      }
    }
    function closeD1_1_Force() {
      document.getElementById("overlayD1_1").classList.add("hidden");
    }

    // ── 🎬 E 页面分镜底片生成 ──
    async function handleD1Next() {
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
      }
    }

    // ── 🎞️ E1 分镜单帧细节重画 (支持新旧后悔药) ──
    let activeFrameIndex = 0;
    let activeE1PreviewMode = "new";

    function openE1(index) {
      activeFrameIndex = index;
      activeE1PreviewMode = "new";
      const frm = state.storyboards[index];
      
      document.getElementById("e1_Title").innerText = `分镜单帧大底片重绘 - [分镜帧 F-0${index+1}] (E1)`;
      document.getElementById("e1_PromptInput").value = frm.prompt;
      
      // 页签重置
      document.getElementById("previewTabE1-new").className = "px-2 py-1 bg-indigo-600 text-[10px] text-white rounded font-bold";
      document.getElementById("previewTabE1-old").className = "px-2 py-1 text-[10px] text-slate-400 hover:text-slate-200 rounded";

      // 画布
      document.getElementById("e1_PreviewArea").innerHTML = `<img id="e1_preview_img" src="${frm.image_url}" class="max-w-full max-h-[300px] object-contain rounded-lg shadow-xl" />`;
      
      // 后悔药备份
      const frame_id = `frame_0${index+1}`;
      if (!state.frameHistory[frame_id]) {
        state.frameHistory[frame_id] = {
          new_url: frm.image_url,
          old_url: frm.image_url
        };
      }

      document.getElementById("overlayE1").classList.remove("hidden");
    }

    function switchE1PreviewMode(mode) {
      activeE1PreviewMode = mode;
      const frm = state.storyboards[activeFrameIndex];
      const frame_id = `frame_0${activeFrameIndex+1}`;
      const hist = state.frameHistory[frame_id];
      
      const tabNew = document.getElementById("previewTabE1-new");
      const tabOld = document.getElementById("previewTabE1-old");
      const img = document.getElementById("e1_preview_img");

      if (mode === "new") {
        tabNew.className = "px-2 py-1 bg-indigo-600 text-[10px] text-white rounded font-bold";
        tabOld.className = "px-2 py-1 text-[10px] text-slate-400 hover:text-slate-200 rounded";
        img.src = hist.new_url;
      } else {
        tabOld.className = "px-2 py-1 bg-indigo-600 text-[10px] text-white rounded font-bold";
        tabNew.className = "px-2 py-1 text-[10px] text-slate-400 hover:text-slate-200 rounded";
        img.src = hist.old_url;
      }
    }

    async function rebuildFrameCard() {
      const frm = state.storyboards[activeFrameIndex];
      const newPrompt = document.getElementById("e1_PromptInput").value;
      const frame_id = `frame_0${activeFrameIndex+1}`;

      const rebuildBtn = document.getElementById("rebuildFrameBtn");
      rebuildBtn.disabled = true;
      rebuildBtn.innerText = "🎨 生图引擎单帧重绘中...";

      try {
        const res = await pywebview.api.render_single_frame({
            target_id: frame_id,
            prompt: newPrompt,
            seed: state.seed,
            style_lock: true
          });
        if (res.status === "success") {
          // 更新后悔药
          state.frameHistory[frame_id].old_url = frm.image_url;
          state.frameHistory[frame_id].new_url = res.render_url;
          
          frm.image_url = res.render_url;
          frm.prompt = newPrompt;
          
          // 更新前端底片网格
          document.getElementById(`framePreviewImg${activeFrameIndex}`).innerHTML = `
            <span class="absolute top-2 left-2 px-1.5 py-0.5 bg-black/80 text-[8px] font-bold rounded text-amber-500 font-mono">F-0${activeFrameIndex+1}</span>
            <img src="${res.render_url}" class="w-full h-full object-cover group-hover:scale-105 transition duration-500" />
          `;
          
          // 更新弹窗图
          switchE1PreviewMode("new");
          showToast("✨ 分镜单帧重画渲染完成！");
        } else {
          showCustomModal("⚠️ 生图失败", "重绘单帧失败，请重试！");
        }
      } catch(err) {
        handleApiError(err, rebuildFrameCard);
      } finally {
        rebuildBtn.disabled = false;
        rebuildBtn.innerText = "💡 确定更新并重新画本帧";
      }
    }

    function closeE1(event) {
      if (event.target.id === "overlayE1") {
        closeE1_Force();
      }
    }
    function closeE1_Force() {
      document.getElementById("overlayE1").classList.add("hidden");
    }

    // ── 🎥 F 页面全盘多轨物理装配 ──
    async function handleSynthesize() {
      navigateTo("F");
      
      const vPlayer = document.getElementById("epicVideoPlayer");
      const vPlaceholder = document.getElementById("videoPlaceholder");
      
      vPlayer.classList.add("hidden");
      vPlaceholder.classList.remove("hidden");

      try {
        const res = await pywebview.api.synthesize_video();
        if (res.status === "success") {
          state.relativeVideoPath = res.relative_path;
          
          vPlaceholder.classList.add("hidden");
          vPlayer.src = res.video_url;
          vPlayer.classList.remove("hidden");
          vPlayer.play();
          
          showToast("🎉 全盘多轨视频物理拼装合成大获成功！请导演欣赏大作！");
        } else {
          showCustomModal("⚠️ 合成失败", "FFmpeg 合成大师运行发生阻碍，请重试！");
        }
      } catch(err) {
        handleApiError(err, handleSynthesize);
      }
    }

    // ── 💾 另存为原生系统对话框下载 ──
    async function downloadEpicVideo() {
      if (!state.relativeVideoPath) {
        showToast("⚠️ 未找到已生成的视频源，请先完成物理合成！");
        return;
      }

      // 检测 pywebview 原生 JS 桥梁是否就绪
      if (typeof pywebview !== "undefined" && pywebview.api) {
        try {
          const defaultFilename = `director_cut_${state.modePath.toLowerCase()}_${Date.now()}.mp4`;
          
          // 1. 调用 Python 原生 Save File Dialog 对话框，获得用户选择的保存物理路径
          const savePath = await pywebview.api.select_save_path(defaultFilename);
          
          if (!savePath) {
            showToast("⏮️ 已取消保存另存为。");
            return;
          }

          showToast("💾 正在为您将视频文件拷贝拷贝至指定位置...");

          // 2. 将此物理绝对路径发送给 API 中控进行安全复制
          const res = await pywebview.api.download_video({
              source_file_relative_path: state.relativeVideoPath,
              target_absolute_path: savePath
            });
          if (res.status === "success") {
            showCustomModal("🎉 保存成功！", `大导演，您的电影大作已成功下载并导出至：\n\n${savePath}`);
          } else {
            showCustomModal("⚠️ 保存失败", res.detail || "文件拷贝失败，请核对写入权限后重试！");
          }
        } catch(e) {
          showCustomModal("⚠️ 对话框异常", "桌面系统接口交互异常，请重试！");
        }
      } else {
        // 兜底（浏览器调试模式，无 pywebview 环境）
        showToast("⚠️ 请通过 启动调色板.bat 打开桌面 App 使用完整下载功能。");
      }
    }

    // ── 🩺 容灾报错与重试拦截机制 ──
    function handleApiError(err, retryCallback) {
      console.error("[Bridge ERROR]:", err);
      
      // 抛出异常时，前端本地状态（输入文本、调好的 presets 参数等）绝对保留！
      // 弹出一个高质感对话框，提供“一键无缝重试”
      showCustomModal(
        "⚠️ 后台处理发生异常",
        `后台脚本执行中出现错误：${err && err.message ? err.message : '未知异常'}。请点击下方按钮重新发起请求（当前输入内容已全部保留）。`,
        "💡 立即重新发起请求",
        true, // 显示取消按钮，留存状态
        retryCallback
      );
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
              cast_prompt: state.presets.cast,
              storyboard_prompt: state.presets.storyboard
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
    }
  