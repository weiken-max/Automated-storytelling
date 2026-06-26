// ── 🎨 全局状态定义 ──
const state = {
  appState: "SCREEN_A",
  activeChannelId: "ch_drama",
  modePath: "CH_DRAMA",
  polishEnabled: false,
  defaultDownloadFolder: localStorage.getItem("palette_default_download_folder") || "",

  // 频道列表（动态，持久化到 localStorage）
  channels: loadChannelsFromStorage(),

  // 当前激活频道的提示词（激活频道时深拷贝注入）
  presets: {
    image: "High-quality 2D vector cartoon, bold black outlines, vibrant flat colors with soft cel-shading. Style inspired by Cyanide and Happiness but with professional lighting and detailed illustrated backgrounds. Character proportions: stick figure limbs, round bean heads.",
    polish: "你是一位专业的资深编剧与剧本医生。\n任务：请阅读用户提供的原始素材（梗概、片段或小说节选均可），在【完全保留用户原始创意、情节走向和核心设定】的前提下，进行专业润色，并补充与盲盒梗概同规格的结构化字段。\n\n润色要求：\n1. 语言风格：使文字更具画面感（Visual Thinking），多用具象动词，少用空泛形容词；**禁止**强行套用「阶层跃迁」「利益算计」等固定套路，除非用户原文已包含类似内核。\n2. 节奏与体量：优化起承转合与悬念，整体梗概总长度须符合后续约 1700 字旁白体量的信息密度，且 synopsis 与 synopsis_acts 拼接总字符数不得超过 1500（汉字+标点）。\n3. 分幕结构：必须输出 synopsis_acts 数组，长度恰好为 6；每幕为连续叙事，幕内不要写「第X幕」小标题，按时间顺序串成一条故事线。\n4. **行业潜规则 industry_rules**：与盲盒大纲一致，输出 1～4 条数组，概括本作可被影像化的矛盾机制或环境张力（非教条）。\n\n输出：**仅** JSON（键名固定）：\n{\n  \"synopsis_acts\": [共6个字符串，依次为第1幕…第6幕],\n  \"synopsis\": \"将 synopsis_acts 用两个换行符拼接的全文，与各幕一致\",\n  \"short_title\": \"12字以内的短片标题，用于飞书卡片抬头\",\n  \"era\": \"时代背景\",\n  \"identity\": \"主角身份或称谓\",\n  \"industry_rules\": [\"……\"]\n}",
    voiceover: "你是一个极其冷峻、犀利的短视频旁白文案大师。\n任务：按用户指示写出**一段**沉浸式旁白（不是全文，只是连续叙事中的一段）。\n\n【写作铁律】\n1. **一镜到底**：禁止使用段落小标题（如 Level、第一阶段）。用时间流逝、场景升级、数字与利益推进。\n2. **第二人称**：全程使用「你」，极简冷峻，少用形容词。\n3. **纯净文本**：禁止 <subshot>、禁止 [CUT]、禁止任何分镜标签。\n4. **本段体量**：本段目标约 {seg_target} 字（允许 ±10%）。\n\n输出要求：**只输出旁白正文**，不要标题、不要 JSON、不要代码围栏、不要解释。",
    outline: "你是一个极其冷酷的现实主义编剧与行业规则解剖师。\n任务：根据用户给出的主题，设计一个充满【利益算计】、【阶层跃迁】与【人性异化】的第二人称人生副本梗概。\n\n要求：\n1. **隐性阶层结构**：故事在底层逻辑上必须包含清晰的跃迁轨迹（入局 -> 进阶 -> 掌权 -> 巅峰与反噬），但绝不使用任何等级或Level标签。\n2. **核心科普（潜规则拆解）**：将该行业的核心运作机制、灰产逻辑或权力分配规则，作为主角晋升的关键武器。不要枯燥说教，要通过主角的“具体决定” and “利益交换”来展现。\n3. **数字与代价**：故事推进必须伴随具体的数字（金钱、份额、时间）以及主角为了权力所抛弃的底线。\n4. **结局闭环**：巅峰时刻必须伴随绝对的冷酷与孤独，主角最终要彻底沦为庞大系统的“宿命囚徒”或面临命运的黑色幽默式反噬。\n5. **分幕结构（硬性）**：必须输出 synopsis_acts 数组，长度恰好为 6，每个元素对应一幕的连续叙事；幕内不要用「第X幕」等小标题；时间顺序从第 1 幕到最后一幕衔接成一条故事线。\n6. **总字数**：`synopsis` 与 `synopsis_acts` 拼接后的总字符数（汉字+标点）不得超过 1500，逻辑必须极其严密。\n\n请输出 JSON 格式（键名固定）：\n{\n  \"synopsis_acts\": [共6个字符串，依次为第1幕…第6幕梗概正文],\n  \"synopsis\": \"将 synopsis_acts 用两个换行符拼接成的全文，必须与各幕内容完全一致\",\n  \"era\": \"时代背景\",\n  \"identity\": \"主角的终极身份\",\n  \"industry_rules\": [\"（揭露的1-2个行业深层潜规则）\"]\n}",
    storyboard: "【画风锚点】\nCyanide and Happiness comic style, 2D vector / flat graphic cartoon, bold black outlines, vivid flat color fills, pure 2D, no photoreal skin texture, no 3D/CGI. 允许卡通级光向（key direction, warm/cool, simple hard-edge shadow shapes），禁止电影级体积光与写实 subsurface skin。\n\n【分镜表现规则】\n★ 动态表情与肢体（核心要求：打破参考图的呆滞感！）：必须深度解析当前分镜的故事情节，强制赋予角色强烈且符合情境的情绪反应。\n1. 必须采用【核心情绪词 + 氰化物式五官拆解】组合。例如不要只写 mouth line，必须写：terrified expression, sharply angled frowning eyebrows, wide dilated dot eyes, screaming jagged mouth shape.\n2. 明确指令：绝不允许角色保持中立或被参考图的默认表情带偏（DO NOT copy the neutral expression from reference）。\n3. 肢体辅助：情绪必须配合夸张的肢体动作（如 recoiling in horror, pointing aggressively, slumping in defeat）。\n4. 脸部特写：当情绪是当前帧重点时，明确写明 close-up on explicit facial expression。"
  },

  // 后台返回的真实编译结果
  compiledVoiceover: "",
  lastCompiledText: "",
  extractedEntities: [],
  assets: [],      // 定妆照卡片
  storyboards: [], // 分镜帧底片
  storyboardGrids: [], // 16 宫格大图批次
  selectedFrameIndexByBatch: {}, // 记录各个 batch_index 选中的 frameIndex
  gridMode: "4x4", // 记录当前项目的 gridMode
  relativeVideoPath: "", // 合成视频在 Runs 下 the 相对路径
  
  // 后画后悔药对比备份
  assetHistory: {}, // {card_id: {new_url, old_url}}
  frameHistory: {}, // {frame_idx: {new_url, old_url}}
  tempCastPrompts: {}, // 临时缓存定妆提示词的各个分栏内容
  runningRedraws: {}, // 后台正在运行重绘的 card_id 或 frame_id 字典
};

function performSessionRecovery(res) {
  if (!res) return;
  showToast("🔄 正在从后台读取项目进度并全盘治愈状态树...");
  
  let targetStage = res.stage;
  if (targetStage === "C") targetStage = "C1";
  if (targetStage === "D") targetStage = "D1";
  
  // 1. 恢复基本变量与智能识别频道
  state.modePath = res.mode_path;
  state.seed = res.seed;
  state.extractedEntities = res.entities;
  state.polishEnabled = res.polish_enabled;
  state.gridMode = res.grid_mode || "4x4";

  // 智能匹配激活的频道 ID，并拉取专属提示词配置
  let recoveredChId = "ch_drama";
  if (res.run_id) {
    const runIdLower = res.run_id.toLowerCase();
    state.channels.forEach(ch => {
      const cleanId = ch.id.toLowerCase().replace("ch_", "");
      if (runIdLower.includes(ch.id.toLowerCase()) || 
          runIdLower.includes(cleanId) || 
          (cleanId.length >= 4 && runIdLower.includes(cleanId.substring(0, 4)))) {
        recoveredChId = ch.id;
      }
    });
  }
  state.activeChannelId = recoveredChId;
  const chObj = state.channels.find(c => c.id === recoveredChId);
  if (chObj) {
    state.presets = getChannelPresets(chObj);
    // 从频道 channelType 派生 modePath（保证定妆模式与频道类型一致）
    state.modePath = (chObj.channelType === "drama") ? "CH_DRAMA" : recoveredChId.toUpperCase();
  }
  
  // 同步顶部状态灯
  const stateBadge = document.getElementById("activeStateBadge");
  if (stateBadge) stateBadge.innerText = `STATUS: SCREEN_${targetStage}`;
  
  // 2. 恢复剧本大纲与编译文本
  if (res.synopsis) {
    state.rawScript = res.synopsis.synopsis || "";
    state.compiledVoiceover = res.synopsis.synopsis || "";
    state.lastCompiledText = res.synopsis.synopsis || "";
    
    const rawScriptEl = document.getElementById("rawScriptTextarea");
    if (rawScriptEl) {
      rawScriptEl.value = res.synopsis.synopsis || "";
    }
    
    const d1VoiceoverEl = document.getElementById("d1VoiceoverOutput");
    if (d1VoiceoverEl) {
      d1VoiceoverEl.innerText = res.synopsis.synopsis || "";
    }
  }
  
  // 3. 恢复定妆卡片，并在资产就绪时同步更新 D1 界面所有进度条与状态
  if (res.assets && res.assets.length > 0) {
    state.assets = res.assets;
    renderAssetCards();

    // 移出结果区域隐藏，百分比进度拉满 100%，点亮状态圆点，启用并高亮下一步按钮
    const d1ResArea = document.getElementById("d1ResultArea");
    if (d1ResArea) d1ResArea.classList.remove("hidden");
    
    const p1Bar = document.getElementById("p1Bar");
    const p1Val = document.getElementById("p1Val");
    const p2Bar = document.getElementById("p2Bar");
    const p2Val = document.getElementById("p2Val");
    const logText = document.getElementById("assistantLogText");
    
    if (p1Bar) p1Bar.style.width = "100%";
    if (p1Val) p1Val.innerText = "100%";
    const p1Dot = document.getElementById("p1StatusDot");
    if (p1Dot) p1Dot.className = "w-2.5 h-2.5 rounded-full bg-emerald-500";
    const p1Txt = document.getElementById("p1StatusText");
    if (p1Txt) {
      p1Txt.className = "text-emerald-400";
      p1Txt.innerText = "1. 第三人称解说词文本已就绪！";
    }
    
    if (p2Bar) p2Bar.style.width = "100%";
    if (p2Val) p2Val.innerText = "100%";
    const p2Dot = document.getElementById("p2StatusDot");
    if (p2Dot) p2Dot.className = "w-2.5 h-2.5 rounded-full bg-emerald-500";
    const p2Txt = document.getElementById("p2StatusText");
    if (p2Txt) {
      p2Txt.className = "text-emerald-400";
      p2Txt.innerText = "2. 角色及美术场景定妆大画卡集已绘制成功！";
    }
    
    if (logText) logText.innerText = "🎉 恭喜！已从上次断点完美读取大纲编译及资产三视图，大卡片画廊已解锁！";
    
    const nBtn = document.getElementById("d1NextBtn");
    if (nBtn) {
      nBtn.disabled = false;
      nBtn.className = "px-8 py-3.5 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl shadow-lg transition-all text-xs tracking-wider uppercase";
    }
  }
  
  // 4. 恢复分镜 (v4.0 16宫格模式)
  if (res.frames && res.frames.length > 0) {
    state.storyboards = res.frames;
  }
  if (res.grids && res.grids.length > 0) {
    state.storyboardGrids = res.grids;
    renderStoryboardGrids();
  }
  if (res.frames && res.frames.length > 0) {
    res.frames.forEach((frm, idx) => {
      const previewImg = document.getElementById(`framePreviewImg${idx}`);
      if (previewImg) {
        previewImg.innerHTML = `
          <span class="absolute top-2 left-2 px-1.5 py-0.5 bg-black/80 text-[8px] font-bold rounded text-amber-500 font-mono">F-0${idx+1}</span>
          ${frm.image_url ? `<img src="${frm.image_url}" class="w-full h-full object-cover group-hover:scale-105 transition duration-500" />` : `<div class="text-[10px] text-slate-700 animate-pulse">Rendering...</div>`}
        `;
      }
      const textPreview = document.getElementById(`frameTextPreview${idx}`);
      if (textPreview && frm.text) {
        textPreview.innerText = frm.text;
      }
      const timeEl = document.getElementById(`frameTime${idx}`);
      if (timeEl && frm.time_range) {
        timeEl.innerText = frm.time_range;
      }
    });
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
  
  navigateTo(targetStage);
  showToast(`🎉 成功为您自动恢复至 [${targetStage} 界面]！`);
}

// ── ✍️ D2 大纲意见反馈重写逻辑 ──
async function applyD2Feedback() {
  if (state.isRunning) {
    showToast("⏳ 任务正在全力运转中，请勿重复点击！");
    return;
  }
  
  const feedbackInput = document.getElementById("d2FeedbackInput");
  const feedback = feedbackInput ? feedbackInput.value.trim() : "";
  if (!feedback) {
    showToast("⚠️ 请先写入您的具体修改意见（例如：加一个猫咪助手）！");
    return;
  }
  
  state.isRunning = true;
  showToast("🧠 正在根据您的修改建议由编剧大模型重新雕琢大纲...");
  
  const btn = document.getElementById("applyFeedbackBtn");
  const oldHtml = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `
      <div class="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
      <span>重写大纲中...</span>
    `;
  }
  
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
          storyboard_prompt: state.presets.storyboard
        }
      }
    });
    
    if (res.status === "success") {
      state.rawScript = res.data.compiled_voiceover;
      const shkOut = document.getElementById("shakeOutlineContent");
      if (shkOut) shkOut.innerText = res.data.compiled_voiceover;
      if (feedbackInput) feedbackInput.value = "";
      showToast("🎉 大纲重写成功！大模型已完美吸纳您的意见！");
    } else {
      showCustomModal("⚠️ 后端排队中", "重写大纲失败，请重试！");
    }
  } catch(err) {
    handleApiError(err, applyD2Feedback);
  } finally {
    state.isRunning = false;
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = oldHtml;
    }
  }
}

// ── 📝 初始化启动逻辑 ──
function initApp() {
  // 1. 激活默认频道（注入提示词）
  const firstCh = state.channels[0];
  if (firstCh) {
    state.activeChannelId = firstCh.id;
    state.modePath = (firstCh.channelType === "drama") ? "CH_DRAMA" : firstCh.id.toUpperCase();
    state.presets = getChannelPresets(firstCh);
  }

  // 2. 渲染首页频道网格
  renderChannelGrid();

  // 3. 更新 JSON Payload 预览
  updateJsonPayloadViewer();
  updatePresetBtnText();

  console.log('[Palette V3] 频道工作站初始化完成，共', state.channels.length, '个频道。');
}

// 双保险：DOMContentLoaded + load 都触发一次
document.addEventListener("DOMContentLoaded", initApp);
window.addEventListener("load", initApp);
setTimeout(initApp, 200);

function syncRawScriptToState() {
  const ta = document.getElementById("rawScriptTextarea");
  const text = ta ? ta.value : "";
  state.rawScript = text;
  saveChannelDraft(text);
  updateJsonPayloadViewer();
}

function insertEmotionTag() {
  const ta = document.getElementById("rawScriptTextarea");
  if (!ta) return;

  const start = ta.selectionStart;
  const end = ta.selectionEnd;
  const val = ta.value;
  const selectedText = val.substring(start, end);

  const prefix = "<cot text=";
  const placeholder = "情绪";
  const suffix = ">" + selectedText + "</cot>";

  const replacement = prefix + placeholder + suffix;
  ta.value = val.substring(0, start) + replacement + val.substring(end);

  // 同步状态与草稿存储
  syncRawScriptToState();

  // 重新聚焦并选定“情绪”占位符
  ta.focus();
  const selectStart = start + prefix.length;
  const selectEnd = selectStart + placeholder.length;
  ta.setSelectionRange(selectStart, selectEnd);
}

// C2 提示词编辑：修改后同步到激活频道的 presets
function syncPromptToState(cat) {
  const el = document.getElementById(`promptText-${cat}`);
  const text = el ? el.value : "";
  state.presets[cat] = text;
  // 写回激活频道的自定义 presets
  const ch = getActiveChannel();
  if (ch) {
    if (!ch.presets) ch.presets = { ...DEFAULT_PRESETS };
    ch.presets[cat] = text;
    saveChannelsToStorage();
  }
  updateJsonPayloadViewer();
}

// C2 进入时：把激活频道的提示词装载到编辑器
function loadPresetsIntoC2() {
  const presets = state.presets;
  const img = document.getElementById("promptText-image");
  const pol = document.getElementById("promptText-polish");
  const voi = document.getElementById("promptText-voiceover");
  const out = document.getElementById("promptText-outline");
  const stb = document.getElementById("promptText-storyboard");
  const cas = document.getElementById("promptText-cast_prompt");
  if (img) img.value = presets.image || DEFAULT_PRESETS.image;
  if (pol) pol.value = presets.polish || DEFAULT_PRESETS.polish;
  if (voi) voi.value = presets.voiceover || DEFAULT_PRESETS.voiceover;
  if (out) out.value = presets.outline || DEFAULT_PRESETS.outline;
  if (stb) stb.value = presets.storyboard || DEFAULT_PRESETS.storyboard;
  if (cas) cas.value = presets.cast_prompt || DEFAULT_PRESETS.cast_prompt;
  updateJsonPayloadViewer();
}

// ── 🛠️ 弹窗与吐司通知 ──
function showToast(text, duration = 3000) {
  const toast = document.getElementById("toastNotification");
  const toastText = document.getElementById("toastText");
  if (toastText) toastText.innerText = text;
  if (toast) {
    toast.classList.remove("hidden");
    setTimeout(() => toast.classList.add("hidden"), duration);
  }
}

function showCustomModal(title, desc, primaryText = "我知道了", showCancel = false, primaryCallback = null) {
  const mTitle = document.getElementById("modalTitle");
  const mDesc = document.getElementById("modalDesc");
  if (mTitle) mTitle.innerText = title;
  if (mDesc) mDesc.innerText = desc;
  
  const pBtn = document.getElementById("modalPrimaryBtn");
  if (pBtn) {
    pBtn.innerText = primaryText;
    pBtn.onclick = () => {
      closeCustomModal();
      if (primaryCallback) primaryCallback();
    };
  }

  const sBtn = document.getElementById("modalSecBtn");
  if (sBtn) {
    if (showCancel) {
      sBtn.classList.remove("hidden");
    } else {
      sBtn.classList.add("hidden");
    }
  }

  const modal = document.getElementById("customModal");
  if (modal) modal.classList.remove("hidden");
}

