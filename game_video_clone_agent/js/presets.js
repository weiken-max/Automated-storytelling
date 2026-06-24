// ── 🎨 全局出厂默认提示词（所有频道的 fallback） ──
const DEFAULT_PRESETS = {
  image: "High-quality 2D vector cartoon, bold black outlines, vibrant flat colors with soft cel-shading. Style inspired by Cyanide and Happiness but with professional lighting and detailed illustrated backgrounds. Character proportions: stick figure limbs, round bean heads.",
  polish: "你是一位专业的资深编剧与剧本医生。\n任务：请阅读用户提供的原始素材（梗概、片段或小说节选均可），在【完全保留用户原始创意、情节走向和核心设定】的前提下，进行专业润色。\n\n输出：仅 JSON：\n{\"synopsis_acts\":[6个字符串],\"synopsis\":\"全文\",\"short_title\":\"12字内标题\",\"era\":\"时代背景\",\"identity\":\"主角身份\",\"industry_rules\":[\"规则\"]}",
  voiceover: "你是一个极其冷峻、犀利的短视频旁白文案大师。\n任务：按用户指示写出一段沉浸式旁白。\n全程使用「你」，极简冷峻。禁止分镜标签。只输出旁白正文。",
  outline: "你是一个极其冷酷的现实主义编剧与行业规则解剖师。\n任务：根据用户给出的主题，设计一个充满利益算计、阶层跃迁与人性异化的第二人称人生副本梗概。\n分幕结构硬性：输出 synopsis_acts 数组，长度恰好为 6。总字数不超过 1500。\n输出 JSON：\n{\"synopsis_acts\":[6个字符串],\"synopsis\":\"全文\",\"era\":\"时代\",\"identity\":\"主角终极身份\",\"industry_rules\":[\"潜规则\"]}",
  storyboard: "【画风锚点】\nCyanide and Happiness comic style, 2D vector / flat graphic cartoon, bold black outlines, vivid flat color fills, pure 2D, no photoreal skin texture, no 3D/CGI. 允许卡通级光向（key direction, warm/cool, simple hard-edge shadow shapes），禁止电影级体积光与写实 subsurface skin。\n\n【分镜表现规则】\n★ 动态表情与肢体（核心要求：打破参考图的呆滞感！）：必须深度解析当前分镜的故事情节，强制赋予角色强烈且符合情境的情绪反应。\n1. 必须采用【核心情绪词 + 氰化物式五官拆解】组合。例如不要只写 mouth line，必须写：terrified expression, sharply angled frowning eyebrows, wide dilated dot eyes, screaming jagged mouth shape.\n2. 明确指令：绝不允许角色保持中立或被参考图的默认表情带偏（DO NOT copy the neutral expression from reference）。\n3. 肢体辅助：情绪必须配合夸张的肢体动作（如 recoiling in horror, pointing aggressively, slumping in defeat）。\n4. 脸部特写：当情绪是当前帧重点时，明确写明 close-up on explicit facial expression。",
  cast_prompt: "[character]\nA cute cartoon stickman style representation of {entity}. Flat colors, strong outline, white background.\n\n[scene]\nA flat 2D vector style minimalist cartoon background scenery depicting {entity}. Flat shades, no character.\n\n[prop]\nA flat 2D vector icon cartoon object depicting {entity}. Primitive shape, flat color fill, white background.",
  tts_engine: "edge",
  voice_role: "zh-CN-YunjianNeural",
  voice_rate: "+0%",
  voice_emotion: "none",
  voice_pitch: 0,
  voice_volume: 0,
  voice_prompt: ""
};

// ── 🎨 全局出厂原厂频道（locked=true 不可删除） ──
const DEFAULT_CHANNELS = [
  {
    id: "ch_drama",
    channelType: "drama",
    name: "剧情故事",
    emoji: "🎭",
    color: "#EF4444",
    locked: true,
    presets: null // null 表示使用 DEFAULT_PRESETS
  },
  {
    id: "ch_science",
    channelType: "science",
    name: "硬核科普",
    emoji: "🔬",
    color: "#F59E0B",
    locked: true,
    presets: {
      image: DEFAULT_PRESETS.image,
      polish: DEFAULT_PRESETS.polish,
      voiceover: DEFAULT_PRESETS.voiceover,
      outline: "你是一名科普内容策划大师，专注于将晦涩的科学原理转化为令人上瘾的短视频内容。\n任务：根据用户给出的科普主题，设计一个充满震撼数据、反直觉结论与科学悬疑感的纪录片式梗概。\n\n要求：\n1. 开篇必须有一个颠覆常识的惊人事实或数字。\n2. 按「现象→原理→实验证据→颠覆性结论」逻辑链展开。\n3. 必须包含至少3个具体、可视化的数字。\n4. 分幕结构（硬性）：synopsis_acts 数组，长度恰好为 6。总字数不超过 1500。\n\n输出 JSON（键名固定）：\n{\"synopsis_acts\":[6个字符串],\"synopsis\":\"全文\",\"era\":\"科学背景\",\"identity\":\"主角\",\"industry_rules\":[\"科学规律\"]}",
      storyboard: "【画风锚点】\nFlat 2D vector infographic sci-tech illustration style, minimalist blueprint diagram, thin clean black outlines, high-contrast digital colors, glowing neon accents, scientific cross-section diagrams, data visualization panels. No 3D rendering, no photoreal textures.\n\n【分镜表现规则】\n★ 科普展示规范（优先信息清晰度与视觉隐喻）：\n1. 优先使用科学视觉隐喻：用可视化比喻表现抽象概念（如：芯片→精密数字城市，引力→时空网格弯曲，神经元→发光网络）。\n2. 镜头允许概念性大跳切，不强制空间连贯（如从微观细胞→宏观人体→地球）。\n3. 尽量减少拟人化情绪表达，以信息清晰度和视觉冲击力为第一优先。\n4. 数据与文字标注：当旁白含具体数字或术语时，在画面描述中明确要求将其可视化为标注图、对比图或比例示意图。"
    }
  }
];

