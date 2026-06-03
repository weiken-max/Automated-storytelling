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
  relativeVideoPath: "", // 合成视频在 Runs 下的相对路径
  
  // 后画后悔药对比备份
  assetHistory: {}, // {card_id: {new_url, old_url}}
  frameHistory: {}, // {frame_idx: {new_url, old_url}}
};

function performSessionRecovery(res) {
  if (!res) return;
  showToast("🔄 正在从后台读取项目进度并全盘治愈状态树...");
  
  // 1. 恢复基本变量与智能识别频道
  state.modePath = res.mode_path;
  state.seed = res.seed;
  state.extractedEntities = res.entities;
  state.polishEnabled = res.polish_enabled;

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
  if (stateBadge) stateBadge.innerText = `STATUS: SCREEN_${res.stage}`;
  
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
  if (img) img.value = presets.image || DEFAULT_PRESETS.image;
  if (pol) pol.value = presets.polish || DEFAULT_PRESETS.polish;
  if (voi) voi.value = presets.voiceover || DEFAULT_PRESETS.voiceover;
  if (out) out.value = presets.outline || DEFAULT_PRESETS.outline;
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
        addCustomAssetRow(ast.label, ast.type);
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
  const hasCustomPresets = outline || image || voiceover || polish || storyboard;
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
      assets_config.push({ label: l, type: select.value });
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
        state.channels[idx].presets = hasCustomPresets ? { outline, image, voiceover, polish, storyboard } : null;
      } else {
        state.channels[idx].presets = hasCustomPresets ? { outline, image, voiceover, polish, storyboard } : null;
      }
    }
    showToast(`✅ 频道「${name}」已更新！`);
  } else {
    const newId = "ch_custom_" + Date.now();
    state.channels.push({ id: newId, channelType, name, emoji, color, locked: false,
      assets_config,
      presets: hasCustomPresets ? { outline, image, voiceover, polish, storyboard } : null
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

function addCustomAssetRow(label = "", type = "character") {
  const container = document.getElementById("customAssetsList");
  if (!container) return;
  if (container.children.length >= 6) {
    showToast("⚠️ 最多支持配置 6 张卡片！");
    return;
  }
  const div = document.createElement("div");
  div.className = "flex items-center gap-2 bg-[#020408] border border-slate-900/60 rounded-xl p-2";
  div.innerHTML = `
    <input type="text" placeholder="卡片名称 (如: 主角)" class="flex-1 bg-[#05070E] border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none" value="${escapeHtml(label)}">
    <select class="bg-[#05070E] border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:border-indigo-500 focus:outline-none">
      <option value="character" ${type === 'character' ? 'selected' : ''}>👤 角色</option>
      <option value="scene" ${type === 'scene' ? 'selected' : ''}>🌅 场景</option>
      <option value="prop" ${type === 'prop' ? 'selected' : ''}>🎒 道具</option>
    </select>
    <button type="button" onclick="this.parentElement.remove()" class="p-1.5 text-slate-500 hover:text-red-400 transition-all cursor-pointer">
      ✕
    </button>
  `;
  container.appendChild(div);
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
        <div class="flex justify-between items-center">
          <span class="text-xs font-bold text-slate-100" id="cardName${idx}">${escapeHtml(ast.name)}</span>
          <span class="px-1.5 py-0.5 bg-indigo-900/40 text-[9px] font-bold text-indigo-300 rounded font-mono">CAST ID: 0${idx + 1}</span>
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

function switchPromptCategory(cat) {
  const cats = ["image", "polish", "voiceover", "outline"];
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
        system_prompt: state.presets.voiceover
      },
      render_flow: {
        style_presets: state.presets.image,
        seed: state.seed
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
          voiceover_flow: { system_prompt: state.presets.voiceover },
          render_flow: { 
            style_presets: state.presets.image, 
            seed: state.seed,
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
        seed: state.seed
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
  const promptInput = document.getElementById("d1_1_PromptInput");
  const newPrompt = promptInput ? promptInput.value : "";
  
  const rebuildBtn = document.getElementById("rebuildAssetBtn");
  if (rebuildBtn) {
    rebuildBtn.disabled = true;
    rebuildBtn.innerText = "🎨 生图引擎重绘中...";
  }

  try {
    const res = await pywebview.api.render_single_frame({
        target_id: ast.id,
        prompt: newPrompt,
        seed: state.seed,
        style_lock: true
      });
    if (res.status === "success") {
      state.assetHistory[ast.id].old_url = ast.image_url;
      state.assetHistory[ast.id].new_url = res.render_url;
      
      ast.image_url = res.render_url;
      ast.prompt = newPrompt;
      
      const prmLabel = document.getElementById(`cardPrompt${activeCardIndex}`);
      if (prmLabel) prmLabel.innerText = newPrompt;
      const imgCont = document.getElementById(`cardImg${activeCardIndex}`);
      if (imgCont) imgCont.innerHTML = `<img src="${res.render_url}" class="w-full h-full object-cover group-hover:scale-105 transition duration-500" />`;
      
      switchD1_1PreviewMode("new");
      showToast("✨ 定妆卡片局部重绘成功！");
    } else {
      showCustomModal("⚠️ 生图失败", "重绘失败，请重试！");
    }
  } catch(err) {
    handleApiError(err, rebuildAssetCard);
  } finally {
    if (rebuildBtn) {
      rebuildBtn.disabled = false;
      rebuildBtn.innerText = "💡 确定更新并进行局部重画";
    }
  }
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
        <div class="text-slate-655 text-3xl">📭</div>
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
          <textarea id="gridPromptArea_${grid.batch_index}" rows="8" class="w-full flex-1 bg-slate-950 border border-slate-850 focus:border-indigo-500/50 rounded-xl p-3.5 text-[11px] text-slate-355 font-mono leading-relaxed focus:outline-none resize-none scrollbar-thin">${grid.prompt}</textarea>
        </div>
      </div>
    `;
  });
  
  container.innerHTML = html;
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
      showToast(`` + `✅ 第 ${batchIndex} 批次分镜重画绘制成功！`);
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
  const promptInput = document.getElementById("e1_PromptInput");
  const newPrompt = promptInput ? promptInput.value : "";
  const frame_id = `frame_0${activeFrameIndex+1}`;

  const rebuildBtn = document.getElementById("rebuildFrameBtn");
  if (rebuildBtn) {
    rebuildBtn.disabled = true;
    rebuildBtn.innerText = "🎨 生图引擎单帧重绘中...";
  }

  try {
    const res = await pywebview.api.render_single_frame({
        target_id: frame_id,
        prompt: newPrompt,
        seed: state.seed,
        style_lock: true
      });
    if (res.status === "success") {
      state.frameHistory[frame_id].old_url = frm.image_url;
      state.frameHistory[frame_id].new_url = res.render_url;
      
      frm.image_url = res.render_url;
      frm.prompt = newPrompt;
      
      const previewImg = document.getElementById(`framePreviewImg${activeFrameIndex}`);
      if (previewImg) {
        previewImg.innerHTML = `
          <span class="absolute top-2 left-2 px-1.5 py-0.5 bg-black/80 text-[8px] font-bold rounded text-amber-500 font-mono">F-0${activeFrameIndex+1}</span>
          <img src="${res.render_url}" class="w-full h-full object-cover group-hover:scale-105 transition duration-500" />
        `;
      }
      
      switchE1PreviewMode("new");
      showToast("✨ 分镜单帧重画渲染完成！");
    } else {
      showCustomModal("⚠️ 生图失败", "重绘单帧失败，请重试！");
    }
  } catch(err) {
    handleApiError(err, rebuildFrameCard);
  } finally {
    if (rebuildBtn) {
      rebuildBtn.disabled = false;
      rebuildBtn.innerText = "💡 确定更新并重新画本帧";
    }
  }
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

  try {
    const res = await pywebview.api.synthesize_video();
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