function closeCustomModal() {
  const modal = document.getElementById("customModal");
  if (modal) modal.classList.add("hidden");
}

// ── 🔄 页面导航状态机 ──
function navigateTo(targetState) {
  const screens = ["screenA", "screenB", "screenC1", "screenC2", "screenD1", "screenD2", "screenE", "screenF"];
  screens.forEach(s => {
    const el = document.getElementById(s);
    if (el) el.classList.add("hidden");
  });
  
  const targetScreen = document.getElementById(`screen${targetState}`);
  if (targetScreen) targetScreen.classList.remove("hidden");
  state.appState = `SCREEN_${targetState}`;
  
  const stateBadge = document.getElementById("activeStateBadge");
  if (stateBadge) stateBadge.innerText = `STATUS: SCREEN_${targetState}`;
  
  // 进入 C1 时：根据激活频道颜色更新 indicator
  if (targetState === "C1") {
    const ch = getActiveChannel();
    const indicator = document.getElementById("c1ModeIndicator");
    if (ch && indicator) {
      indicator.style.backgroundColor = ch.color;
      indicator.style.boxShadow = `0 0 8px ${ch.color}80`;
      indicator.className = "w-3 h-3 rounded-full";
    }
    // 加载该频道的草稿
    loadChannelDraft();
    // 初始化 TTS 引擎选择和参数
    initTtsSettingsFromState();
    // 更新 C1 顶部「⚙️ 当前频道提示词」按钮文字
    const promptBtnLabel = document.getElementById("c1PromptBtnLabel");
    if (promptBtnLabel && ch) promptBtnLabel.innerText = `${ch.emoji || ''} ${ch.name} 提示词`;
    // C2 频道名更新
    const c2Name = document.getElementById("c2ChannelName");
    if (c2Name && ch) c2Name.innerText = ch.name;
  }

  // 进入 C2 时：把当前频道的提示词载入编辑器
  if (targetState === "C2") {
    loadPresetsIntoC2();
  }

  // 进入 A 时：重新渲染频道网格
  if (targetState === "A") {
    renderChannelGrid();
  }
}

// ── 🎨 频道首页网格渲染 ──
function renderChannelGrid() {
  const grid = document.getElementById("channelGrid");
  if (!grid) return;

  // 限制：最多 8 个
  const addBtn = document.getElementById("addChannelBtn");
  if (addBtn) addBtn.style.display = state.channels.length >= 8 ? "none" : "";

  if (!state.channels || state.channels.length === 0) {
    grid.innerHTML = '<div class="col-span-3 text-center text-slate-600 text-xs py-10">暂无频道，请点击下方按钮新增</div>';
    return;
  }

  grid.innerHTML = state.channels.map(ch => {
    const borderColor = ch.color;
    const glowShadow = `0 12px 30px ${ch.color}44`;
    return `
      <div onclick="activateChannel('${ch.id}', event)"
        class="ch-card group relative rounded-2xl p-5 cursor-pointer flex flex-col space-y-3"
        style="background:#0D1227; border:1px solid #1e293b; transition:all 0.3s;"
        onmouseover="this.style.borderColor='${borderColor}'; this.style.transform='translateY(-4px)'; this.style.boxShadow='${glowShadow}';"
        onmouseout="this.style.borderColor='#1e293b'; this.style.transform=''; this.style.boxShadow='';"
      >
        <!-- 顶部发光线 -->
        <div class="absolute top-0 inset-x-0 h-[2px] rounded-t-2xl"
          style="background:linear-gradient(to right, transparent, ${borderColor}, transparent); opacity:0; transition:opacity 0.3s;"
          onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0'"></div>

        <!-- Emoji + 编辑按钮 -->
        <div style="display:flex; align-items:flex-start; justify-content:space-between;">
          <span style="font-size:1.875rem; line-height:1;">${ch.emoji || '🎬'}</span>
          <button onclick="event.stopPropagation(); openChannelEditor('${ch.id}')"
            style="opacity:0; padding:6px; border-radius:8px; background:#0f172a; border:none; color:#94a3b8; font-size:0.75rem; cursor:pointer; transition:opacity 0.2s;"
            onmouseover="this.style.opacity='1'; this.style.background='#1e293b'; this.style.color='#e2e8f0';"
            onmouseout="this.style.opacity='0';"
            class="edit-btn">✏️</button>
        </div>

        <!-- 频道名 -->
        <div>
          <p style="font-size:0.875rem; font-weight:700; color:#f1f5f9; letter-spacing:0.05em; margin:0 0 4px;">${ch.name}</p>
          <div style="display:flex; align-items:center; gap:6px;">
            <span style="width:6px; height:6px; border-radius:50%; background:${ch.color}; display:inline-block;"></span>
            <span style="font-size:10px; color:#64748b; font-family:monospace;">${ch.locked ? '🔒 原厂频道' : '🎨 自定义频道'}</span>
          </div>
        </div>

        <!-- 进入提示 -->
        <div style="padding-top:8px; border-top:1px solid rgba(30,41,59,0.6); display:flex; justify-content:space-between; align-items:center; font-size:10px; color:#475569;">
          <span>点击进入导演空间</span>
          <span style="font-weight:700; color:${ch.color};">›</span>
        </div>
      </div>
    `;
  }).join("");

  grid.querySelectorAll('.ch-card').forEach(card => {
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
  state.modePath = (ch.channelType === "drama") ? "CH_DRAMA" : channelId.toUpperCase();
  state.presets = getChannelPresets(ch);

  // 转场特效
  if (event) {
    const splash = document.getElementById("splashCircle");
    if (splash) {
      splash.style.left = `${event.clientX}px`;
      splash.style.top = `${event.clientY}px`;
      splash.style.backgroundColor = ch.color;
      splash.classList.add("active");
    }
    setTimeout(() => {
      navigateTo("C1");
      if (splash) splash.classList.remove("active");
    }, 900);
  } else {
    navigateTo("C1");
  }
}

function getActiveChannel() {
  return state.channels.find(c => c.id === state.activeChannelId) || state.channels[0];
}

function saveChannelDraft(text) {
  localStorage.setItem(`palette_draft_${state.activeChannelId}`, text);
}

function loadChannelDraft() {
  const draft = localStorage.getItem(`palette_draft_${state.activeChannelId}`) || "";
  const ta = document.getElementById("rawScriptTextarea");
  if (ta) { ta.value = draft; state.rawScript = draft; }
  updateJsonPayloadViewer();
}

// 解析 [标签] 内容为键值对
function parseCastPrompt(castPromptStr) {
  const result = {};
  if (!castPromptStr) return result;
  const regex = /\[([^\]]+)\]([\s\S]*?)(?=\[[^\]]+\]|$)/g;
  let match;
  while ((match = regex.exec(castPromptStr)) !== null) {
    result[match[1].trim()] = match[2].trim();
  }
  return result;
}

// 判断资产名称是否属于通用名称（机制 A：无中文，则判定为通用资产）
function isGenericLabel(label) {
  if (!label) return true;
  return !/[\u4e00-\u9fa5]/.test(label);
}

// 动态渲染多输入框 (融合机制 A 与 机制 B)
function renderCastPromptFields() {
  const container = document.getElementById("chEditorCastPromptContainer");
  if (!container) return;
  
  // 暂存用户当前正在输入的内容，防止输入时重绘丢失焦点/输入值
  const currentInputs = {};
  container.querySelectorAll("textarea").forEach(ta => {
    currentInputs[ta.dataset.label] = ta.value;
  });
  
  container.innerHTML = "";
  const channelType = document.querySelector('input[name="chChannelType"]:checked')?.value || "science";
  
  let fields = [];
  
  if (channelType === "science") {
    fields = [{ label: "scene", displayName: "🔬 科普底图模板 (scene)", type: "scene" }];
  } else if (channelType === "drama") {
    fields = [
      { label: "character", displayName: "👤 角色定妆模板 (character)", type: "character" },
      { label: "scene", displayName: "🌅 场景定妆模板 (scene)", type: "scene" },
      { label: "prop", displayName: "🎒 道具定妆模板 (prop)", type: "prop" }
    ];
  } else { // 自定义模式
    const rows = document.querySelectorAll("#customAssetsList > div");
    const genericTypesToShow = new Set();
    const specificLabelsToShow = [];
    
    rows.forEach((row, idx) => {
      const input = row.querySelector("input");
      const select = row.querySelector("select");
      if (!input || !select) return;
      const l = input.value.trim() || `未命名卡片_${idx+1}`;
      const type = select.value;
      const customImagePath = row.dataset.customImagePath || "";
      
      if (isGenericLabel(l)) {
        // 机制 A：通用资产（如 1, 2, A, B 等）
        genericTypesToShow.add(type);
      } else {
        // 机制 B：专属中文资产（如 玩家, 老板 等）
        specificLabelsToShow.push({ label: l, type: type, customImagePath: customImagePath });
      }
    });
    
    // 1. 渲染通用输入框 (Mechanism A)
    if (genericTypesToShow.has("character")) {
      fields.push({ label: "character", displayName: "👤 通用角色定妆模板 (character)", type: "character" });
    }
    if (genericTypesToShow.has("scene")) {
      fields.push({ label: "scene", displayName: "🌅 通用场景定妆模板 (scene)", type: "scene" });
    }
    if (genericTypesToShow.has("prop")) {
      fields.push({ label: "prop", displayName: "🎒 通用道具定妆模板 (prop)", type: "prop" });
    }
    
    // 2. 渲染专属的中文输入框 (Mechanism B)
    specificLabelsToShow.forEach(item => {
      const typeEmoji = item.type === "character" ? "👤" : (item.type === "scene" ? "🌅" : "🎒");
      fields.push({
        label: item.label,
        displayName: `${typeEmoji} 专属 [${item.label}] 定妆模板 (${item.type})`,
        type: item.type,
        customImagePath: item.customImagePath
      });
    });
  }
  
  // 默认兜底提示词描述
  const defaultDesc = {
    character: "A tactical military character design sheet, orthographic view, depicting a modern operator representing {entity}. Wearing tactical military gear: a low-profile helmet with headset, tactical plate carrier vest, cargo pants in olive drab or khaki tan, clean 2D vector style with smooth flat colors, bold outlines, and a professional concept art aesthetic, pure white background #FFFFFF.",
    scene: "A tactical military command center or surveillance room interior depicting {entity}. Clean 2D flat painting style, wide angle, high-tech monitors glowing with greenish tactical map HUD overlays, realist tactical military color palette, no characters.",
    prop: "A 2D flat vector icon of a high-tech tactical object representing {entity}. A military-grade gadget, tactical tablet, or class badge, clean lines, olive drab and steel gray colors, pure white background #FFFFFF."
  };
  
  fields.forEach(f => {
    // 提取策略：优先提取用户当前在页面上打字的值，其次提取之前从 LocalStorage 中加载的值，最后用默认值兜底
    const val = currentInputs[f.label] !== undefined 
      ? currentInputs[f.label] 
      : (state.tempCastPrompts[f.label] || defaultDesc[f.type] || "");
      
    // 同步到 state 临时缓存，以防止由于重新渲染导致的丢失
    state.tempCastPrompts[f.label] = val;
      
    let uploadUI = "";
    if (f.customImagePath) {
      uploadUI = `
        <div class="flex items-center gap-3 bg-[#0A0D1B] border border-indigo-950/40 rounded-xl p-2.5 mt-1.5 animate-fade-in">
          <img src="${f.customImagePath}" class="w-12 h-12 rounded-lg object-cover border border-slate-800/80 shadow-md" />
          <div class="flex flex-col gap-1.5 flex-1 min-w-0">
            <span class="text-[10px] text-slate-400 font-mono truncate max-w-[220px]">${f.customImagePath}</span>
            <div class="flex items-center gap-2">
              <button type="button" onclick="autoDescribeAssetImage('${escapeHtml(f.label)}', '${f.type}', '${escapeHtml(f.customImagePath)}', this)" class="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 text-slate-100 rounded-lg text-[9px] font-bold flex items-center gap-1 transition-all cursor-pointer whitespace-nowrap">
                🤖 智能识别 (Gemini Pro)
              </button>
            </div>
          </div>
        </div>
      `;
    }

    const div = document.createElement("div");
    div.className = "space-y-1 animate-fade-in";
    div.innerHTML = `
      <div class="flex justify-between items-center">
        <span class="text-[10px] font-bold text-slate-400">${f.displayName}</span>
      </div>
      <textarea data-label="${f.label}" rows="3" 
        class="w-full bg-[#05070E] border border-slate-800 rounded-xl p-3.5 text-xs font-mono text-slate-200 focus:border-indigo-500 focus:outline-none leading-relaxed"
        oninput="state.tempCastPrompts['${f.label}'] = this.value"
      >${val}</textarea>
      ${uploadUI}
    `;
    container.appendChild(div);
  });
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
  const rollbackBtn = document.getElementById("chEditorRollbackBtn");
  if (!modal) return;

  // 渲染颜色选择器
  const palette = document.getElementById("chColorPalette");
  let selectedColor = channelId
    ? (state.channels.find(c => c.id === channelId)?.color || CHANNEL_COLORS[0])
    : CHANNEL_COLORS[3];
  if (palette) {
    palette.innerHTML = CHANNEL_COLORS.map(clr => `
      <button type="button" onclick="selectEditorColor('${clr}')" id="colorDot_${clr.replace('#','')}"
        class="w-8 h-8 rounded-full border-2 transition-all cursor-pointer hover:scale-110"
        style="background:${clr}; border-color: ${clr === selectedColor ? 'white' : 'transparent'}"></button>
    `).join("");
  }
  const colorInput = document.getElementById("chEditorColor");
  if (colorInput) colorInput.value = selectedColor;

  if (channelId) {
    const ch = state.channels.find(c => c.id === channelId);
    if (!ch) return;
    const editorTitle = document.getElementById("chEditorTitle");
    const editorEmoji = document.getElementById("chEditorEmoji");
    const editorEmojiInput = document.getElementById("chEditorEmojiInput");
    const editorName = document.getElementById("chEditorName");
    const editorOutline = document.getElementById("chEditorOutline");
    const editorImage = document.getElementById("chEditorImage");
    const editorVoiceover = document.getElementById("chEditorVoiceover");
    const editorPolish = document.getElementById("chEditorPolish");
    const editorStoryboard = document.getElementById("chEditorStoryboard");

    if (editorTitle) editorTitle.innerText = `编辑频道：${ch.name}`;
    if (editorEmoji) editorEmoji.innerText = ch.emoji || '🎬';
    if (editorEmojiInput) editorEmojiInput.value = ch.emoji || '';
    if (editorName) editorName.value = ch.name;
    const presets = getChannelPresets(ch);
    if (editorOutline) editorOutline.value   = ch.presets?.outline   || presets.outline || '';
    if (editorImage) editorImage.value     = ch.presets?.image     || '';
    if (editorVoiceover) editorVoiceover.value = ch.presets?.voiceover || '';
    if (editorPolish) editorPolish.value    = ch.presets?.polish    || '';
    if (editorStoryboard) editorStoryboard.value = ch.presets?.storyboard || '';

    // 解析已有的定妆提示词合并包
    state.tempCastPrompts = parseCastPrompt(ch.presets?.cast_prompt || presets.cast_prompt || '');

    const chType = ch.channelType || "science";
    document.querySelectorAll('input[name="chChannelType"]').forEach(r => {
      r.checked = (r.value === chType);
      r.disabled = !!ch.locked;
    });
    const typeRow = document.getElementById("chTypeRow");
    if (typeRow) typeRow.style.opacity = ch.locked ? "0.55" : "1";
    
    const assetsList = document.getElementById("customAssetsList");
    if (assetsList) assetsList.innerHTML = "";
    if (chType === "custom" && ch.assets_config) {
      ch.assets_config.forEach(ast => {
        addCustomAssetRow(ast.label, ast.type, ast.custom_image_path || "");
      });
    }
    
    _syncChannelTypeStyle();
    if (deleteBtn) deleteBtn.classList.toggle("hidden", !!ch.locked);
    if (rollbackBtn) rollbackBtn.classList.toggle("hidden", !ch.presetsBackup);
  } else {
    const editorTitle = document.getElementById("chEditorTitle");
    const editorEmoji = document.getElementById("chEditorEmoji");
    const editorEmojiInput = document.getElementById("chEditorEmojiInput");
    const editorName = document.getElementById("chEditorName");
    const editorOutline = document.getElementById("chEditorOutline");
    const editorImage = document.getElementById("chEditorImage");
    const editorVoiceover = document.getElementById("chEditorVoiceover");
    const editorPolish = document.getElementById("chEditorPolish");
    const editorStoryboard = document.getElementById("chEditorStoryboard");

    if (editorTitle) editorTitle.innerText = "新增创作频道";
    if (editorEmoji) editorEmoji.innerText = "🎬";
    if (editorEmojiInput) editorEmojiInput.value = "";
    if (editorName) editorName.value = "";
    if (editorOutline) editorOutline.value = "";
    if (editorImage) editorImage.value = "";
    if (editorVoiceover) editorVoiceover.value = "";
    if (editorPolish) editorPolish.value = "";
    if (editorStoryboard) editorStoryboard.value = "";
    
    // 清空临时提示词缓存
    state.tempCastPrompts = {};
    
    const assetsList = document.getElementById("customAssetsList");
    if (assetsList) assetsList.innerHTML = "";

    document.querySelectorAll('input[name="chChannelType"]').forEach(r => {
      r.checked = (r.value === "science");
      r.disabled = false;
    });
    const typeRow = document.getElementById("chTypeRow");
    if (typeRow) typeRow.style.opacity = "1";
    _syncChannelTypeStyle();
    if (deleteBtn) deleteBtn.classList.add("hidden");
    if (rollbackBtn) rollbackBtn.classList.add("hidden");
  }

  modal.classList.remove("hidden");
}

function _syncChannelTypeStyle() {
  const val = document.querySelector('input[name="chChannelType"]:checked')?.value || "science";
  const sciEl = document.getElementById("chTypeLabelScience");
  const draEl = document.getElementById("chTypeLabelDrama");
  const custEl = document.getElementById("chTypeLabelCustom");
  if (sciEl) sciEl.style.borderColor = (val === "science") ? "#F59E0B" : "";
  if (draEl) draEl.style.borderColor = (val === "drama")   ? "#6366F1" : "";
  if (custEl) custEl.style.borderColor = (val === "custom") ? "#8B5CF6" : "";

  const customSection = document.getElementById("customAssetsConfigSection");
  if (customSection) {
    if (val === "custom") {
      customSection.classList.remove("hidden");
    } else {
      customSection.classList.add("hidden");
    }
  }
  renderCastPromptFields();
}

function selectEditorColor(clr) {
  const colorInput = document.getElementById("chEditorColor");
  if (colorInput) colorInput.value = clr;
  document.querySelectorAll("#chColorPalette button").forEach(btn => {
    const btnClr = btn.style.background;
    btn.style.borderColor = btnClr === clr ? 'white' : 'transparent';
  });
}

function closeChannelEditor() {
  const modal = document.getElementById("channelEditorModal");
  if (modal) modal.classList.add("hidden");
  _editingChannelId = null;
}