// 从 localStorage 恢复频道列表（带安全迁移逻辑）
function loadChannelsFromStorage() {
  try {
    const raw = localStorage.getItem("palette_channels_v3");
    if (!raw) return JSON.parse(JSON.stringify(DEFAULT_CHANNELS));
    const parsed = JSON.parse(raw);
    // 安全守卫：确保原厂频道始终存在
    DEFAULT_CHANNELS.forEach(dc => {
      if (!parsed.find(c => c.id === dc.id)) parsed.unshift(dc);
    });
    // 迁移守卫：为旧版本没有 channelType 字段的频道补充默认值
    parsed.forEach(ch => {
      if (!ch.channelType) {
        ch.channelType = (ch.id === "ch_drama") ? "drama" : "science";
      }
    });
    return parsed;
  } catch(e) {
    return JSON.parse(JSON.stringify(DEFAULT_CHANNELS));
  }
}

// 从后台的物理 JSON 备份中异步恢复频道列表（自愈双保险，防止 localStorage 易失）
async function loadChannelsFromBackend() {
  if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.get_channels) {
    try {
      const res = await pywebview.api.get_channels();
      if (res.status === "success" && res.channels && res.channels.length > 0) {
        const parsed = res.channels;
        // 安全守卫：确保出厂频道始终存在
        DEFAULT_CHANNELS.forEach(dc => {
          if (!parsed.find(c => c.id === dc.id)) parsed.unshift(dc);
        });
        // 迁移守卫：补充 channelType
        parsed.forEach(ch => {
          if (!ch.channelType) {
            ch.channelType = (ch.id === "ch_drama") ? "drama" : "science";
          }
        });
        state.channels = parsed;
        
        // 同步当前激活频道的 presets 内存缓存
        const activeCh = state.channels.find(c => c.id === state.activeChannelId) || state.channels[0];
        if (activeCh) {
          state.activeChannelId = activeCh.id;
          state.presets = getChannelPresets(activeCh);
        }
        
        // 重新刷新主网格渲染
        renderChannelGrid();
        updateJsonPayloadViewer();
        console.log('[Bridge] 成功由物理硬盘 JSON 恢复持久化频道与提示词：', state.channels.length, '个。');
      }
    } catch(err) {
      console.error('[Bridge] 从本地硬盘读取频道备份失败:', err);
    }
  }
}

// 获取频道实际使用的 presets（null 时 fallback 到 DEFAULT_PRESETS）
function getChannelPresets(channel) {
  if (!channel.presets) return { ...DEFAULT_PRESETS };
  return {
    image:      channel.presets.image      || DEFAULT_PRESETS.image,
    polish:     channel.presets.polish     || DEFAULT_PRESETS.polish,
    voiceover:  channel.presets.voiceover  || DEFAULT_PRESETS.voiceover,
    outline:    channel.presets.outline    || DEFAULT_PRESETS.outline,
    storyboard: channel.presets.storyboard || DEFAULT_PRESETS.storyboard,
    cast_prompt: channel.presets.cast_prompt || DEFAULT_PRESETS.cast_prompt,
    tts_engine: channel.presets.tts_engine || DEFAULT_PRESETS.tts_engine,
    voice_role: channel.presets.voice_role || DEFAULT_PRESETS.voice_role,
    voice_rate: channel.presets.voice_rate || DEFAULT_PRESETS.voice_rate,
    voice_emotion: channel.presets.voice_emotion || DEFAULT_PRESETS.voice_emotion,
    voice_pitch: channel.presets.voice_pitch !== undefined ? channel.presets.voice_pitch : DEFAULT_PRESETS.voice_pitch,
    voice_volume: channel.presets.voice_volume !== undefined ? channel.presets.voice_volume : DEFAULT_PRESETS.voice_volume,
    voice_prompt: channel.presets.voice_prompt !== undefined ? channel.presets.voice_prompt : DEFAULT_PRESETS.voice_prompt
  };
}

// ── 💾 频道持久化存储 ──
function saveChannelsToStorage() {
  localStorage.setItem("palette_channels_v3", JSON.stringify(state.channels));
  // 异步同步到后台（双轨备份，失败不影响前端）
  if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.save_channels) {
    pywebview.api.save_channels(state.channels).catch(() => {});
  }
}