function saveChannelFromEditor() {
  const nameInput = document.getElementById("chEditorName");
  const name = nameInput ? nameInput.value.trim() : "";
  if (!name) { showToast("⚠️ 请填写频道名称！"); return; }
  if (state.channels.length >= 8 && !_editingChannelId) {
    showToast("⚠️ 最多创建 8 个频道！"); return;
  }

  const emojiInput = document.getElementById("chEditorEmojiInput");
  const emoji = emojiInput ? (emojiInput.value.trim() || "🎬") : "🎬";
  const colorInput = document.getElementById("chEditorColor");
  const color = colorInput ? (colorInput.value || "#6366F1") : "#6366F1";
  
  const chEditorOutline = document.getElementById("chEditorOutline");
  const chEditorImage = document.getElementById("chEditorImage");
  const chEditorVoiceover = document.getElementById("chEditorVoiceover");
  const chEditorPolish = document.getElementById("chEditorPolish");
  const chEditorStoryboard = document.getElementById("chEditorStoryboard");

  const outline = chEditorOutline ? chEditorOutline.value.trim() : "";
  const image = chEditorImage ? chEditorImage.value.trim() : "";
  const voiceover = chEditorVoiceover ? chEditorVoiceover.value.trim() : "";
  const polish = chEditorPolish ? chEditorPolish.value.trim() : "";
  const storyboard = chEditorStoryboard ? chEditorStoryboard.value.trim() : "";
  
  // 从动态分栏输入框中读取并拼装定妆照提示词
  const castPromptParts = [];
  const taList = document.querySelectorAll("#chEditorCastPromptContainer textarea");
  taList.forEach(ta => {
    const lbl = ta.dataset.label;
    const val = ta.value.trim();
    castPromptParts.push(`[${lbl}]\n${val}`);
  });
  const cast_prompt = castPromptParts.join("\n\n").trim();

  const hasCustomPresets = outline || image || voiceover || polish || storyboard || cast_prompt;
  const channelType = document.querySelector('input[name="chChannelType"]:checked')?.value || "science";

  let assets_config = null;
  if (channelType === "custom") {
    assets_config = [];
    const rows = document.querySelectorAll("#customAssetsList > div");
    if (rows.length === 0) {
      showToast("⚠️ 自定义资产模式下，必须配置至少 1 个卡片！");
      return;
    }
    for (const row of rows) {
      const input = row.querySelector("input");
      const select = row.querySelector("select");
      const l = input.value.trim();
      if (!l) {
        showToast("⚠️ 卡片名称不能为空！");
        return;
      }
      const customImagePath = row.dataset.customImagePath || "";
      assets_config.push({ label: l, type: select.value, custom_image_path: customImagePath });
    }
  }

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
        state.channels[idx].assets_config = assets_config;
        state.channels[idx].presets = hasCustomPresets ? { outline, image, voiceover, polish, storyboard, cast_prompt } : null;
      } else {
        state.channels[idx].presets = hasCustomPresets ? { outline, image, voiceover, polish, storyboard, cast_prompt } : null;
      }
    }
    showToast(`✅ 频道「${name}」已更新！`);
  } else {
    const newId = "ch_custom_" + Date.now();
    state.channels.push({ id: newId, channelType, name, emoji, color, locked: false,
      assets_config,
      presets: hasCustomPresets ? { outline, image, voiceover, polish, storyboard, cast_prompt } : null
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
    showToast("⚠️ 没有可用的备份版本！");
    return;
  }
  const bak = ch.presetsBackup;
  const oEl = document.getElementById("chEditorOutline");
  const iEl = document.getElementById("chEditorImage");
  const vEl = document.getElementById("chEditorVoiceover");
  const pEl = document.getElementById("chEditorPolish");
  const sEl = document.getElementById("chEditorStoryboard");

  if (oEl) oEl.value = bak.outline || '';
  if (iEl) iEl.value = bak.image || '';
  if (vEl) vEl.value = bak.voiceover || '';
  if (pEl) pEl.value = bak.polish || '';
  if (sEl) sEl.value = bak.storyboard || '';
  
  // 回滚定妆提示词缓存并重新生成输入框
  state.tempCastPrompts = parseCastPrompt(bak.cast_prompt || '');
  renderCastPromptFields();
  
  showToast("🔙 已还原到上一版本提示词。点『保存频道』确认应用。");
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

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

function addCustomAssetRow(label = "", type = "character", customImagePath = "") {
  const container = document.getElementById("customAssetsList");
  if (!container) return;
  if (container.children.length >= 6) {
    showToast("⚠️ 最多支持配置 6 张卡片！");
    return;
  }
  const div = document.createElement("div");
  div.className = "flex flex-col gap-2 bg-[#020408] border border-slate-900/60 rounded-xl p-2.5 animate-fade-in";
  div.dataset.customImagePath = customImagePath;
  div.innerHTML = `
    <div class="flex items-center gap-2 w-full">
      <input type="text" placeholder="卡片名称 (如: 小红)" class="flex-1 bg-[#05070E] border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none" value="${escapeHtml(label)}" oninput="onAssetLabelInput(this)">
      <select class="bg-[#05070E] border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:border-indigo-500 focus:outline-none" onchange="renderCastPromptFields()">
        <option value="character" ${type === 'character' ? 'selected' : ''}>👤 角色</option>
        <option value="scene" ${type === 'scene' ? 'selected' : ''}>🌅 场景</option>
        <option value="prop" ${type === 'prop' ? 'selected' : ''}>🎒 道具</option>
      </select>
      <div class="upload-btn-container"></div>
      <button type="button" onclick="this.parentElement.parentElement.remove(); renderCastPromptFields();" class="p-1.5 text-slate-500 hover:text-red-400 transition-all cursor-pointer">
        ✕
      </button>
    </div>
  `;
  container.appendChild(div);
  updateAssetRowUploadButton(div);
  renderCastPromptFields();
}

function onAssetLabelInput(input) {
  const row = input.parentElement.parentElement;
  updateAssetRowUploadButton(row);
  renderCastPromptFields();
}

function updateAssetRowUploadButton(row) {
  const input = row.querySelector("input");
  const uploadContainer = row.querySelector(".upload-btn-container");
  if (!input || !uploadContainer) return;
  
  const val = input.value.trim();
  if (!isGenericLabel(val)) {
    const path = row.dataset.customImagePath || "";
    uploadContainer.innerHTML = `
      <button type="button" onclick="uploadCustomAssetImage(this)" class="px-2 py-1.5 ${path ? 'bg-emerald-600 hover:bg-emerald-700 text-white' : 'bg-indigo-900/60 hover:bg-indigo-800 text-indigo-200'} border border-indigo-900/40 rounded-lg text-xs flex items-center gap-1 transition-all cursor-pointer whitespace-nowrap font-bold">
        ${path ? '✔ 已选图' : '📤 上传图片'}
      </button>
    `;
  } else {
    uploadContainer.innerHTML = "";
    row.dataset.customImagePath = "";
  }
}

async function uploadCustomAssetImage(btn) {
  if (typeof pywebview === 'undefined' || !pywebview.api) {
    showToast("⚠️ 桌面系统接口未就绪，无法上传本地图片");
    return;
  }
  const row = btn.parentElement.parentElement.parentElement;
  const input = row.querySelector("input");
  const label = input ? input.value.trim() : "custom_asset";
  
  btn.disabled = true;
  const oldText = btn.innerHTML;
  btn.innerText = "⏳ 请选择...";
  
  try {
    const res = await pywebview.api.select_custom_asset_image({
      channel_id: _editingChannelId || 'temp_channel',
      label: label
    });
    
    if (res.status === "success") {
      row.dataset.customImagePath = res.image_path;
      showToast("🎉 图片上传保存成功！");
      updateAssetRowUploadButton(row);
      renderCastPromptFields();
    } else if (res.status === "cancel") {
      showToast("已取消选择图片");
      updateAssetRowUploadButton(row);
    } else {
      showToast(`⚠️ 上传失败: ${res.detail}`);
      updateAssetRowUploadButton(row);
    }
  } catch (err) {
    showToast(`⚠️ 上传异常: ${err}`);
    updateAssetRowUploadButton(row);
  } finally {
    btn.disabled = false;
  }
}

async function autoDescribeAssetImage(label, type, imagePath, btn) {
  if (typeof pywebview === 'undefined' || !pywebview.api) {
    showToast("⚠️ 桌面系统接口未就绪，无法使用智能识图");
    return;
  }
  btn.disabled = true;
  const oldText = btn.innerHTML;
  btn.innerText = "🤖 智能识别中...";
  
  try {
    const res = await pywebview.api.describe_custom_asset_image({
      image_path: imagePath,
      type: type
    });
    
    if (res.status === "success" && res.description) {
      const ta = document.querySelector(`textarea[data-label="${label}"]`);
      if (ta) {
        ta.value = res.description;
        state.tempCastPrompts[label] = res.description;
      }
      showToast("🎉 智能识别成功，已自动填入描述！");
    } else {
      showToast(`⚠️ 智能识别失败: ${res.detail || "未知错误"}`);
    }
  } catch (err) {
    showToast(`⚠️ 识别异常: ${err}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = oldText;
  }
}

function renderAssetCards() {
  const container = document.getElementById("castingCardsGallery");
  if (!container) return;
  container.innerHTML = "";

  const N = state.assets.length;
  if (N === 0) return;

  if (N === 1) {
    container.className = "flex justify-center max-w-md mx-auto w-full";
  } else if (N === 2) {
    container.className = "grid grid-cols-1 md:grid-cols-2 gap-6 max-w-3xl mx-auto w-full";
  } else if (N === 3) {
    container.className = "grid grid-cols-1 md:grid-cols-3 gap-6 w-full";
  } else if (N === 4) {
    container.className = "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 w-full";
  } else {
    container.className = "grid grid-cols-1 md:grid-cols-3 gap-6 w-full";
  }

  state.assets.forEach((ast, idx) => {
    const cardDiv = document.createElement("div");
    cardDiv.onclick = () => openD1_1(idx);
    cardDiv.className = "group relative bg-[#0D1227] border border-slate-800 hover:border-indigo-500/80 rounded-2xl shadow-2xl p-4 cursor-pointer transition-all duration-500 hover:-translate-y-2 hover:shadow-[0_15px_30px_rgba(99,102,241,0.15)] flex flex-col space-y-3 w-full animate-fade-in";
    cardDiv.innerHTML = `
      <div class="absolute top-0 inset-x-0 h-[2px] bg-gradient-to-r from-transparent via-indigo-500 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
      
      <div class="relative w-full aspect-[4/3] bg-slate-950 rounded-xl border border-slate-850 overflow-hidden flex items-center justify-center" id="cardImg${idx}">
        ${ast.image_url ? `<img src="${ast.image_url}" class="w-full h-full object-cover group-hover:scale-105 transition duration-500" />` : `<div class="text-xs text-slate-600 animate-pulse">Awaiting ${escapeHtml(ast.name)}</div>`}
      </div>
      
      <div class="space-y-1">
        <div class="flex justify-between items-center gap-1.5">
          <span class="text-xs font-bold text-slate-100 truncate" id="cardName${idx}">${escapeHtml(ast.name)}</span>
          <div class="flex items-center gap-1 shrink-0">
            ${ast.custom_image_path ? '<span class="px-1.5 py-0.5 bg-emerald-950/60 text-[9px] font-bold text-emerald-350 rounded font-mono">CUSTOM</span>' : ''}
            <span class="px-1.5 py-0.5 bg-indigo-900/40 text-[9px] font-bold text-indigo-300 rounded font-mono">0${idx + 1}</span>
          </div>
        </div>
        <p class="text-[10px] text-slate-400 line-clamp-2 leading-relaxed" id="cardPrompt${idx}">${escapeHtml(ast.prompt || 'Generating...')}</p>
      </div>
      <div class="pt-2 border-t border-slate-850 flex items-center justify-between text-[10px] text-indigo-400 font-bold group-hover:text-indigo-300">
        <span>提示词精整</span>
        <span>点击调优 ›</span>
      </div>
    `;
    container.appendChild(cardDiv);
  });
}

function resetToHome() {
  navigateTo("A");
}

function loadDemoScript() {
  const ch = getActiveChannel();
  let script = "在 2098 年的霓虹雨夜，老钟表匠擦拭着手里的一枚神秘发光怀表。表盘的指针发生了诡异的逆向旋转，记忆深处的星空誓言再次浮现在眼前。";
  if (ch && ch.id === "ch_science") {
    script = "我们每天看到的太阳光，实际上需要穿过极其庞大、密集的太阳内部粒子堆。光子在太阳内部通过『随机漫步』不断折射碰撞，最终在经历约十万年的艰难求索后，才在短短 8 分钟内跨越真空，抵达我们的双眼。";
  }
  const ta = document.getElementById("rawScriptTextarea");
  if (ta) ta.value = script;
  state.rawScript = script;
  syncRawScriptToState();
  showToast("🎬 Demo 剧本已载入！");
}

function togglePolishSwitch() {
  const toggle = document.getElementById("polishToggle");
  if (!toggle) return;
  state.polishEnabled = toggle.checked;
  
  const tag = document.getElementById("polishStatusTag");
  const desc = document.getElementById("polishDesc");
  
  if (toggle.checked) {
    if (tag) {
      tag.innerText = "✨ 润色已开启 (智能修饰)";
      tag.className = "px-2 py-0.5 bg-indigo-900 border border-indigo-800 text-[9px] text-indigo-300 rounded";
    }
    if (desc) desc.innerText = "智能修饰模式：允许大模型对您的原文大纲进行扩写润色，丰富文学色彩，产生更高级的电影分镜。";
  } else {
    if (tag) {
      tag.innerText = "已关闭 (原稿锁死)";
      tag.className = "px-2 py-0.5 bg-slate-900 border border-slate-800 text-[9px] text-slate-400 rounded";
    }
    if (desc) desc.innerText = "锁死直出模式：系统将直接物理切片分析您的文字，大模型生成旁白时绝不篡改、增删任何字词，原汁原味透传！";
  }
  
  updateJsonPayloadViewer();
}

// ── 🎙️ 火山/Edge TTS 控制层事件响应 ──
function initTtsSettingsFromState() {
  const engine = state.presets.tts_engine || "edge";
  selectTtsEngine(engine, false);
  
  // 初始化滑块与文本框的值
  const pitchRange = document.getElementById("voicePitchRange");
  const pitchVal = document.getElementById("voicePitchVal");
  if (pitchRange && pitchVal) {
    pitchRange.value = state.presets.voice_pitch !== undefined ? state.presets.voice_pitch : 0;
    pitchVal.innerText = pitchRange.value;
  }
  const volumeRange = document.getElementById("voiceVolumeRange");
  const volumeVal = document.getElementById("voiceVolumeVal");
  if (volumeRange && volumeVal) {
    volumeRange.value = state.presets.voice_volume !== undefined ? state.presets.voice_volume : 0;
    volumeVal.innerText = volumeRange.value;
  }
  const promptInput = document.getElementById("voicePromptInput");
  if (promptInput) {
    promptInput.value = state.presets.voice_prompt || "";
  }
}

function selectTtsEngine(engine, triggerChange = true) {
  state.presets.tts_engine = engine;
  
  const edgeBtn = document.getElementById("engineEdgeBtn");
  const volcBtn = document.getElementById("engineVolcBtn");
  
  if (engine === "volc") {
    if (edgeBtn) edgeBtn.className = "px-3 py-1 text-[10px] font-bold rounded transition-all cursor-pointer text-slate-400 hover:text-slate-200";
    if (volcBtn) volcBtn.className = "px-3 py-1 text-[10px] font-bold rounded transition-all cursor-pointer bg-indigo-600 text-white shadow";
    
    // 显示情绪选择器、高级配置和提示卡片
    const emoGroup = document.getElementById("voiceEmotionGroup");
    if (emoGroup) emoGroup.classList.remove("hidden");
    const advGroup = document.getElementById("volcAdvancedSettings");
    if (advGroup) advGroup.classList.remove("hidden");
    const tipCard = document.getElementById("volcEmotionTipCard");
    if (tipCard) tipCard.classList.remove("hidden");
  } else {
    if (edgeBtn) edgeBtn.className = "px-3 py-1 text-[10px] font-bold rounded transition-all cursor-pointer bg-indigo-600 text-white shadow";
    if (volcBtn) volcBtn.className = "px-3 py-1 text-[10px] font-bold rounded transition-all cursor-pointer text-slate-400 hover:text-slate-200";
    
    // 隐藏情绪选择器、高级配置和提示卡片
    const emoGroup = document.getElementById("voiceEmotionGroup");
    if (emoGroup) emoGroup.classList.add("hidden");
    const advGroup = document.getElementById("volcAdvancedSettings");
    if (advGroup) advGroup.classList.add("hidden");
    const tipCard = document.getElementById("volcEmotionTipCard");
    if (tipCard) tipCard.classList.add("hidden");
  }
  
  populateVoiceRolesAndRates(false);
  
  if (triggerChange) {
    onVoiceSettingChange();
  }
}

function populateVoiceRolesAndRates(resetToDefault = false) {
  const engine = state.presets.tts_engine || "edge";
  const selector = document.getElementById("voiceRoleSelector");
  if (!selector) return;
  
  selector.innerHTML = "";
  
  const edgeVoices = [
    { value: "zh-CN-YunjianNeural", text: "👨 云健 (深沉男声/解说首选)" },
    { value: "zh-CN-YunxiNeural", text: "👦 云希 (活泼男声/剧情首选)" },
    { value: "zh-CN-XiaoxiaoNeural", text: "👧 晓晓 (温柔女声/甜美)" },
    { value: "zh-CN-YunyangNeural", text: "🧔 云扬 (庄重男声/新闻播报)" },
    { value: "zh-CN-XiaoyiNeural", text: "👩 晓伊 (温暖女声)" },
    { value: "zh-CN-YunjieNeural", text: "🧔 云杰 (沉稳男声)" },
    { value: "zh-CN-LiaoningNeural", text: "🗣️ 东北辽宁话 (特色方言)" },
    { value: "zh-CN-ShaanxiNeural", text: "🗣️ 陕西方言 (特色方言)" },
    { value: "zh-HK-HiuMaanNeural", text: "👩 晓曼 (粤语女声)" },
    { value: "zh-HK-WanLungNeural", text: "👨 云龙 (粤语男声)" },
    { value: "zh-TW-HsiaoChenNeural", text: "👩 晓臻 (闽南语女声)" },
    { value: "zh-TW-YunJheNeural", text: "👨 云哲 (闽南语男声)" }
  ];
  
  const volcVoices = [
    { value: "zh_female_vv_uranus_bigtts", text: "👧 Vivi 2.0 (故事大模型女声)" },
    { value: "saturn_zh_female_cancan_tob", text: "👧 知性灿灿 (大模型2.0角色扮演女声)" },
    { value: "saturn_zh_female_kexinshaonv_tob", text: "👧 可馨女生 (大模型2.0角色扮演女声)" },
    { value: "saturn_zh_female_tiaopigongzhu_tob", text: "👧 调皮公主 (大模型2.0角色扮演女声)" },
    { value: "saturn_zh_male_shuangliangshaonian_tob", text: "👦 爽朗少年 (大模型2.0角色扮演男声)" },
    { value: "saturn_zh_male_tiancaitongzhuo_tob", text: "👦 天才同桌 (大模型2.0角色扮演男声)" },
    { value: "zh_female_xiaohe_uranus_bigtts", text: "👧 小何 2.0 (故事大模型女声)" },
    { value: "zh_male_m191_uranus_bigtts", text: "👦 云舟 2.0 (故事大模型男声)" },
    { value: "zh_female_peiqi_uranus_bigtts", text: "👧 佩奇 2.0 (故事大模型女声)" },
    { value: "zh_male_xuanyijieshuo_uranus_bigtts", text: "🧔 悬疑解说 2.0 (故事大模型男声)" },
    { value: "zh_male_deep_podcast_uranus_bigtts", text: "👨 深夜播客 (多情感1.0男声)" },
    { value: "zh_female_giga_boss_uranus_bigtts", text: "👩 高冷御姐 (多情感1.0女声)" },
    { value: "zh_female_neighbor_aunt_uranus_bigtts", text: "👩 邻居阿姨 (多情感1.0女声)" },
    { value: "zh_female_shuangkuaisisi_moon_bigtts", text: "👧 爽快丝丝 (1.0经典女声)" },
    { value: "zh_male_shuangkuaiyunjie_moon_bigtts", text: "👨 爽快云杰 (1.0经典男声)" },
    { value: "zh_female_story_bigtts", text: "👩 讲述女声 (1.0故事女声)" },
    { value: "zh_male_story_bigtts", text: "🧔 讲述男声 (1.0故事男声)" },
    { value: "zh_male_boy_bigtts", text: "👦 阳光男孩 (1.0经典童声)" },
    { value: "zh_female_girl_bigtts", text: "👧 甜美女孩 (1.0经典童声)" },
    { value: "zh_male_game_bigtts", text: "🧔 游戏解说 (1.0解说男声)" },
    { value: "zh_female_xiaoxue_bigtts", text: "👩 小雪 (温柔女声)" },
    { value: "zh_female_miaomiao_bigtts", text: "👧 妙妙 (可爱女声)" },
    { value: "zh_female_xiaojie_bigtts", text: "👩 小洁 (温暖女声)" },
    { value: "zh_male_xiaohan_bigtts", text: "👦 小韩 (阳光男声)" },
    { value: "zh_male_xiaokun_bigtts", text: "🧔 小坤 (沉稳男声)" },
    { value: "S_SbhrW9GN1", text: "🎙️ 人生体验 (我的克隆音色)" },
    { value: "icl_my_clone", text: "🎙️ 声音复刻 2.0 (ICL大模型)" },
    { value: "custom", text: "✍️ 自定义输入音色标识..." }
  ];
  
  const targetVoices = (engine === "volc") ? [...volcVoices] : [...edgeVoices];
  
  // 动态加载用户在 localStorage 中保存的自定义音色列表
  let customVoices = [];
  try {
    const raw = localStorage.getItem("palette_custom_voices");
    if (raw) {
      customVoices = JSON.parse(raw);
    }
  } catch (e) {
    console.error("加载自定义音色列表失败:", e);
  }

  // 过滤并插入自定义音色到 custom 选项前
  customVoices.forEach(cv => {
    if (cv.engine === engine) {
      const item = { value: cv.id, text: `👤 [自定义] ${cv.name}` };
      const customIndex = targetVoices.findIndex(v => v.value === "custom");
      if (customIndex !== -1) {
        targetVoices.splice(customIndex, 0, item);
      } else {
        targetVoices.push(item);
      }
    }
  });

  targetVoices.forEach(v => {
    const opt = document.createElement("option");
    opt.value = v.value;
    opt.innerText = v.text;
    selector.appendChild(opt);
  });
  
  let currentVal = state.presets.voice_role;
  const isVolc = (engine === "volc");
  
  // 检查当前值是否在此列表中
  const valExists = targetVoices.some(v => v.value === currentVal);
  
  if (resetToDefault || !currentVal) {
    currentVal = isVolc ? "saturn_zh_female_cancan_tob" : "zh-CN-YunjianNeural";
  } else if (!valExists) {
    // 如果值不存在且不是 custom，但在 volcano 引擎下，有可能是用户自己输入的自定义音色名（非 custom value）
    if (isVolc && currentVal !== "custom") {
      // 这是一个输入框定义的自定义值，我们自动将 select 指向 "custom"，并把输入框展现出来
      selector.value = "custom";
      const customInput = document.getElementById("customVoiceInput");
      if (customInput) {
        customInput.value = currentVal;
        customInput.classList.remove("hidden");
      }
      // 直接返回
      updateVoiceRateAndEmotionSelectors();
      return;
    } else {
      // Edge-TTS 或者是其他，退回默认
      currentVal = isVolc ? "saturn_zh_female_cancan_tob" : "zh-CN-YunjianNeural";
    }
  }
  
  selector.value = currentVal;
  
  // 处理自定义输入框的展现/隐藏
  const customInput = document.getElementById("customVoiceInput");
  if (customInput) {
    if (currentVal === "custom") {
      customInput.classList.remove("hidden");
      customInput.value = "";
    } else {
      customInput.classList.add("hidden");
    }
  }
  
  toggleCustomVoicePanels();
  updateVoiceRateAndEmotionSelectors();
}

function updateVoiceRateAndEmotionSelectors() {
  const rateSelector = document.getElementById("voiceRateSelector");
  if (rateSelector && state.presets.voice_rate) {
    rateSelector.value = state.presets.voice_rate;
  }
  
  const emotionSelector = document.getElementById("voiceEmotionSelector");
  if (emotionSelector && state.presets.voice_emotion) {
    emotionSelector.value = state.presets.voice_emotion;
  }
  
  const pitchRange = document.getElementById("voicePitchRange");
  const pitchVal = document.getElementById("voicePitchVal");
  if (pitchRange && pitchVal) {
    pitchRange.value = state.presets.voice_pitch !== undefined ? state.presets.voice_pitch : 0;
    pitchVal.innerText = pitchRange.value;
  }
  
  const volumeRange = document.getElementById("voiceVolumeRange");
  const volumeVal = document.getElementById("voiceVolumeVal");
  if (volumeRange && volumeVal) {
    volumeRange.value = state.presets.voice_volume !== undefined ? state.presets.voice_volume : 0;
    volumeVal.innerText = volumeRange.value;
  }
  
  const promptInput = document.getElementById("voicePromptInput");
  if (promptInput) {
    promptInput.value = state.presets.voice_prompt || "";
  }
}

function onVoiceSettingChange() {
  const engine = state.presets.tts_engine || "edge";
  const selector = document.getElementById("voiceRoleSelector");
  const customInput = document.getElementById("customVoiceInput");
  const rateSelector = document.getElementById("voiceRateSelector");
  const emotionSelector = document.getElementById("voiceEmotionSelector");
  const pitchRange = document.getElementById("voicePitchRange");
  const volumeRange = document.getElementById("voiceVolumeRange");
  const promptInput = document.getElementById("voicePromptInput");
  
  if (!selector) return;
  
  let role = selector.value;
  if (role === "custom" && customInput) {
    customInput.classList.remove("hidden");
    role = customInput.value.trim() || "saturn_zh_female_cancan_tob";
  } else if (customInput) {
    customInput.classList.add("hidden");
  }
  
  state.presets.voice_role = role;
  if (rateSelector) state.presets.voice_rate = rateSelector.value;
  if (emotionSelector) state.presets.voice_emotion = emotionSelector.value;
  if (pitchRange) state.presets.voice_pitch = parseInt(pitchRange.value || 0);
  if (volumeRange) state.presets.voice_volume = parseInt(volumeRange.value || 0);
  if (promptInput) state.presets.voice_prompt = promptInput.value;
  
  // 同步到频道 Preset
  const ch = getActiveChannel();
  if (ch) {
    if (!ch.presets) ch.presets = {};
    ch.presets.tts_engine = state.presets.tts_engine;
    ch.presets.voice_role = state.presets.voice_role;
    ch.presets.voice_rate = state.presets.voice_rate;
    ch.presets.voice_emotion = state.presets.voice_emotion;
    ch.presets.voice_pitch = state.presets.voice_pitch;
    ch.presets.voice_volume = state.presets.voice_volume;
    ch.presets.voice_prompt = state.presets.voice_prompt;
    saveChannelsToStorage();
  }
  
  toggleCustomVoicePanels();
  updateJsonPayloadViewer();
}

function switchPromptCategory(cat) {
  const cats = ["image", "polish", "voiceover", "outline", "storyboard", "cast_prompt"];
  cats.forEach(c => {
    const area = document.getElementById(`promptArea-${c}`);
    if (area) area.classList.add("hidden");
    const btn = document.getElementById(`catBtn-${c}`);
    if (btn) btn.className = "w-full text-left p-4 rounded-xl border border-slate-900 bg-slate-950/20 text-slate-400 hover:text-slate-200 transition-all flex flex-col space-y-1";
  });
  
  const targetArea = document.getElementById(`promptArea-${cat}`);
  if (targetArea) targetArea.classList.remove("hidden");
  const targetBtn = document.getElementById(`catBtn-${cat}`);
  if (targetBtn) targetBtn.className = "w-full text-left p-4 rounded-xl border border-indigo-500/20 bg-indigo-950/20 text-slate-200 transition-all flex flex-col space-y-1";
}

function appendPromptTag(tag) {
  const area = document.getElementById("promptText-image");
  if (!area) return;
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
  const val = DEFAULT_PRESETS[cat] || "";
  const el = document.getElementById(`promptText-${cat}`);
  if (el) el.value = val;
  state.presets[cat] = val;
  syncPromptToState(cat);
  showToast("🔄 参数已重置为出厂默认设置。");
}

function savePresets() {
  const ch = getActiveChannel();
  if (ch) {
    if (!ch.presets) ch.presets = {};
    ch.presets.image     = state.presets.image;
    ch.presets.polish    = state.presets.polish;
    ch.presets.voiceover = state.presets.voiceover;
    ch.presets.outline   = state.presets.outline;
    ch.presets.storyboard = state.presets.storyboard;
    ch.presets.cast_prompt = state.presets.cast_prompt;
    saveChannelsToStorage();
  }
  showToast(`💾 「${ch ? ch.name : '当前频道'}」的提示词预设已同步！`);
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
        system_prompt: state.presets.voiceover,
        engine: state.presets.tts_engine || "edge",
        voice_role: state.presets.voice_role || "",
        voice_rate: state.presets.voice_rate || "",
        voice_emotion: state.presets.voice_emotion || "",
        voice_pitch: parseInt(state.presets.voice_pitch || 0),
        voice_volume: parseInt(state.presets.voice_volume || 0),
        voice_prompt: state.presets.voice_prompt || ""
      },
      render_flow: {
        style_presets: state.presets.image,
        seed: state.seed,
        cast_prompt: state.presets.cast_prompt,
        storyboard_prompt: state.presets.storyboard
      }
    }
  };
  const viewer = document.getElementById("jsonPayloadViewer");
  if (viewer) viewer.innerText = JSON.stringify(payload, null, 2);
}

async function triggerChannelShake() {
  if (state.isRunning) { showToast("⏳ 上一个请求还在运行中，请稍候！"); return; }

  const ch = getActiveChannel();
  const outlinePrompt = state.presets.outline;

  const btn = document.getElementById("c1ShakeBtn");
  const btnIcon = document.getElementById("c1ShakeBtnIcon");
  const originalIcon = btnIcon ? btnIcon.innerText : "🎲";
  if (btn) btn.disabled = true;
  if (btnIcon) btnIcon.innerText = "⏳";
  showToast(`🎲 正在为「${ch ? ch.name : '当前频道'}」脑暴剧本灵感...`);

  try {
    const res = await pywebview.api.compile_story({
      app_id: "palette-cinema-id",
      mode_path: state.modePath,
      original_text: "请根据本频道的创作方向，为我随机生成一个精彩的短视频故事大纲。",
      pipeline_config: {
        polish_flow: { enabled: true, system_prompt: outlinePrompt },
        voiceover_flow: { system_prompt: state.presets.voiceover },
        render_flow: { style_presets: state.presets.image, seed: Date.now() % 99999 }
      }
    });

    if (res.status === "success") {
      const outline = res.data.compiled_voiceover || "";
      const ta = document.getElementById("rawScriptTextarea");
      if (ta) { ta.value = outline; }
      state.rawScript = outline;
      saveChannelDraft(outline);
      syncRawScriptToState();
      showToast("🎉 脑暴灵感已生成并填入！您可以直接修改后发射！");
    } else {
      showCustomModal("⚠️ 后端排队中", "脑暴大纲生成失败，请重试！");
    }
  } catch(err) {
    handleApiError(err, triggerChannelShake);
  } finally {
    if (btn) btn.disabled = false;
    if (btnIcon) btnIcon.innerText = originalIcon;
  }
}

async function triggerShake() {
  await triggerChannelShake();
}

function submitD2ToD1() {
  const feedbackInput = document.getElementById("d2FeedbackInput");
  const feedback = feedbackInput ? feedbackInput.value : "";
  if (feedback.trim()) {
    showToast("💡 大纲修订建议已录入...");
  }
  setTimeout(() => {
    handleC1Launch(state.rawScript);
  }, 800);
}

async function handleC1Launch(directText = null) {
  const text = directText || state.rawScript;
  if (!text.trim()) {
    showCustomModal("⚠️ 提示", "大导演，剧本内容不能为空哦，请输入您的创意大纲！");
    return;
  }

  if (state.assets && state.assets.length > 0 && state.compiledVoiceover && state.lastCompiledText === text) {
    navigateTo("D1");
    
    const d1ResArea = document.getElementById("d1ResultArea");
    if (d1ResArea) d1ResArea.classList.remove("hidden");
    
    const p1Bar = document.getElementById("p1Bar");
    const p1Val = document.getElementById("p1Val");
    const p2Bar = document.getElementById("p2Bar");
    const p2Val = document.getElementById("p2Val");
    const logText = document.getElementById("assistantLogText");
    
    if (p1Bar) p1Bar.style.width = "100%";
    if (p1Val) p1Val.innerText = "100%";
    const p1Dot = document.getElementById("p1StatusDot");
    if (p1Dot) p1Dot.className = "w-2.5 h-2.5 rounded-full bg-emerald-500";
    const p1Txt = document.getElementById("p1StatusText");
    if (p1Txt) {
      p1Txt.className = "text-emerald-400";
      p1Txt.innerText = "1. 第三人称解说词文本已就绪！";
    }
    
    if (p2Bar) p2Bar.style.width = "100%";
    if (p2Val) p2Val.innerText = "100%";
    const p2Dot = document.getElementById("p2StatusDot");
    if (p2Dot) p2Dot.className = "w-2.5 h-2.5 rounded-full bg-emerald-500";
    const p2Txt = document.getElementById("p2StatusText");
    if (p2Txt) {
      p2Txt.className = "text-emerald-400";
      p2Txt.innerText = "2. 角色及美术场景定妆大画卡集已绘制成功！";
    }
    
    if (logText) logText.innerText = "🎉 恭喜！旁白与定妆画已就绪，大卡片画廊已解锁！";
    
    const nBtn = document.getElementById("d1NextBtn");
    if (nBtn) {
      nBtn.disabled = false;
      nBtn.className = "px-8 py-3.5 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl shadow-lg transition-all text-xs tracking-wider uppercase";
    }
    
    showToast("✨ 旁白与定妆资产已存在，直接为您展示！");
    return;
  }

  navigateTo("D1");
  
  const p1Bar = document.getElementById("p1Bar");
  const p1Val = document.getElementById("p1Val");
  const p2Bar = document.getElementById("p2Bar");
  const p2Val = document.getElementById("p2Val");
  const logText = document.getElementById("assistantLogText");
  const lockBadge = document.getElementById("d1LockBadge");
  
  if (p1Bar) p1Bar.style.width = "0%";
  if (p1Val) p1Val.innerText = "0%";
  if (p2Bar) p2Bar.style.width = "0%";
  if (p2Val) p2Val.innerText = "0%";

  if (lockBadge) {
    lockBadge.innerText = state.polishEnabled ? "✨ SMART_POLISH_FLOW" : "🔒 ORIGINAL_TEXT_LOCKED";
    lockBadge.className = state.polishEnabled ? "px-2 py-0.5 text-[9px] tracking-widest uppercase font-bold rounded bg-indigo-950 border border-indigo-800 text-indigo-200" : "px-2 py-0.5 text-[9px] tracking-widest uppercase font-bold rounded bg-red-950 border border-red-800/80 text-red-200";
  }

  try {
    if (logText) logText.innerText = "[第1步] 正在呼唤大模型提炼大纲并编译解说旁白文本 (预计 5 秒)...";
    if (p1Bar) p1Bar.style.width = "40%";
    if (p1Val) p1Val.innerText = "40%";

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
          voiceover_flow: { 
            system_prompt: state.presets.voiceover,
            engine: state.presets.tts_engine || "edge",
            voice_role: state.presets.voice_role || "",
            voice_rate: state.presets.voice_rate || "",
            voice_emotion: state.presets.voice_emotion || "",
            voice_pitch: parseInt(state.presets.voice_pitch || 0),
            voice_volume: parseInt(state.presets.voice_volume || 0),
            voice_prompt: state.presets.voice_prompt || ""
          },
          render_flow: { 
            style_presets: state.presets.image, 
            seed: state.seed,
            cast_prompt: state.presets.cast_prompt,
            storyboard_prompt: state.presets.storyboard
          }
        }
      });
    if (cData.status !== "success") {
      throw new Error(cData.detail || "剧本编译失败");
    }

    state.compiledVoiceover = cData.data.compiled_voiceover;
    state.lastCompiledText = text;
    state.extractedEntities = cData.data.extracted_entities;
    state.assets_to_generate = cData.data.assets_to_generate || [];

    if (p1Bar) p1Bar.style.width = "100%";
    if (p1Val) p1Val.innerText = "100%";
    const p1Dot = document.getElementById("p1StatusDot");
    if (p1Dot) p1Dot.className = "w-2.5 h-2.5 rounded-full bg-emerald-500";
    const p1Txt = document.getElementById("p1StatusText");
    if (p1Txt) {
      p1Txt.className = "text-emerald-400";
      p1Txt.innerText = "1. 第三人称解说词文本已就绪！";
    }
    
    const d1VoiceoverEl = document.getElementById("d1VoiceoverOutput");
    if (d1VoiceoverEl) d1VoiceoverEl.innerText = state.compiledVoiceover;

    if (logText) logText.innerText = "[第2步] 解说词已全部编译就绪！正在物理派生生图引擎绘制 3 大核心资产 (预计 20 秒)...";
    const p2Dot = document.getElementById("p2StatusDot");
    if (p2Dot) p2Dot.className = "w-2.5 h-2.5 rounded-full bg-indigo-500 animate-ping";
    const p2Txt = document.getElementById("p2StatusText");
    if (p2Txt) {
      p2Txt.className = "text-slate-350";
    }
    if (p2Bar) p2Bar.style.width = "20%";
    if (p2Val) p2Val.innerText = "20%";

    let logSec = 0;
    const logTimer = setInterval(() => {
      logSec += 3;
      if (logText) {
        if (state.extractedEntities && state.extractedEntities.length === 1) {
          logText.innerText = `[第2步] 正在由画画引擎全力绘制【${state.extractedEntities[0] || '视觉基底'}】视觉背景底板...`;
        } else {
          if (logSec === 3) logText.innerText = `[第2步] 正在由画画引擎全力绘制【${state.extractedEntities[0] || '角色'}】定妆三视图...`;
          else if (logSec === 9) logText.innerText = `[第2步] 正在绘制【${state.extractedEntities[1] || '场景'}】电影大场景立绘...`;
          else if (logSec === 15) logText.innerText = `[第2步] 正在绘制【${state.extractedEntities[2] || '道具'}】线索道具图...`;
        }
      }
      
      let curPercent = Math.min(85, 20 + logSec * 3);
      if (p2Bar) p2Bar.style.width = `${curPercent}%`;
      if (p2Val) p2Val.innerText = `${curPercent}%`;
    }, 1500);

    const aData = await pywebview.api.generate_assets({
        entities: state.extractedEntities,
        global_style_prompt: state.presets.image,
        seed: state.seed,
        assets_to_generate: state.assets_to_generate
      });
    clearInterval(logTimer);
    if (aData.status !== "success") {
      throw new Error(aData.detail || "定妆照生图失败");
    }

    state.assets = aData.assets;
    renderAssetCards();

    if (p2Bar) p2Bar.style.width = "100%";
    if (p2Val) p2Val.innerText = "100%";
    const p2DotFinal = document.getElementById("p2StatusDot");
    if (p2DotFinal) p2DotFinal.className = "w-2.5 h-2.5 rounded-full bg-emerald-500";
    const p2TxtFinal = document.getElementById("p2StatusText");
    if (p2TxtFinal) {
      p2TxtFinal.className = "text-emerald-400";
      p2TxtFinal.innerText = "2. 角色及美术场景定妆大画卡集已绘制成功！";
    }
    
    if (logText) logText.innerText = "🎉 恭喜！大纲编译及资产三视图绘制圆满通过，大卡片画廊已解锁！";
    const d1ResultArea = document.getElementById("d1ResultArea");
    if (d1ResultArea) d1ResultArea.classList.remove("hidden");
    
    const nBtn = document.getElementById("d1NextBtn");
    if (nBtn) {
      nBtn.disabled = false;
      nBtn.className = "px-8 py-3.5 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl shadow-lg transition-all text-xs tracking-wider uppercase";
    }

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
  if (!ast) return;
  
  const title = document.getElementById("d1_1_Title");
  const promptInput = document.getElementById("d1_1_PromptInput");
  const previewArea = document.getElementById("d1_1_PreviewArea");

  if (title) title.innerText = `定妆画资产细节深度精整 - [${ast.name}] (D1.1)`;
  if (promptInput) promptInput.value = ast.prompt;
  
  const tabNew = document.getElementById("previewTab-new");
  const tabOld = document.getElementById("previewTab-old");
  if (tabNew) tabNew.className = "px-2 py-1 bg-indigo-600 text-[10px] text-white rounded font-bold";
  if (tabOld) tabOld.className = "px-2 py-1 text-[10px] text-slate-400 hover:text-slate-200 rounded";

  if (previewArea) {
    previewArea.innerHTML = `<img id="d1_1_preview_img" src="${ast.image_url}" class="max-w-full max-h-[300px] object-contain rounded-lg shadow-xl" />`;
  }
  
  if (!state.assetHistory[ast.id]) {
    state.assetHistory[ast.id] = {
      new_url: ast.image_url,
      old_url: ast.image_url
    };
  }

  // Disable textarea and button if redrawing is in progress
  const isRedrawing = state.runningRedraws[ast.id] === true;
  const rebuildBtn = document.getElementById("rebuildAssetBtn");
  if (promptInput) {
    promptInput.disabled = isRedrawing;
  }
  if (rebuildBtn) {
    rebuildBtn.disabled = isRedrawing;
    if (isRedrawing) {
      rebuildBtn.innerText = "🎨 后台正在重绘中...";
    } else {
      rebuildBtn.innerText = "💡 确定更新并进行局部重画";
    }
  }

  const overlay = document.getElementById("overlayD1_1");
  if (overlay) overlay.classList.remove("hidden");
}

function switchD1_1PreviewMode(mode) {
  activeD1_1PreviewMode = mode;
  const ast = state.assets[activeCardIndex];
  if (!ast) return;
  const hist = state.assetHistory[ast.id];
  if (!hist) return;
  
  const tabNew = document.getElementById("previewTab-new");
  const tabOld = document.getElementById("previewTab-old");
  const img = document.getElementById("d1_1_preview_img");

  if (mode === "new") {
    if (tabNew) tabNew.className = "px-2 py-1 bg-indigo-600 text-[10px] text-white rounded font-bold";
    if (tabOld) tabOld.className = "px-2 py-1 text-[10px] text-slate-400 hover:text-slate-200 rounded";
    if (img) img.src = hist.new_url;
  } else {
    if (tabOld) tabOld.className = "px-2 py-1 bg-indigo-600 text-[10px] text-white rounded font-bold";
    if (tabNew) tabNew.className = "px-2 py-1 text-[10px] text-slate-400 hover:text-slate-200 rounded";
    if (img) img.src = hist.old_url;
  }
}

async function rebuildAssetCard() {
  const ast = state.assets[activeCardIndex];
  if (!ast) return;
  
  const card_id = ast.id;
  if (state.runningRedraws[card_id]) {
    showToast("⚠️ 该卡片正在重绘中，请勿重复操作！");
    return;
  }
  
  const promptInput = document.getElementById("d1_1_PromptInput");
  const newPrompt = promptInput ? promptInput.value : "";
  
  // Mark as running redraw
  state.runningRedraws[card_id] = true;
  
  // Close the modal immediately
  closeD1_1_Force();
  
  // Put the gallery card in local loading state
  const targetIndex = activeCardIndex;
  const imgCont = document.getElementById(`cardImg${targetIndex}`);
  const originalHtml = imgCont ? imgCont.innerHTML : ""; // Keep original HTML in case of failure
  
  if (imgCont) {
    // Show glassmorphic overlay + loading spinner
    imgCont.style.position = "relative";
    imgCont.innerHTML = `
      ${originalHtml}
      <div class="absolute inset-0 bg-black/60 backdrop-blur-[2px] flex flex-col items-center justify-center text-white z-10">
        <svg class="animate-spin h-8 w-8 text-indigo-400 mb-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <span class="text-xs font-semibold animate-pulse text-indigo-200">重画中...</span>
      </div>
    `;
  }
  
  // Background asynchronous call
  pywebview.api.render_single_frame({
    target_id: card_id,
    prompt: newPrompt,
    seed: state.seed,
    style_lock: true
  })
  .then(res => {
    if (res && res.status === "success") {
      state.assetHistory[card_id].old_url = ast.image_url;
      state.assetHistory[card_id].new_url = res.render_url;
      
      ast.image_url = res.render_url;
      ast.prompt = newPrompt;
      
      const prmLabel = document.getElementById(`cardPrompt${targetIndex}`);
      if (prmLabel) prmLabel.innerText = newPrompt;
      const finalImgCont = document.getElementById(`cardImg${targetIndex}`);
      if (finalImgCont) {
        finalImgCont.innerHTML = `<img src="${res.render_url}" class="w-full h-full object-cover group-hover:scale-105 transition duration-500" />`;
      }
      showToast(`✨ 定妆照 [${ast.name}] 后台重绘成功！`);
    } else {
      // Restore card visual state
      const finalImgCont = document.getElementById(`cardImg${targetIndex}`);
      if (finalImgCont) {
        finalImgCont.innerHTML = originalHtml;
      }
      showCustomModal("⚠️ 生图失败", `定妆照 [${ast.name}] 重绘失败，请重试！`);
    }
  })
  .catch(err => {
    // Restore card visual state
    const finalImgCont = document.getElementById(`cardImg${targetIndex}`);
    if (finalImgCont) {
      finalImgCont.innerHTML = originalHtml;
    }
    showCustomModal("⚠️ 接口调用异常", `定妆照 [${ast.name}] 重绘失败: ` + String(err));
  })
  .finally(() => {
    // Release the redraw lock
    delete state.runningRedraws[card_id];
  });
}

function closeD1_1(event) {
  if (event && event.target && event.target.id === "overlayD1_1") {
    closeD1_1_Force();
  }
}
function closeD1_1_Force() {
  const overlay = document.getElementById("overlayD1_1");
  if (overlay) overlay.classList.add("hidden");
}

// ── 🎬 E 页面分镜底片生成 ──
async function handleD1Next() {
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
  showToast("🎞️ 正在物理切分旁白并插值生图分镜大宫格...");
  
  const densitySelect = document.getElementById("storyboardDensity");
  const density = densitySelect ? densitySelect.value : "medium";
  const gridModeSelect = document.getElementById("gridModeSelector");
  const gridMode = gridModeSelect ? gridModeSelect.value : "4x4";
  const panelsCount = gridMode === "2x2" ? 4 : (gridMode === "3x3" ? 9 : 16);
  
  const container = document.getElementById("storyboardGrid");
  if (container) {
    container.className = "flex items-center justify-center py-20 w-full";
    container.innerHTML = `
      <div class="text-center space-y-4">
        <div class="w-10 h-10 border-4 border-slate-750 border-t-indigo-500 rounded-full animate-spin mx-auto"></div>
        <div class="text-indigo-400 text-xs font-semibold tracking-wider animate-pulse">正在调用大模型极速渲染 ${panelsCount} 宫格大图，请稍后...</div>
      </div>
    `;
  }
  
  try {
    const res = await pywebview.api.generate_storyboard({ 
      density: density,
      grid_mode: gridMode
    });
    if (res.status === "success") {
      state.storyboardGrids = res.grids;
      if (res.frames) {
        state.storyboards = res.frames;
      }
      state.gridMode = res.grid_mode || gridMode;
      renderStoryboardGrids();
      showToast(`🎞️ ${panelsCount}宫格切图大网格渲染完毕！`);
    } else {
      showCustomModal("⚠️ 生成失败", res.detail || "底片插值失败，请重试！");
      renderStoryboardError(res.detail || "底片插值失败，请重试！");
    }
  } catch(err) {
    handleApiError(err, handleD1Next);
    renderStoryboardError(err.message || String(err));
  } finally {
    state.isRunning = false;
  }
}

function renderStoryboardError(errorMsg) {
  const container = document.getElementById("storyboardGrid");
  if (!container) return;
  
  container.className = "flex items-center justify-center py-16 w-full";
  container.innerHTML = `
    <div class="text-center space-y-4 max-w-lg bg-[#141B37] border border-red-500/20 p-6 rounded-2xl shadow-xl w-full">
      <div class="text-red-400 text-3xl">⚠️</div>
      <div class="text-sm font-bold text-slate-200">生成分镜失败</div>
      <div class="text-xs text-slate-450 font-mono text-left bg-[#0B0F22] p-3 rounded-lg overflow-auto max-h-40 border border-slate-800 leading-relaxed">${errorMsg}</div>
      <div class="pt-2">
        <button onclick="handleD1Next_ForceRetry()" class="px-6 py-2.5 bg-indigo-650 hover:bg-indigo-550 text-white font-bold rounded-xl shadow-lg transition text-xs tracking-wider cursor-pointer">
          🔄 重新尝试当前步骤
        </button>
      </div>
    </div>
  `;
}

async function handleD1Next_ForceRetry() {
  state.storyboardGrids = null;
  await handleD1Next();
}


function renderStoryboardGrids() {
  const container = document.getElementById("storyboardGrid");
  if (!container) return;
  
  const headerTextEl = container.previousElementSibling ? container.previousElementSibling.querySelector("p") : null;
  if (headerTextEl) {
    headerTextEl.innerHTML = `系统根据旁白句数科学组织了 ${state.storyboardGrids ? state.storyboardGrids.length : 0} 个宫格大图批次。点击任意子分镜格子可对该格进行精雕重绘，修改提示词后点击“打回重画”即可。`;
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
    const batchIndex = grid.batch_index;
    let N = 4;
    if (state.gridMode === "2x2") N = 2;
    else if (state.gridMode === "3x3") N = 3;
    const panelsCount = N * N;
    const batchStart = (batchIndex - 1) * panelsCount;
    
    // We render the cells of the grid:
    let cellsHtml = "";
    for (let i = 0; i < panelsCount; i++) {
      const globalFrameIdx = batchStart + i;
      const frameLabel = "F-" + String(globalFrameIdx + 1).padStart(2, '0');
      
      if (globalFrameIdx < state.storyboards.length) {
        const frame = state.storyboards[globalFrameIdx];
        const isRedrawing = state.runningRedraws[globalFrameIdx];
        const isSelected = state.selectedFrameIndexByBatch[batchIndex] === globalFrameIdx;
        
        let cellStyleHtml = "";
        if (frame && frame.image_url) {
          cellStyleHtml = `background-image: url('${frame.image_url}'); background-size: cover; background-position: center;`;
        } else if (grid.image_url) {
          const r = Math.floor(i / N);
          const c = i % N;
          const pctX = N > 1 ? (c / (N - 1)) * 100 : 0;
          const pctY = N > 1 ? (r / (N - 1)) * 100 : 0;
          cellStyleHtml = `background-image: url('${grid.image_url}'); background-size: ${N * 100}% ${N * 100}%; background-position: ${pctX}% ${pctY}%;`;
        }
        
        const selectedClasses = isSelected ? "ring-2 ring-indigo-500 border-indigo-500 z-10 scale-[1.02]" : "";
        const loadingClasses = isRedrawing ? "" : "hidden";
        
        cellsHtml += `
          <div id="gridCell_${globalFrameIdx}" 
               data-frame-idx="${globalFrameIdx}"
               onclick="selectSubGridCell(${batchIndex}, ${globalFrameIdx})" 
               class="sub-grid-cell relative overflow-hidden cursor-pointer aspect-[16/9] border border-slate-850 hover:border-indigo-500/80 rounded-xl transition-all duration-200 bg-slate-950 group ${selectedClasses}" 
               style="${cellStyleHtml}">
            
            <!-- Frame Label Overlay -->
            <span class="absolute top-1.5 left-1.5 px-1.5 py-0.5 bg-black/80 text-[8px] font-bold rounded text-amber-500 font-mono select-none">${frameLabel}</span>
            
            <!-- Hover Overlay -->
            <div class="absolute inset-0 bg-indigo-500/10 opacity-0 group-hover:opacity-100 transition duration-200"></div>
            
            <!-- Loading Frosted Glass Overlay -->
            <div id="cellOverlay_${globalFrameIdx}" class="loading-overlay absolute inset-0 bg-slate-950/70 backdrop-blur-xs flex flex-col items-center justify-center space-y-1 transition duration-200 ${loadingClasses}">
              <div class="w-4 h-4 border-2 border-slate-700 border-t-indigo-500 rounded-full animate-spin"></div>
              <span class="text-[8px] text-slate-400 font-semibold tracking-wider font-mono">重画中...</span>
            </div>
          </div>
        `;
      } else {
        // Placeholder cells
        cellsHtml += `
          <div class="bg-slate-950/60 border border-slate-900 aspect-[16/9] rounded-xl flex items-center justify-center text-[8px] text-slate-700 font-mono select-none">
            Placeholder
          </div>
        `;
      }
    }
    
    // Now construct the grid container columns class
    let gridColsClass = "grid-cols-4";
    if (N === 2) gridColsClass = "grid-cols-2";
    else if (N === 3) gridColsClass = "grid-cols-3";
    
    // Check if currently selected
    const selectedFrameIdx = state.selectedFrameIndexByBatch[batchIndex];
    let panelTitle = "📝 批次提示词微调控制盘";
    let textareaVal = grid.prompt;
    let buttonHtml = `<span>🔄 打回当前整组宫格重画</span>`;
    let isBtnDisabled = "";
    let returnBtnClass = "hidden";
    let buttonOnClick = `handleRegenBatch(${batchIndex}, this)`;
    let buttonColorClass = "bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 hover:text-rose-200 border border-rose-900/50 hover:border-rose-700/50";
    
    if (selectedFrameIdx !== undefined) {
      const frame = state.storyboards[selectedFrameIdx];
      const frameLabel = "F-" + String(selectedFrameIdx + 1).padStart(2, '0');
      panelTitle = `📝 选中分镜 [${frameLabel}] 提示词精雕`;
      textareaVal = frame ? frame.prompt : "";
      returnBtnClass = "";
      
      const isRedrawing = state.runningRedraws[selectedFrameIdx];
      if (isRedrawing) {
        isBtnDisabled = "disabled";
        buttonHtml = `
          <div class="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
          <span>正在重画中...</span>
        `;
      } else {
        buttonHtml = `<span>🎨 打回单个子分镜 [${frameLabel}] 重画</span>`;
      }
      buttonColorClass = "bg-red-600 hover:bg-red-500 text-white border border-red-700";
      buttonOnClick = `handleRegenSingleCell(${batchIndex}, ${selectedFrameIdx}, this)`;
    }
    
    html += `
      <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-4 transition-all hover:border-indigo-500/50 duration-300 flex flex-col md:flex-row gap-6">
        <!-- Left Side: Image Preview Grid -->
        <div class="w-full md:w-1/2 flex flex-col justify-between space-y-3">
          <div>
            <div class="flex items-center justify-between mb-2">
              <span class="px-2.5 py-1 bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 text-[10px] font-bold rounded-lg font-mono">${grid.range_text}</span>
              <span class="text-[10px] text-slate-500 font-mono">BATCH_${String(grid.batch_index).padStart(3, '0')}</span>
            </div>
            
            <!-- Grid Container -->
            <div id="gridContainer_${batchIndex}" class="grid ${gridColsClass} gap-1.5 aspect-[16/9] w-full bg-slate-950 rounded-xl border border-slate-850 p-1.5 overflow-hidden">
              ${cellsHtml}
            </div>
          </div>
        </div>

        <!-- Right Side: Prompts Editor -->
        <div id="gridControlPanel_${batchIndex}" class="flex-1 flex flex-col space-y-2.5 justify-between">
          <div class="flex items-center justify-between">
            <span class="text-xs font-semibold text-slate-350 panel-title">${panelTitle}</span>
            <div id="returnBtnContainer_${batchIndex}" class="${returnBtnClass}">
              <button onclick="deselectSubGridCell(${batchIndex})" class="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg text-[10px] font-semibold transition-all border border-slate-700 shadow-sm cursor-pointer">
                返回整组修改
              </button>
            </div>
          </div>
          
          <textarea id="gridPromptArea_${batchIndex}" 
                    rows="6" 
                    oninput="handlePromptInput(${batchIndex}, this)"
                    class="w-full flex-1 bg-slate-950 border border-slate-850 focus:border-indigo-500/50 rounded-xl p-3.5 text-[11px] text-slate-355 font-mono leading-relaxed focus:outline-none resize-none scrollbar-thin">${textareaVal}</textarea>
          
          <button id="regenBtn_${batchIndex}" 
                  ${isBtnDisabled}
                  onclick="${buttonOnClick}" 
                  class="w-full py-2.5 ${buttonColorClass} rounded-xl text-xs font-bold transition-all flex items-center justify-center space-x-2 shadow-sm cursor-pointer">
            ${buttonHtml}
          </button>
        </div>
      </div>
    `;
  });
  
  container.innerHTML = html;
}

function selectSubGridCell(batchIndex, globalFrameIdx) {
  state.selectedFrameIndexByBatch[batchIndex] = globalFrameIdx;
  
  // Highlight cell in DOM
  const container = document.getElementById(`gridContainer_${batchIndex}`);
  if (container) {
    const cells = container.querySelectorAll(".sub-grid-cell");
    cells.forEach(cell => {
      const idx = parseInt(cell.getAttribute("data-frame-idx"));
      if (idx === globalFrameIdx) {
        cell.classList.add("ring-2", "ring-indigo-500", "border-indigo-500", "z-10", "scale-[1.02]");
      } else {
        cell.classList.remove("ring-2", "ring-indigo-500", "border-indigo-500", "z-10", "scale-[1.02]");
      }
    });
  }
  
  // Update control panel to single frame mode
  updateBatchControls(batchIndex);
}

function deselectSubGridCell(batchIndex) {
  delete state.selectedFrameIndexByBatch[batchIndex];
  
  // Update cell styles in DOM
  const container = document.getElementById(`gridContainer_${batchIndex}`);
  if (container) {
    const cells = container.querySelectorAll(".sub-grid-cell");
    cells.forEach(cell => {
      cell.classList.remove("ring-2", "ring-indigo-500", "border-indigo-500", "z-10", "scale-[1.02]");
    });
  }
  
  // Restore control panel to batch mode
  updateBatchControls(batchIndex);
}

function handlePromptInput(batchIndex, textarea) {
  const selectedFrameIdx = state.selectedFrameIndexByBatch[batchIndex];
  if (selectedFrameIdx === undefined) {
    // Batch Mode: update grid.prompt in memory
    const grid = state.storyboardGrids.find(g => g.batch_index === batchIndex);
    if (grid) grid.prompt = textarea.value;
  } else {
    // Single Frame Mode: update frame prompt in memory
    const frame = state.storyboards[selectedFrameIdx];
    if (frame) frame.prompt = textarea.value;
  }
}

function updateBatchControls(batchIndex) {
  const selectedFrameIdx = state.selectedFrameIndexByBatch[batchIndex];
  const controlPanel = document.getElementById(`gridControlPanel_${batchIndex}`);
  if (!controlPanel) return;
  
  const titleEl = controlPanel.querySelector(".panel-title");
  const textarea = document.getElementById(`gridPromptArea_${batchIndex}`);
  const actionBtn = document.getElementById(`regenBtn_${batchIndex}`);
  const returnBtnContainer = document.getElementById(`returnBtnContainer_${batchIndex}`);
  
  const grid = state.storyboardGrids.find(g => g.batch_index === batchIndex);
  if (!grid) return;
  
  if (selectedFrameIdx === undefined) {
    // Batch Mode
    if (titleEl) titleEl.innerText = "📝 批次提示词微调控制盘";
    if (textarea) {
      textarea.value = grid.prompt;
      textarea.readOnly = false;
    }
    if (actionBtn) {
      actionBtn.className = "w-full py-2.5 bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 hover:text-rose-200 border border-rose-900/50 hover:border-rose-700/50 rounded-xl text-xs font-bold transition-all flex items-center justify-center space-x-2 shadow-sm cursor-pointer";
      actionBtn.innerHTML = `<span>🔄 打回当前整组宫格重画</span>`;
      actionBtn.disabled = false;
      actionBtn.onclick = function() { handleRegenBatch(batchIndex, this); };
    }
    if (returnBtnContainer) {
      returnBtnContainer.classList.add("hidden");
    }
  } else {
    // Single Frame Mode
    const frame = state.storyboards[selectedFrameIdx];
    const frameLabel = "F-" + String(selectedFrameIdx + 1).padStart(2, '0');
    
    if (titleEl) titleEl.innerText = `📝 选中分镜 [${frameLabel}] 提示词精雕`;
    if (textarea) {
      textarea.value = frame ? frame.prompt : "";
      textarea.readOnly = false;
    }
    if (actionBtn) {
      actionBtn.className = "w-full py-2.5 bg-red-600 hover:bg-red-500 text-white border border-red-700 rounded-xl text-xs font-bold transition-all flex items-center justify-center space-x-2 shadow-sm cursor-pointer";
      
      const isRedrawing = state.runningRedraws[selectedFrameIdx];
      if (isRedrawing) {
        actionBtn.disabled = true;
        actionBtn.innerHTML = `
          <div class="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
          <span>正在重画中...</span>
        `;
      } else {
        actionBtn.disabled = false;
        actionBtn.innerHTML = `<span>🎨 打回单个子分镜 [${frameLabel}] 重画</span>`;
      }
      actionBtn.onclick = function() { handleRegenSingleCell(batchIndex, selectedFrameIdx, this); };
    }
    if (returnBtnContainer) {
      returnBtnContainer.classList.remove("hidden");
      returnBtnContainer.innerHTML = `
        <button onclick="deselectSubGridCell(${batchIndex})" class="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg text-[10px] font-semibold transition-all border border-slate-700 shadow-sm cursor-pointer">
          返回整组修改
        </button>
      `;
    }
  }
}

async function handleRegenSingleCell(batchIndex, globalFrameIdx, btn) {
  const frame = state.storyboards[globalFrameIdx];
  if (!frame) return;
  
  // Set redrawing status
  state.runningRedraws[globalFrameIdx] = true;
  
  // Show loading overlay on cell immediately
  const overlay = document.getElementById(`cellOverlay_${globalFrameIdx}`);
  if (overlay) overlay.classList.remove("hidden");
  
  // Update control panel button (if currently selected)
  updateBatchControls(batchIndex);
  
  showToast(`🎨 正在后台重绘单分镜 F-${String(globalFrameIdx + 1).padStart(2, '0')}...`);
  
  try {
    const res = await pywebview.api.render_single_frame({
      target_id: `frame_${globalFrameIdx + 1}`,
      prompt: frame.prompt
    });
    
    if (res.status === "success") {
      showToast(`✅ 单分镜 F-${String(globalFrameIdx + 1).padStart(2, '0')} 重绘成功！`);
      
      // Update image url with timestamp to bust cache
      const newUrl = res.render_url + (res.render_url.includes('?') ? '&' : '?') + 't=' + Date.now();
      frame.image_url = newUrl;
      
      // Update cell background in DOM in place
      const cell = document.getElementById(`gridCell_${globalFrameIdx}`);
      if (cell) {
        cell.style.backgroundImage = `url('${newUrl}')`;
        cell.style.backgroundSize = 'cover';
        cell.style.backgroundPosition = 'center';
      }
    } else {
      showCustomModal("⚠️ 重绘失败", res.detail || "单分镜重绘失败，请重试！");
    }
  } catch(err) {
    showCustomModal("❌ 出错了", err.message || "请求发送失败！");
  } finally {
    delete state.runningRedraws[globalFrameIdx];
    
    // Hide loading overlay
    const overlay = document.getElementById(`cellOverlay_${globalFrameIdx}`);
    if (overlay) overlay.classList.add("hidden");
    
    // Update control panel button (if currently selected)
    updateBatchControls(batchIndex);
  }
}

function showLargeGridImage(url) {
  if (!url) return;
  const largeImg = document.getElementById("largeGridImg");
  if (largeImg) largeImg.src = url;
  const overlay = document.getElementById("overlayLargeGrid");
  if (overlay) overlay.classList.remove("hidden");
}

function closeLargeGrid() {
  const overlay = document.getElementById("overlayLargeGrid");
  if (overlay) overlay.classList.add("hidden");
  const largeImg = document.getElementById("largeGridImg");
  if (largeImg) largeImg.src = "";
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
      
      // Clear manual redraws for this batch in frontend state
      let N = 4;
      if (state.gridMode === "2x2") N = 2;
      else if (state.gridMode === "3x3") N = 3;
      const panelsCount = N * N;
      const batchStart = (batchIndex - 1) * panelsCount;
      for (let i = 0; i < panelsCount; i++) {
        const globalFrameIdx = batchStart + i;
        if (state.storyboards && state.storyboards[globalFrameIdx]) {
          state.storyboards[globalFrameIdx].image_url = "";
        }
      }
      delete state.selectedFrameIndexByBatch[batchIndex];
      
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
}

// ── 🎞️ E1 分镜单帧细节重画 (支持新旧后悔药) ──
let activeFrameIndex = 0;
let activeE1PreviewMode = "new";

function openE1(index) {
  activeFrameIndex = index;
  activeE1PreviewMode = "new";
  const frm = state.storyboards[index];
  if (!frm) return;
  
  const title = document.getElementById("e1_Title");
  const promptInput = document.getElementById("e1_PromptInput");
  const previewArea = document.getElementById("e1_PreviewArea");

  if (title) title.innerText = `分镜单帧大底片重绘 - [分镜帧 F-0${index+1}] (E1)`;
  if (promptInput) promptInput.value = frm.prompt;
  
  const tabNew = document.getElementById("previewTabE1-new");
  const tabOld = document.getElementById("previewTabE1-old");
  if (tabNew) tabNew.className = "px-2 py-1 bg-indigo-600 text-[10px] text-white rounded font-bold";
  if (tabOld) tabOld.className = "px-2 py-1 text-[10px] text-slate-400 hover:text-slate-200 rounded";

  if (previewArea) {
    previewArea.innerHTML = `<img id="e1_preview_img" src="${frm.image_url}" class="max-w-full max-h-[300px] object-contain rounded-lg shadow-xl" />`;
  }
  
  const frame_id = `frame_0${index+1}`;
  if (!state.frameHistory[frame_id]) {
    state.frameHistory[frame_id] = {
      new_url: frm.image_url,
      old_url: frm.image_url
    };
  }

  // Disable textarea and button if redrawing is in progress
  const isRedrawing = state.runningRedraws[frame_id] === true;
  const rebuildBtn = document.getElementById("rebuildFrameBtn");
  if (promptInput) {
    promptInput.disabled = isRedrawing;
  }
  if (rebuildBtn) {
    rebuildBtn.disabled = isRedrawing;
    if (isRedrawing) {
      rebuildBtn.innerText = "🎨 后台正在重绘中...";
    } else {
      rebuildBtn.innerText = "💡 确定更新并重新画本帧";
    }
  }

  const overlay = document.getElementById("overlayE1");
  if (overlay) overlay.classList.remove("hidden");
}

function switchE1PreviewMode(mode) {
  activeE1PreviewMode = mode;
  const frm = state.storyboards[activeFrameIndex];
  if (!frm) return;
  const frame_id = `frame_0${activeFrameIndex+1}`;
  const hist = state.frameHistory[frame_id];
  if (!hist) return;
  
  const tabNew = document.getElementById("previewTabE1-new");
  const tabOld = document.getElementById("previewTabE1-old");
  const img = document.getElementById("e1_preview_img");

  if (mode === "new") {
    if (tabNew) tabNew.className = "px-2 py-1 bg-indigo-600 text-[10px] text-white rounded font-bold";
    if (tabOld) tabOld.className = "px-2 py-1 text-[10px] text-slate-400 hover:text-slate-200 rounded";
    if (img) img.src = hist.new_url;
  } else {
    if (tabOld) tabOld.className = "px-2 py-1 bg-indigo-600 text-[10px] text-white rounded font-bold";
    if (tabNew) tabNew.className = "px-2 py-1 text-[10px] text-slate-400 hover:text-slate-200 rounded";
    if (img) img.src = hist.old_url;
  }
}

async function rebuildFrameCard() {
  const frm = state.storyboards[activeFrameIndex];
  if (!frm) return;
  
  const frame_id = `frame_0${activeFrameIndex+1}`;
  if (state.runningRedraws[frame_id]) {
    showToast("⚠️ 该分镜正在重绘中，请勿重复操作！");
    return;
  }

  const promptInput = document.getElementById("e1_PromptInput");
  const newPrompt = promptInput ? promptInput.value : "";
  
  // Mark as running redraw
  state.runningRedraws[frame_id] = true;
  
  // Close the modal immediately
  closeE1_Force();
  
  // Put the frame card in local loading state
  const targetIndex = activeFrameIndex;
  const previewImg = document.getElementById(`framePreviewImg${targetIndex}`);
  const originalHtml = previewImg ? previewImg.innerHTML : ""; // Keep original HTML in case of failure
  
  if (previewImg) {
    // Show glassmorphic overlay + loading spinner
    previewImg.style.position = "relative";
    previewImg.innerHTML = `
      ${originalHtml}
      <div class="absolute inset-0 bg-black/60 backdrop-blur-[2px] flex flex-col items-center justify-center text-white z-10">
        <svg class="animate-spin h-6 w-6 text-indigo-400 mb-1" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <span class="text-[9px] font-semibold animate-pulse text-indigo-200">重画中...</span>
      </div>
    `;
  }
  
  // Background asynchronous call
  pywebview.api.render_single_frame({
    target_id: frame_id,
    prompt: newPrompt,
    seed: state.seed,
    style_lock: true
  })
  .then(res => {
    if (res && res.status === "success") {
      state.frameHistory[frame_id].old_url = frm.image_url;
      state.frameHistory[frame_id].new_url = res.render_url;
      
      frm.image_url = res.render_url;
      frm.prompt = newPrompt;
      
      const finalPreviewImg = document.getElementById(`framePreviewImg${targetIndex}`);
      if (finalPreviewImg) {
        finalPreviewImg.innerHTML = `
          <span class="absolute top-2 left-2 px-1.5 py-0.5 bg-black/80 text-[8px] font-bold rounded text-amber-500 font-mono">F-0${targetIndex+1}</span>
          <img src="${res.render_url}" class="w-full h-full object-cover group-hover:scale-105 transition duration-500" />
        `;
      }
      showToast(`✨ 分镜帧 F-0${targetIndex+1} 后台重绘成功！`);
    } else {
      // Restore card visual state
      const finalPreviewImg = document.getElementById(`framePreviewImg${targetIndex}`);
      if (finalPreviewImg) {
        finalPreviewImg.innerHTML = originalHtml;
      }
      showCustomModal("⚠️ 生图失败", `分镜帧 F-0${targetIndex+1} 重画失败，请重试！`);
    }
  })
  .catch(err => {
    // Restore card visual state
    const finalPreviewImg = document.getElementById(`framePreviewImg${targetIndex}`);
    if (finalPreviewImg) {
      finalPreviewImg.innerHTML = originalHtml;
    }
    showCustomModal("⚠️ 接口调用异常", `分镜帧 F-0${targetIndex+1} 重画失败: ` + String(err));
  })
  .finally(() => {
    // Release the redraw lock
    delete state.runningRedraws[frame_id];
  });
}

function closeE1(event) {
  if (event && event.target && event.target.id === "overlayE1") {
    closeE1_Force();
  }
}
function closeE1_Force() {
  const overlay = document.getElementById("overlayE1");
  if (overlay) overlay.classList.add("hidden");
}

// ── 🎥 F 页面全盘多轨物理装配 ──
async function handleSynthesize() {
  navigateTo("F");
  
  const vPlayer = document.getElementById("epicVideoPlayer");
  const vPlaceholder = document.getElementById("videoPlaceholder");
  
  if (vPlayer) vPlayer.classList.add("hidden");
  if (vPlaceholder) vPlaceholder.classList.remove("hidden");

  const speedupCheck = document.getElementById("enableSpeedup");
  const enableSpeedup = speedupCheck ? speedupCheck.checked : true;

  const compileTypeSelect = document.getElementById("compileTypeSelector");
  const compileType = compileTypeSelect ? compileTypeSelect.value : "video";

  try {
    const res = await pywebview.api.synthesize_video({ 
      enable_speedup: enableSpeedup,
      compile_type: compileType
    });
    if (res.status === "success") {
      state.relativeVideoPath = res.relative_path;
      
      if (vPlaceholder) vPlaceholder.classList.add("hidden");
      if (vPlayer) {
        vPlayer.src = res.video_url;
        vPlayer.classList.remove("hidden");
        vPlayer.play();
      }
      
      showToast("🎉 全盘多轨视频物理拼装合成大获成功！请导演欣赏大作！");
    } else {
      showCustomModal("⚠️ 合成失败", "FFmpeg 合成大师运行发生阻碍，请重试！");
    }
  } catch(err) {
    handleApiError(err, handleSynthesize);
  }
}

// ── 💾 另存为与预设极速导出下载 ──
async function downloadEpicVideo() {
  if (!state.relativeVideoPath) {
    showToast("⚠️ 未找到已生成的视频源，请先完成物理合成！");
    return;
  }

  if (typeof pywebview !== "undefined" && pywebview.api) {
    try {
      const defaultFilename = `director_cut_${state.modePath.toLowerCase()}_${Date.now()}.mp4`;
      let savePath = "";
      
      if (state.defaultDownloadFolder) {
        savePath = state.defaultDownloadFolder;
        showToast("💾 正在自动将视频导出至您的预设目录...");
      } else {
        savePath = await pywebview.api.select_save_path(defaultFilename);
        if (!savePath) {
          showToast("⏮️ 已取消保存另存为。");
          return;
        }
        showToast("💾 正在为您将视频文件拷贝至指定位置...");
      }

      const res = await pywebview.api.download_video({
          source_file_relative_path: state.relativeVideoPath,
          target_absolute_path: savePath
        });
      if (res.status === "success") {
        const actualPath = res.actual_path || savePath;
        showCustomModal("🎉 保存成功！", `大导演，您的电影大作已成功下载并导出至：\n\n${actualPath}`);
      } else {
        showCustomModal("⚠️ 保存失败", res.detail || "文件拷贝失败，请核对写入权限后重试！");
      }
    } catch(e) {
      console.error("Download exception:", e);
      showCustomModal("⚠️ 对话框异常", `桌面系统接口交互异常，请重试！\n\n异常详情: ${e.message || e}`);
    }
  } else {
    showToast("⚠️ 请通过 启动调色板.bat 打开桌面 App 使用完整下载功能。");
  }
}

async function presetDownloadFolder() {
  if (typeof pywebview !== "undefined" && pywebview.api) {
    try {
      showToast("⚙️ 请在弹出的文件夹选择框中指定默认下载目录...");
      const folderPath = await pywebview.api.select_download_dir();
      if (folderPath) {
        state.defaultDownloadFolder = folderPath;
        localStorage.setItem("palette_default_download_folder", folderPath);
        updatePresetBtnText();
        showToast("⚙️ 成功预设默认下载目录！");
      } else {
        showToast("⏮️ 已取消选择默认下载目录。");
      }
    } catch(e) {
      console.error("Preset exception:", e);
      showCustomModal("⚠️ 预设接口异常", `桌面系统接口交互异常，请重试！\n\n异常详情: ${e.message || e}`);
    }
  } else {
    showToast("⚠️ 仅可在桌面 App 模式中预设默认下载目录。");
  }
}

function updatePresetBtnText() {
  const btnText = document.getElementById("presetPathBtnText");
  if (btnText) {
    if (state.defaultDownloadFolder) {
      let displayPath = state.defaultDownloadFolder;
      if (displayPath.length > 20) {
        displayPath = displayPath.substring(0, 8) + "..." + displayPath.substring(displayPath.length - 10);
      }
      btnText.innerText = "⚙️ 预设: " + displayPath;
    } else {
      btnText.innerText = "⚙️ 预设默认下载目录";
    }
  }
}

function handleApiError(err, retryCallback) {
  console.error("[Bridge ERROR]:", err);
  showCustomModal(
    "⚠️ 后台处理发生异常",
    `后台脚本执行中出现错误：${err && err.message ? err.message : '未知异常'}。请点击下方按钮重新发起请求（当前输入内容已全部保留）。`,
    "💡 立即重新发起请求",
    true,
    retryCallback
  );
}

function toggleStageCalls(idx) {
  if (!state.backstageExpandedStages) {
    state.backstageExpandedStages = {};
  }
  const el = document.getElementById(`stageCalls_${idx}`);
  const caret = document.getElementById(`caret_${idx}`);
  if (el) {
    const isHidden = el.classList.toggle('hidden');
    if (isHidden) {
      delete state.backstageExpandedStages[idx];
      if (caret) caret.innerText = "▼";
    } else {
      state.backstageExpandedStages[idx] = true;
      if (caret) caret.innerText = "▲";
    }
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
    
    const isExpanded = !!(state.backstageExpandedStages && state.backstageExpandedStages[idx]);
    
    let headerHtml = `
      <div class="flex justify-between items-start cursor-pointer" onclick="toggleStageCalls(${idx})">
        <div class="space-y-1">
          <div class="text-[9px] text-slate-500 font-mono tracking-widest uppercase">STAGE 0${idx+1}</div>
          <div class="text-xs ${titleColor} flex items-center space-x-1.5">
            <span class="text-sm select-none">${icon}</span>
            <span>${stage.name}</span>
          </div>
        </div>
        <div class="flex items-center space-x-2">
          ${statusBadge}
          <span id="caret_${idx}" class="text-[9px] text-slate-600 font-mono select-none">${isExpanded ? '▲' : '▼'}</span>
        </div>
      </div>
    `;
    
    let callsHtml = `<div id="stageCalls_${idx}" class="${isExpanded ? '' : 'hidden'} pt-3 border-t border-slate-850/50 space-y-2.5">`;
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

// ── 🎙️ 旁白音色试听预览控制逻辑 ──
let currentPreviewAudio = null; // 全局试听 Audio 引用

function previewSelectedVoice() {
  const engine = state.presets.tts_engine || "edge";
  const voice = state.presets.voice_role || "";
  const rate = state.presets.voice_rate || "+0%";
  const emotion = state.presets.voice_emotion || "none";
  const pitch = parseInt(state.presets.voice_pitch || 0);
  const volume = parseInt(state.presets.voice_volume || 0);
  const prompt = state.presets.voice_prompt || "";
  
  const btnText = document.getElementById("ttsPreviewText");
  if (!btnText) return;
  
  // 如果当前正在播放，则停止播放并恢复文字
  if (currentPreviewAudio && !currentPreviewAudio.paused) {
    currentPreviewAudio.pause();
    btnText.innerText = "🔊 试听当前设置";
    return;
  }
  
  btnText.innerText = "⏳ 正在合成并加载...";
  
  const payload = { engine, voice, rate, emotion, pitch, volume, prompt };
  
  // 区分是 PyQt 桌面程序 Bridge 还是 API Standalone 模式
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.tts_preview(payload).then(res => {
      handleTtsPreviewResult(res);
    }).catch(err => {
      showToast("试听音频生成失败: " + err);
      btnText.innerText = "🔊 试听当前设置";
    });
  } else {
    // API 模式，发送 HTTP POST 请求
    fetch("http://127.0.0.1:8000/api/story/v1/tts-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
    .then(r => r.json())
    .then(res => {
      handleTtsPreviewResult(res);
    })
    .catch(err => {
      showToast("网络请求失败，请确保 API 服务在后台正常运行");
      btnText.innerText = "🔊 试听当前设置";
    });
  }
}

function handleTtsPreviewResult(res) {
  const btnText = document.getElementById("ttsPreviewText");
  if (!btnText) return;
  
  if (res.status === "success" && res.audio_url) {
    // 实例化并播放音频
    if (currentPreviewAudio) {
      currentPreviewAudio.pause();
    }
    currentPreviewAudio = new Audio(res.audio_url);
    
    currentPreviewAudio.onplay = () => {
      btnText.innerText = "⏸️ 正在播放试听";
    };
    
    currentPreviewAudio.onended = () => {
      btnText.innerText = "🔊 试听当前设置";
    };
    
    currentPreviewAudio.onerror = (e) => {
      showToast("播放音频失败，请重试");
      btnText.innerText = "🔊 试听当前设置";
    };
    
    currentPreviewAudio.play().catch(err => {
      showToast("浏览器限制自动播放，请点击允许或重试");
      btnText.innerText = "🔊 试听当前设置";
    });
  } else {
    showToast(res.detail || "试听生成失败");
    btnText.innerText = "🔊 试听当前设置";
  }
}

// ── 🎙️ 自定义音色管理功能 (保存/重命名/删除) ──

function toggleCustomVoicePanels() {
  const selector = document.getElementById("voiceRoleSelector");
  const savePanel = document.getElementById("customVoiceSavePanel");
  const managePanel = document.getElementById("customVoiceManagePanel");
  const customInput = document.getElementById("customVoiceInput");
  
  if (!selector) return;
  
  const val = selector.value;
  
  // 加载自定义保存的音色列表
  let customVoices = [];
  try {
    const raw = localStorage.getItem("palette_custom_voices");
    if (raw) customVoices = JSON.parse(raw);
  } catch(e) {}
  
  const isSavedCustom = customVoices.some(cv => cv.id === val);
  
  if (val === "custom") {
    if (customInput) customInput.classList.remove("hidden");
    if (savePanel) savePanel.classList.remove("hidden");
    if (managePanel) managePanel.classList.add("hidden");
  } else if (isSavedCustom) {
    if (customInput) customInput.classList.add("hidden");
    if (savePanel) savePanel.classList.add("hidden");
    if (managePanel) managePanel.classList.remove("hidden");
  } else {
    if (savePanel) savePanel.classList.add("hidden");
    if (managePanel) managePanel.classList.add("hidden");
  }
}

function saveCustomVoice() {
  const engine = state.presets.tts_engine || "edge";
  const customInput = document.getElementById("customVoiceInput");
  const nameInput = document.getElementById("customVoiceNameInput");
  
  if (!customInput || !nameInput) return;
  
  const id = customInput.value.trim();
  const name = nameInput.value.trim();
  
  if (!id) {
    showToast("请输入音色标识 ID！");
    return;
  }
  if (!name) {
    showToast("请为该音色取一个名字！");
    return;
  }
  
  let customVoices = [];
  try {
    const raw = localStorage.getItem("palette_custom_voices");
    if (raw) customVoices = JSON.parse(raw);
  } catch(e) {}
  
  const existingIndex = customVoices.findIndex(cv => cv.id === id);
  if (existingIndex !== -1) {
    customVoices[existingIndex].name = name;
    customVoices[existingIndex].engine = engine;
  } else {
    customVoices.push({ id, name, engine });
  }
  
  localStorage.setItem("palette_custom_voices", JSON.stringify(customVoices));
  showToast(`音色「${name}」保存成功！`);
  
  nameInput.value = "";
  
  state.presets.voice_role = id;
  populateVoiceRolesAndRates();
  onVoiceSettingChange();
}

function renameCustomVoice() {
  const selector = document.getElementById("voiceRoleSelector");
  if (!selector) return;
  
  const id = selector.value;
  
  let customVoices = [];
  try {
    const raw = localStorage.getItem("palette_custom_voices");
    if (raw) customVoices = JSON.parse(raw);
  } catch(e) {}
  
  const voice = customVoices.find(cv => cv.id === id);
  if (!voice) return;
  
  const newName = prompt(`请输入音色「${voice.name}」的新名称:`, voice.name);
  if (newName === null) return;
  
  const trimmed = newName.trim();
  if (!trimmed) {
    showToast("音色名称不能为空！");
    return;
  }
  
  voice.name = trimmed;
  localStorage.setItem("palette_custom_voices", JSON.stringify(customVoices));
  showToast("重命名成功！");
  
  populateVoiceRolesAndRates();
}

function deleteCustomVoice() {
  const selector = document.getElementById("voiceRoleSelector");
  if (!selector) return;
  
  const id = selector.value;
  
  let customVoices = [];
  try {
    const raw = localStorage.getItem("palette_custom_voices");
    if (raw) customVoices = JSON.parse(raw);
  } catch(e) {}
  
  const voice = customVoices.find(cv => cv.id === id);
  if (!voice) return;
  
  if (!confirm(`确定要删除自定义音色「${voice.name}」吗？`)) {
    return;
  }
  
  customVoices = customVoices.filter(cv => cv.id !== id);
  localStorage.setItem("palette_custom_voices", JSON.stringify(customVoices));
  showToast("删除成功！");
  
  const engine = state.presets.tts_engine || "edge";
  state.presets.voice_role = (engine === "volc") ? "saturn_zh_female_cancan_tob" : "zh-CN-YunjianNeural";
  
  populateVoiceRolesAndRates();
  onVoiceSettingChange();
}

// ================================================================
// ⚙️ 模型配置面板 — 5卡手风琴版 v3.0
// ================================================================


let _cachedSlots = [];
let _cachedVendors = {};
let _cachedProviders = [];   // list_all_providers()：全部厂商（含自定义/中转站）
let _cachedCombos = {};      // combo_presets：整套 5 槽位方案

const INLINE_ADD_OPT = "__add_provider__";

function _slotRoleModelKey(slotKey) {
  if (slotKey === "llm") return "llm";
  if (slotKey === "vlm" || slotKey === "vlm_analyze") return "vlm";
  return "img";
}

// 厂商目录索引：vendor_key → provider 项（优先全量目录，回退已配厂商）
function _providerByKey(vk) {
  if (!vk) return null;
  for (var i = 0; i < _cachedProviders.length; i++) {
    if (_cachedProviders[i].vendor_key === vk) return _cachedProviders[i];
  }
  return _cachedVendors[vk] || null;
}

async function openModelSettingsModal() {
  if (typeof pywebview === 'undefined' || !pywebview.api) {
    showToast("⚠️ 桌面系统接口未就绪，无法配置模型");
    return;
  }
  try {
    const res = await pywebview.api.get_model_settings();
    if (res.status !== "success") {
      showCustomModal("⚠️ 获取模型配置失败", res.detail || "未知错误");
      return;
    }
    _cachedSlots = res.data.slots || [];
    _cachedVendors = res.data.vendors || {};
    _cachedProviders = res.data.providers || [];
    _cachedCombos = res.data.combo_presets || {};
    _renderComboPresetSelect();
    _renderModelCards();
    document.getElementById("modelSettingsModal").classList.remove("hidden");
  } catch (err) {
    showCustomModal("⚠️ 获取接口异常", err.message || err);
  }
}

function closeModelSettingsModal() {
  const modal = document.getElementById("modelSettingsModal");
  if (modal) modal.classList.add("hidden");
}

function _renderModelCards() {
  const container = document.getElementById("modelCardsContainer");
  if (!container) return;
  container.innerHTML = "";

  _cachedSlots.forEach(slot => {
    const card = document.createElement("div");
    card.className = "bg-[#05070E] border border-slate-800 rounded-xl overflow-hidden transition-all";

    const hasKey = (slot.api_key && slot.api_key.length > 0) || (slot.masked_key && slot.masked_key.length > 0);
    const statusColor = hasKey ? "text-emerald-400" : "text-red-400";
    const statusDot = hasKey ? "🟢" : "🔴";

    card.innerHTML = `
      <div class="flex items-center justify-between px-3 py-2.5 cursor-pointer select-none hover:bg-[#0a0e1a] transition"
           onclick="toggleModelCard('${slot.key}')">
        <div class="flex items-center space-x-2.5 min-w-0">
          <span class="text-sm">${slot.icon}</span>
          <span class="text-[11px] font-semibold text-slate-200 whitespace-nowrap">${slot.name}</span>
          <span id="card_summary_${slot.key}" class="text-[9px] text-slate-500 truncate">${slot.vendor_name} | ${slot.model}</span>
        </div>
        <div class="flex items-center space-x-2 shrink-0 ml-2">
          <span class="${statusColor} text-[9px]">${statusDot}</span>
          <span id="card_arrow_${slot.key}" class="text-[10px] text-slate-600 transition-transform duration-200">▶</span>
        </div>
      </div>
      <div id="card_body_${slot.key}" class="hidden px-3 pb-3 pt-1 border-t border-slate-800/60 space-y-2.5">
        <p class="text-[9px] text-slate-500">${slot.desc}</p>
        <div>
          <label class="text-[9px] text-slate-500 mb-1 block">厂商 / 中转站</label>
          <select id="vendor_sel_${slot.key}" onchange="onCardVendorChange('${slot.key}')"
                  class="w-full bg-[#0a0e1a] border border-slate-750 rounded-lg p-1.5 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none">
          </select>
          <div id="vendor_url_${slot.key}" class="text-[8px] text-slate-600 font-mono mt-0.5 truncate"></div>
        </div>
        <div>
          <label class="text-[9px] text-slate-500 mb-1 block">API Key（该槽位独立）</label>
          <div class="flex gap-1.5">
            <input id="apikey_${slot.key}" type="password" value="${slot.api_key || ''}"
                   class="flex-1 bg-[#0a0e1a] border border-slate-750 rounded-lg p-1.5 text-xs text-slate-200 font-mono focus:border-indigo-500 focus:outline-none">
            <button onclick="event.stopPropagation(); togglePw('apikey_${slot.key}')"
                    class="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-[10px] text-slate-400 rounded-lg border border-slate-750 cursor-pointer">👁️</button>
          </div>
        </div>
        <div>
          <label class="text-[9px] text-slate-500 mb-1 block">模型名</label>
          <input id="model_${slot.key}" type="text" list="hist_${slot.key}" value="${slot.model}"
                 class="w-full bg-[#0a0e1a] border border-slate-750 rounded-lg p-1.5 text-xs text-slate-200 font-mono focus:border-indigo-500 focus:outline-none">
          <datalist id="hist_${slot.key}"></datalist>
        </div>
      </div>
    `;
    container.appendChild(card);
    setTimeout(() => {
      _populateCardVendorSelect(slot.key, slot.vendor_key);
      _rebuildModelDatalist(slot.key);
    }, 0);
  });
}

function _populateCardVendorSelect(slotKey, currentVendorKey) {
  const sel = document.getElementById('vendor_sel_' + slotKey);
  if (!sel) return;
  sel.innerHTML = "";

  const slot = _cachedSlots.find(function (s) { return s.key === slotKey; });
  const memory = (slot && slot.memory) || {};
  const memVendorKeys = Object.keys(memory);

  // 已用厂商集合（用于去重）
  const usedSet = {};

  // 1) 最近使用（该槽位记忆里的厂商）
  if (memVendorKeys.length) {
    const g1 = document.createElement("optgroup");
    g1.label = "最近使用";
    memVendorKeys.forEach(function (vk) {
      const p = _providerByKey(vk);
      const name = (p && p.vendor_name) || vk;
      const opt = document.createElement("option");
      opt.value = vk;
      opt.textContent = "⭐ " + name;
      if (vk === currentVendorKey) opt.selected = true;
      g1.appendChild(opt);
      usedSet[vk] = true;
    });
    sel.appendChild(g1);
  }

  // 2) 全部厂商（启用的，排除已在“最近使用”里的）
  const g2 = document.createElement("optgroup");
  g2.label = "全部厂商";
  _cachedProviders.forEach(function (p) {
    if (p.enabled === false) return;
    if (usedSet[p.vendor_key]) return;
    const opt = document.createElement("option");
    opt.value = p.vendor_key;
    opt.textContent = p.vendor_name + (p.has_key ? "  🟢" : "  🔴");
    if (p.vendor_key === currentVendorKey) opt.selected = true;
    g2.appendChild(opt);
    usedSet[p.vendor_key] = true;
  });
  // 当前绑定的厂商若不在目录里（已禁用/被删），仍补一条以免丢失选择
  if (currentVendorKey && !usedSet[currentVendorKey]) {
    const p = _providerByKey(currentVendorKey);
    const opt = document.createElement("option");
    opt.value = currentVendorKey;
    opt.textContent = ((p && p.vendor_name) || currentVendorKey) + "（当前）";
    opt.selected = true;
    g2.appendChild(opt);
  }
  sel.appendChild(g2);

  // 3) 内联添加
  const optAdd = document.createElement("option");
  optAdd.value = INLINE_ADD_OPT;
  optAdd.textContent = "➕ 添加新厂商 / 中转站…";
  sel.appendChild(optAdd);

  _updateCardVendorUrl(slotKey);
}

function _updateCardVendorUrl(slotKey) {
  const sel = document.getElementById('vendor_sel_' + slotKey);
  const urlEl = document.getElementById('vendor_url_' + slotKey);
  if (!sel || !urlEl) return;
  if (sel.value === INLINE_ADD_OPT) { urlEl.textContent = ""; return; }
  const slot = _cachedSlots.find(function (s) { return s.key === slotKey; });
  const mem = (slot && slot.memory && slot.memory[sel.value]) || {};
  const p = _providerByKey(sel.value);
  urlEl.textContent = mem.base_url || (p ? p.base_url : "") || "";
}

function onCardVendorChange(slotKey) {
  var sel = document.getElementById('vendor_sel_' + slotKey);
  if (!sel) return;

  // 选中“➕ 添加新厂商/中转站”
  if (sel.value === INLINE_ADD_OPT) {
    openInlineProvider(slotKey);
    // 暂时回退到该槽位上次的厂商，等添加成功后再切
    var slotPrev = _cachedSlots.find(function (s) { return s.key === slotKey; });
    sel.value = (slotPrev && slotPrev.vendor_key) || "";
    return;
  }

  _updateCardVendorUrl(slotKey);
  var modelInput = document.getElementById('model_' + slotKey);
  var apiKeyInput = document.getElementById('apikey_' + slotKey);
  var slot = _cachedSlots.find(function (s) { return s.key === slotKey; });
  var vk = sel.value;
  var mem = (slot && slot.memory && slot.memory[vk]) || {};
  var p = _providerByKey(vk) || {};

  // API Key：优先该槽位对该厂商记忆的 key → 厂商目录 key
  if (apiKeyInput) apiKeyInput.value = mem.api_key || p.api_key || '';

  // 模型名：优先该槽位×厂商记忆里最近用的模型 → 厂商默认模型
  var modelKey = _slotRoleModelKey(slotKey);
  var def = (mem.models && mem.models[0]) || (p.default_models && p.default_models[modelKey]) || "";
  if (modelInput) modelInput.value = def;

  _rebuildModelDatalist(slotKey);
}

function _rebuildModelDatalist(slotKey) {
  var dl = document.getElementById('hist_' + slotKey);
  if (!dl) return;
  dl.innerHTML = "";
  var sel = document.getElementById('vendor_sel_' + slotKey);
  var slot = _cachedSlots.find(function (s) { return s.key === slotKey; });
  var vk = sel ? sel.value : (slot && slot.vendor_key);
  if (vk === INLINE_ADD_OPT) return;

  var list = [];
  // 该槽位×该厂商记忆里用过的模型（两级记忆的第二级）
  var mem = (slot && slot.memory && slot.memory[vk]) || {};
  if (mem.models && mem.models.length) list = list.concat(mem.models);
  // 厂商预置变体
  var p = _providerByKey(vk);
  if (p && p.model_variants) {
    p.model_variants.forEach(function (m) { if (list.indexOf(m) === -1) list.push(m); });
  }
  // 该厂商默认模型
  if (p && p.default_models) {
    var modelKey = _slotRoleModelKey(slotKey);
    var d = p.default_models[modelKey];
    if (d && list.indexOf(d) === -1) list.push(d);
  }
  list.forEach(function (m) {
    var opt = document.createElement("option");
    opt.value = m;
    dl.appendChild(opt);
  });
}

function toggleModelCard(slotKey) {
  const body = document.getElementById('card_body_' + slotKey);
  const arrow = document.getElementById('card_arrow_' + slotKey);
  if (!body) return;
  document.querySelectorAll('[id^="card_body_"]').forEach(function(b) {
    if (b !== body) b.classList.add("hidden");
  });
  document.querySelectorAll('[id^="card_arrow_"]').forEach(function(a) {
    if (a !== arrow) a.style.transform = "rotate(0deg)";
  });
  const isHidden = body.classList.contains("hidden");
  body.classList.toggle("hidden");
  arrow.style.transform = isHidden ? "rotate(90deg)" : "rotate(0deg)";
}

function togglePw(inputId) {
  const inp = document.getElementById(inputId);
  if (inp) inp.type = inp.type === "password" ? "text" : "password";
}

// 收集当前 5 槽位 UI → slots 结构
function _collectSlotsFromUI() {
  var slots = {};
  _cachedSlots.forEach(function (s) {
    var vkEl = document.getElementById('vendor_sel_' + s.key);
    var akEl = document.getElementById('apikey_' + s.key);
    var mnEl = document.getElementById('model_' + s.key);
    var buEl = document.getElementById('vendor_url_' + s.key);
    var vk = (vkEl && vkEl.value && vkEl.value !== INLINE_ADD_OPT) ? vkEl.value : s.vendor_key;
    slots[s.key] = {
      vendor_key: vk,
      api_key: (akEl && akEl.value) || "",
      model: (mnEl && mnEl.value) || s.model,
      base_url: (buEl && buEl.textContent) || s.base_url || ""
    };
  });
  return slots;
}

async function saveVendorSettings() {
  if (typeof pywebview === 'undefined' || !pywebview.api) return;
  var slots = _collectSlotsFromUI();
  try {
    const res = await pywebview.api.save_vendor_settings({ slots: slots });
    if (res.status === "success") {
      showToast("🎉 配置已保存并热更新！");
      closeModelSettingsModal();
    } else {
      showCustomModal("⚠️ 保存失败", res.detail || "未知错误");
    }
  } catch (err) {
    showCustomModal("⚠️ 接口调用异常", err.message || err);
  }
}

async function saveModelSettings() { await saveVendorSettings(); }

// ================================================================
// 🎛️ 组合预设（整套 5 槽位方案）
// ================================================================
function _renderComboPresetSelect() {
  const sel = document.getElementById("comboPresetSelect");
  if (!sel) return;
  const prev = sel.value;
  sel.innerHTML = '<option value="">— 选择一个方案 —</option>';
  Object.keys(_cachedCombos).forEach(function (name) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    sel.appendChild(opt);
  });
  if (prev && _cachedCombos[prev]) sel.value = prev;
}

async function applyComboPreset() {
  const sel = document.getElementById("comboPresetSelect");
  const name = sel ? sel.value : "";
  if (!name) { showToast("请先选择一个组合预设"); return; }
  try {
    const res = await pywebview.api.apply_combo_preset(name);
    if (res.status === "success") {
      showToast("✅ 已应用方案「" + name + "」");
      // 重新拉取最新配置刷新卡片
      const r2 = await pywebview.api.get_model_settings();
      if (r2.status === "success") {
        _cachedSlots = r2.data.slots || _cachedSlots;
        _cachedVendors = r2.data.vendors || _cachedVendors;
        _cachedProviders = r2.data.providers || _cachedProviders;
        _cachedCombos = r2.data.combo_presets || _cachedCombos;
        _renderModelCards();
      }
    } else {
      showCustomModal("⚠️ 应用失败", res.detail || "未知错误");
    }
  } catch (err) {
    showCustomModal("⚠️ 接口异常", err.message || err);
  }
}

async function saveComboPreset() {
  const name = (prompt("给这套 5 槽位配置起个名字（例如：省钱套餐 / 高质量套餐）") || "").trim();
  if (!name) return;
  const slots = _collectSlotsFromUI();
  try {
    const res = await pywebview.api.save_combo_preset(name, slots);
    if (res.status === "success") {
      _cachedCombos = (res.data && res.data.combo_presets) || _cachedCombos;
      _renderComboPresetSelect();
      const sel = document.getElementById("comboPresetSelect");
      if (sel) sel.value = name;
      showToast("💾 已保存方案「" + name + "」");
    } else {
      showCustomModal("⚠️ 保存失败", res.detail || "未知错误");
    }
  } catch (err) {
    showCustomModal("⚠️ 接口异常", err.message || err);
  }
}

async function deleteComboPreset() {
  const sel = document.getElementById("comboPresetSelect");
  const name = sel ? sel.value : "";
  if (!name) { showToast("请先选择要删除的方案"); return; }
  showCustomModal("🗑 删除方案", "确定删除组合预设「" + name + "」？", "删除", true, async function () {
    try {
      const res = await pywebview.api.delete_combo_preset(name);
      if (res.status === "success") {
        _cachedCombos = (res.data && res.data.combo_presets) || {};
        _renderComboPresetSelect();
        showToast("已删除方案「" + name + "」");
      } else {
        showCustomModal("⚠️ 删除失败", res.detail || "未知错误");
      }
    } catch (err) {
      showCustomModal("⚠️ 接口异常", err.message || err);
    }
  });
}

// ================================================================
// ➕ 内联添加厂商 / 中转站
// ================================================================
function openInlineProvider(slotKey) {
  document.getElementById("ip_slot_key").value = slotKey || "";
  document.getElementById("ip_name").value = "";
  document.getElementById("ip_base_url").value = "";
  document.getElementById("ip_api_key").value = "";
  document.getElementById("ip_model_variants").value = "";
  document.getElementById("inlineProviderModal").classList.remove("hidden");
}

function closeInlineProvider() {
  document.getElementById("inlineProviderModal").classList.add("hidden");
}

async function submitInlineProvider() {
  const slotKey = document.getElementById("ip_slot_key").value;
  const name = (document.getElementById("ip_name").value || "").trim();
  const baseUrl = (document.getElementById("ip_base_url").value || "").trim();
  const apiKey = (document.getElementById("ip_api_key").value || "").trim();
  const variantsRaw = (document.getElementById("ip_model_variants").value || "").trim();
  if (!name) { showToast("请填写厂商名称"); return; }
  if (!baseUrl) { showToast("请填写 Base URL"); return; }
  const variants = variantsRaw ? variantsRaw.split("\n").map(function (s) { return s.trim(); }).filter(Boolean) : [];

  try {
    const res = await pywebview.api.add_inline_provider({
      vendor_name: name, base_url: baseUrl, api_key: apiKey,
      api_format: "openai_compatible", model_variants: variants
    });
    if (res.status === "success") {
      _cachedProviders = (res.data && res.data.providers) || _cachedProviders;
      const newKey = res.data && res.data.vendor_key;
      closeInlineProvider();
      showToast("➕ 已添加「" + name + "」");
      // 把新厂商选进触发的槽位并刷新
      if (slotKey && newKey) {
        _populateCardVendorSelect(slotKey, newKey);
        const sel = document.getElementById('vendor_sel_' + slotKey);
        if (sel) sel.value = newKey;
        onCardVendorChange(slotKey);
      }
    } else {
      showCustomModal("⚠️ 添加失败", res.detail || "未知错误");
    }
  } catch (err) {
    showCustomModal("⚠️ 接口异常", err.message || err);
  }
}


// ================================================================
// 🏪 供应商管理面板（商业版：客户自配供应商/中转站）
// ================================================================

let _allProviders = [];
let _providerActiveVendors = {};

async function openProviderManager() {
  if (typeof pywebview === 'undefined' || !pywebview.api) {
    showToast("⚠️ 桌面系统接口未就绪");
    return;
  }
  await refreshProviderList();
  cancelProviderEdit();
  document.getElementById("providerManagerModal").classList.remove("hidden");
}

function closeProviderManager() {
  const modal = document.getElementById("providerManagerModal");
  if (modal) modal.classList.add("hidden");
  // 关闭后刷新模型配置卡片，确保新供应商立即可选
  if (typeof openModelSettingsModal === "function") {
    pywebview.api.get_model_settings().then(function(res) {
      if (res && res.status === "success") {
        _cachedSlots = res.data.slots || _cachedSlots;
        _cachedVendors = res.data.vendors || _cachedVendors;
        _cachedProviders = res.data.providers || _cachedProviders;
        _cachedCombos = res.data.combo_presets || _cachedCombos;
        _renderComboPresetSelect();
        _renderModelCards();
      }
    }).catch(function() {});
  }
}

async function refreshProviderList() {
  try {
    const res = await pywebview.api.list_providers();
    if (res.status !== "success") {
      showCustomModal("⚠️ 获取供应商失败", res.detail || "未知错误");
      return;
    }
    _allProviders = res.data.providers || [];
    _providerActiveVendors = res.data.active_vendors || {};
    _renderProviderList();
  } catch (err) {
    showCustomModal("⚠️ 接口异常", err.message || err);
  }
}

function _isProviderInUse(vk) {
  return Object.values(_providerActiveVendors).indexOf(vk) !== -1;
}

function _renderProviderList() {
  const container = document.getElementById("providerListContainer");
  if (!container) return;
  container.innerHTML = "";

  _allProviders.forEach(function(p) {
    const inUse = _isProviderInUse(p.vendor_key);
    const enabled = p.enabled !== false;
    const keyDot = p.has_key ? "🟢" : "🔴";
    const roles = (p.supported_roles || []).join(" / ") || "未配置模型";
    const row = document.createElement("div");
    row.className = "bg-[#05070E] border border-slate-800 rounded-xl px-3 py-2.5 flex items-center justify-between"
      + (enabled ? "" : " opacity-50");
    row.innerHTML =
      '<div class="min-w-0 flex-1">'
      + '<div class="flex items-center gap-2">'
      + '<span class="text-[11px] font-semibold text-slate-200 truncate">' + _esc(p.vendor_name) + '</span>'
      + (p.builtin ? '<span class="text-[8px] px-1.5 py-0.5 rounded-full bg-slate-800 text-slate-400">内置</span>'
                   : '<span class="text-[8px] px-1.5 py-0.5 rounded-full bg-indigo-900/60 text-indigo-300">自定义</span>')
      + (inUse ? '<span class="text-[8px] px-1.5 py-0.5 rounded-full bg-emerald-900/50 text-emerald-300">使用中</span>' : '')
      + '<span class="text-[9px]">' + keyDot + '</span>'
      + '</div>'
      + '<div class="text-[8px] text-slate-600 font-mono truncate mt-0.5">' + _esc(p.base_url || '—') + '</div>'
      + '<div class="text-[8px] text-slate-500 mt-0.5">' + _esc(p.api_format) + ' · ' + _esc(roles) + '</div>'
      + '</div>'
      + '<div class="flex items-center gap-1.5 shrink-0 ml-2">'
      + '<button onclick="startEditProvider(\'' + p.vendor_key + '\')" class="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-[10px] text-slate-300 rounded-lg border border-slate-750 cursor-pointer">编辑</button>'
      + '<button onclick="toggleProviderEnabled(\'' + p.vendor_key + '\',' + (!enabled) + ')" class="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-[10px] rounded-lg border border-slate-750 cursor-pointer ' + (enabled ? 'text-amber-300' : 'text-emerald-300') + '">' + (enabled ? '禁用' : '启用') + '</button>'
      + (p.builtin ? '' : '<button onclick="deleteProvider(\'' + p.vendor_key + '\')" class="px-2 py-1 bg-slate-800 hover:bg-red-900/60 text-[10px] text-red-300 rounded-lg border border-slate-750 cursor-pointer">删除</button>')
      + '</div>';
    container.appendChild(row);
  });
}

function _esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function startAddProvider() {
  _fillProviderForm({ vendor_key: "", vendor_name: "", base_url: "", api_key: "",
    api_format: "openai_compatible", builtin: false,
    default_models: {}, model_variants: [] }, "新增供应商");
}

function startEditProvider(vk) {
  const p = _allProviders.find(function(x) { return x.vendor_key === vk; });
  if (!p) return;
  _fillProviderForm(p, "编辑：" + p.vendor_name);
}

function _fillProviderForm(p, title) {
  document.getElementById("pe_vendor_key").value = p.vendor_key || "";
  document.getElementById("pe_title").textContent = title;
  document.getElementById("pe_name").value = p.vendor_name || "";
  document.getElementById("pe_api_format").value = p.api_format || "openai_compatible";
  document.getElementById("pe_base_url").value = p.base_url || "";
  document.getElementById("pe_api_key").value = p.api_key || "";
  var dm = p.default_models || {};
  document.getElementById("pe_model_llm").value = dm.llm || "";
  document.getElementById("pe_model_vlm").value = dm.vlm || "";
  document.getElementById("pe_model_img").value = dm.img || "";
  document.getElementById("pe_model_variants").value = (p.model_variants || []).join("\n");
  var badge = document.getElementById("pe_builtin_badge");
  var nameInput = document.getElementById("pe_name");
  if (p.builtin) {
    badge.classList.remove("hidden");
    nameInput.setAttribute("disabled", "disabled");
  } else {
    badge.classList.add("hidden");
    nameInput.removeAttribute("disabled");
  }
  var tr = document.getElementById("pe_test_result");
  tr.classList.add("hidden"); tr.textContent = "";
  document.getElementById("providerEditForm").classList.remove("hidden");
}

function cancelProviderEdit() {
  const form = document.getElementById("providerEditForm");
  if (form) form.classList.add("hidden");
}

function _collectProviderForm() {
  var variants = (document.getElementById("pe_model_variants").value || "")
    .split("\n").map(function(s) { return s.trim(); }).filter(function(s) { return s; });
  return {
    vendor_key: document.getElementById("pe_vendor_key").value || "",
    vendor_name: document.getElementById("pe_name").value.trim(),
    api_format: document.getElementById("pe_api_format").value,
    base_url: document.getElementById("pe_base_url").value.trim(),
    api_key: document.getElementById("pe_api_key").value.trim(),
    models: {
      llm: document.getElementById("pe_model_llm").value.trim(),
      vlm: document.getElementById("pe_model_vlm").value.trim(),
      img: document.getElementById("pe_model_img").value.trim()
    },
    model_variants: variants
  };
}

async function submitProviderEdit() {
  var cfg = _collectProviderForm();
  if (!cfg.vendor_name) { showToast("⚠️ 请填写供应商名称"); return; }
  if (!cfg.base_url) { showToast("⚠️ 请填写 Base URL"); return; }
  try {
    const res = await pywebview.api.save_provider(cfg);
    if (res.status === "success") {
      showToast("✅ 供应商已保存");
      _allProviders = res.data.providers || _allProviders;
      _renderProviderList();
      cancelProviderEdit();
    } else {
      showCustomModal("⚠️ 保存失败", res.detail || "未知错误");
    }
  } catch (err) {
    showCustomModal("⚠️ 接口异常", err.message || err);
  }
}

async function deleteProvider(vk) {
  const p = _allProviders.find(function(x) { return x.vendor_key === vk; });
  if (!confirm("确定删除供应商「" + (p ? p.vendor_name : vk) + "」吗？")) return;
  try {
    const res = await pywebview.api.delete_provider(vk);
    if (res.status === "success") {
      showToast("🗑️ 已删除");
      _allProviders = res.data.providers || _allProviders;
      _renderProviderList();
    } else {
      showCustomModal("⚠️ 删除失败", res.detail || "未知错误");
    }
  } catch (err) {
    showCustomModal("⚠️ 接口异常", err.message || err);
  }
}

async function toggleProviderEnabled(vk, enabled) {
  if (!enabled && _isProviderInUse(vk)) {
    showToast("⚠️ 该供应商正在被某个模型位使用，请先切换后再禁用");
    return;
  }
  try {
    const res = await pywebview.api.set_provider_enabled(vk, enabled);
    if (res.status === "success") {
      _allProviders = res.data.providers || _allProviders;
      _renderProviderList();
    } else {
      showCustomModal("⚠️ 操作失败", res.detail || "未知错误");
    }
  } catch (err) {
    showCustomModal("⚠️ 接口异常", err.message || err);
  }
}

async function testProviderConnection() {
  var cfg = _collectProviderForm();
  var tr = document.getElementById("pe_test_result");
  tr.classList.remove("hidden");
  tr.className = "text-[10px] text-slate-400";
  tr.textContent = "⏳ 正在测试连接...";
  try {
    const res = await pywebview.api.test_provider_connection({
      base_url: cfg.base_url, api_key: cfg.api_key,
      api_format: cfg.api_format, model: cfg.models.llm || cfg.models.vlm || cfg.models.img
    });
    if (res.status === "success") {
      tr.className = "text-[10px] text-emerald-400";
      tr.textContent = "✅ " + (res.msg || "连接成功");
    } else {
      tr.className = "text-[10px] text-red-400";
      tr.textContent = "❌ " + (res.detail || "连接失败");
    }
  } catch (err) {
    tr.className = "text-[10px] text-red-400";
    tr.textContent = "❌ " + (err.message || err);
  }
}
