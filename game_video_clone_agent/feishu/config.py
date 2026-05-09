"""
飞书交互系统 · 全局常量配置
集中管理所有硬编码的字符串、状态名、词组、模板等
"""

# ================================================================
# 一、流水线状态常量（唯一数据源，替代散落各处的字符串）
# ================================================================
STATUS = {
    # 基础态
    "IDLE":                         "IDLE",
    "WAITING_TOPIC":                "WAITING_TOPIC",
    # 大纲审批
    "GENERATING_SYNOPSIS":          "GENERATING_SYNOPSIS",
    "WAITING_SYNOPSIS_APPROVAL":    "WAITING_SYNOPSIS_APPROVAL",
    # 定妆审批
    "GENERATING_VISUALS":           "GENERATING_VISUALS",
    "WAITING_CHARACTER_APPROVAL":   "WAITING_CHARACTER_APPROVAL",
    # 分镜审批
    "WAITING_STORYBOARD_APPROVAL":  "WAITING_STORYBOARD_APPROVAL",
    # 生产中
    "STEP1_WRITING":                "STEP1_WRITING",
    "STEP1_READY":                  "STEP1_READY",
    "STEP2_GENERATING":             "STEP2_GENERATING",
    "STEP2_FAILED":                 "STEP2_FAILED",
    "STEP2_SUCCESS":                "STEP2_SUCCESS",
    "STEP3_ASSEMBLING":             "STEP3_ASSEMBLING",
    # 终态
    "COMPLETED":                    "COMPLETED",
    "ERROR":                        "ERROR",
    # 新增：暂停态
    "PAUSED":                       "PAUSED",
}

# ================================================================
# 二、状态 → 人类可读映射
# ================================================================
STATUS_HUMAN = {
    STATUS["IDLE"]:                         "🟢 空闲待机（请让我推荐选题）",
    STATUS["WAITING_TOPIC"]:                "⏳ 等待您选择盲盒题目",
    STATUS["GENERATING_SYNOPSIS"]:          "🧠 正在连线大模型撰写剧情大纲...",
    STATUS["WAITING_SYNOPSIS_APPROVAL"]:    "👀 大纲已发，正在等待您批示（可回复修改意见）",
    STATUS["GENERATING_VISUALS"]:           "🎨 正在绘制三阶段定妆照...",
    STATUS["WAITING_CHARACTER_APPROVAL"]:   "👀 定妆照已发，等待您决定是否重画",
    STATUS["WAITING_STORYBOARD_APPROVAL"]:  "🧩 分镜宫格已发，等待您打回某批或全部通过",
    STATUS["STEP1_WRITING"]:                "✍️ [生产阶段 1/3] 正在规划分镜和视觉脚本...",
    STATUS["STEP1_READY"]:                  "✅ [生产阶段 1/3] 已就绪：主音轨 + 分镜蓝图完成，可执行 Step2 生图",
    STATUS["STEP2_GENERATING"]:             "🖼️ [生产阶段 2/3] 仅容器生图执行中 (耗时较长)...",
    STATUS["STEP2_FAILED"]:                 "❌ [生产阶段 2/3] 生图失败，已阻断进入 Step3（请重跑 Step2）",
    STATUS["STEP2_SUCCESS"]:                "✅ [生产阶段 2/3] 生图通过，等待进入 Step3",
    STATUS["STEP3_ASSEMBLING"]:             "🎬 [生产阶段 3/3] 正在剪辑合并视频大片...",
    STATUS["COMPLETED"]:                    "✅ 视频已交付！",
    STATUS["ERROR"]:                        "❌ 发生崩溃中断！流程已卡死",
    STATUS["PAUSED"]:                       "⏸️ 生产已暂停",
}

# 冲突卡片中使用的简化状态映射（较简短的描述）
STATUS_HUMAN_SHORT = {
    STATUS["GENERATING_SYNOPSIS"]:          "🧠 正在编写大纲",
    STATUS["WAITING_SYNOPSIS_APPROVAL"]:    "👀 等待您审批大纲",
    STATUS["GENERATING_VISUALS"]:           "🎨 正在绘制三阶段定妆照",
    STATUS["WAITING_CHARACTER_APPROVAL"]:   "👀 等待您审批定妆图",
    STATUS["WAITING_STORYBOARD_APPROVAL"]:  "🧩 分镜宫格已发，等待您打回批次或全部通过",
    STATUS["STEP1_WRITING"]:                "✍️ 正在规划分镜",
    STATUS["STEP1_READY"]:                  "✅ Step1 已完成（可开始 Step2）",
    STATUS["STEP2_GENERATING"]:             "🖼️ 正在生成全量原画",
    STATUS["STEP2_FAILED"]:                 "❌ Step2 失败（已阻断进入 Step3）",
    STATUS["STEP2_SUCCESS"]:                "✅ Step2 通过（可进入 Step3）",
    STATUS["STEP3_ASSEMBLING"]:             "🎬 正在剪辑合成",
}

# 状态 → 运维状态卡片颜色
STATUS_CARD_COLOR = {
    STATUS["ERROR"]:    "red",
    STATUS["IDLE"]:     "green",
    STATUS["COMPLETED"]: "green",
    STATUS["WAITING_TOPIC"]: "green",
}

# 需要拦截用户消息的「忙碌/错误」状态（这些状态下不处理普通对话，直接推状态卡）
BUSY_OR_ERROR_STATES = [
    STATUS["GENERATING_SYNOPSIS"],
    STATUS["GENERATING_VISUALS"],
    STATUS["STEP1_WRITING"],
    STATUS["STEP2_GENERATING"],
    STATUS["STEP2_FAILED"],
    STATUS["STEP3_ASSEMBLING"],
    STATUS["ERROR"],
]

# 未完成项目状态（Hub 重启后需要推送「恢复提醒」的状态集合）
UNFINISHED_RESUME_STATUSES = frozenset([
    STATUS["GENERATING_SYNOPSIS"],
    STATUS["WAITING_SYNOPSIS_APPROVAL"],
    STATUS["GENERATING_VISUALS"],
    STATUS["WAITING_CHARACTER_APPROVAL"],
    STATUS["WAITING_STORYBOARD_APPROVAL"],
    STATUS["STEP1_WRITING"],
    STATUS["STEP1_READY"],
    STATUS["STEP2_GENERATING"],
    STATUS["STEP2_FAILED"],
    STATUS["STEP2_SUCCESS"],
    STATUS["STEP3_ASSEMBLING"],
    STATUS["ERROR"],
])

# 生产进行中状态（禁止重复触发生产的状态）
BUSY_PRODUCTION_STATES = [
    STATUS["STEP1_WRITING"],
    STATUS["STEP1_READY"],
    STATUS["STEP2_GENERATING"],
    STATUS["STEP2_FAILED"],
    STATUS["STEP3_ASSEMBLING"],
    STATUS["WAITING_STORYBOARD_APPROVAL"],
]

# ================================================================
# 三、合法状态转移表（当前态 → 允许到达的目标态集合）
# ================================================================
ALLOWED_TRANSITIONS = {
    STATUS["IDLE"]:                     {STATUS["WAITING_TOPIC"], STATUS["GENERATING_SYNOPSIS"], STATUS["WAITING_SYNOPSIS_APPROVAL"]},
    STATUS["WAITING_TOPIC"]:            {STATUS["IDLE"], STATUS["GENERATING_SYNOPSIS"]},
    STATUS["GENERATING_SYNOPSIS"]:      {STATUS["WAITING_SYNOPSIS_APPROVAL"], STATUS["ERROR"], STATUS["IDLE"]},
    STATUS["WAITING_SYNOPSIS_APPROVAL"]:{STATUS["GENERATING_VISUALS"], STATUS["GENERATING_SYNOPSIS"], STATUS["ERROR"], STATUS["IDLE"]},
    STATUS["GENERATING_VISUALS"]:       {STATUS["WAITING_CHARACTER_APPROVAL"], STATUS["ERROR"], STATUS["IDLE"]},
    STATUS["WAITING_CHARACTER_APPROVAL"]:{STATUS["STEP1_WRITING"], STATUS["GENERATING_VISUALS"], STATUS["ERROR"], STATUS["IDLE"]},
    STATUS["WAITING_STORYBOARD_APPROVAL"]:{STATUS["STEP2_GENERATING"], STATUS["STEP3_ASSEMBLING"], STATUS["ERROR"], STATUS["IDLE"]},
    STATUS["STEP1_WRITING"]:            {STATUS["STEP1_READY"], STATUS["ERROR"], STATUS["IDLE"], STATUS["PAUSED"]},
    STATUS["STEP1_READY"]:              {STATUS["STEP2_GENERATING"], STATUS["ERROR"], STATUS["IDLE"]},
    STATUS["STEP2_GENERATING"]:         {STATUS["STEP2_SUCCESS"], STATUS["STEP2_FAILED"], STATUS["WAITING_STORYBOARD_APPROVAL"], STATUS["ERROR"], STATUS["IDLE"], STATUS["PAUSED"]},
    STATUS["STEP2_FAILED"]:             {STATUS["STEP2_GENERATING"], STATUS["ERROR"], STATUS["IDLE"]},
    STATUS["STEP2_SUCCESS"]:            {STATUS["STEP3_ASSEMBLING"], STATUS["ERROR"], STATUS["IDLE"]},
    STATUS["STEP3_ASSEMBLING"]:         {STATUS["COMPLETED"], STATUS["ERROR"], STATUS["IDLE"], STATUS["PAUSED"]},
    STATUS["COMPLETED"]:                {STATUS["IDLE"]},
    STATUS["ERROR"]:                    {STATUS["IDLE"], STATUS["GENERATING_SYNOPSIS"], STATUS["GENERATING_VISUALS"], STATUS["STEP1_WRITING"], STATUS["STEP2_GENERATING"], STATUS["STEP3_ASSEMBLING"]},
    STATUS["PAUSED"]:                   {STATUS["STEP1_WRITING"], STATUS["STEP2_GENERATING"], STATUS["STEP3_ASSEMBLING"], STATUS["ERROR"], STATUS["IDLE"]},
}

# ================================================================
# 四、卡片按钮 Action Type 常量
# ================================================================
ACTION = {
    # 选题与立项
    "SELECT_TOPIC":                 "select_topic",
    "REQUEST_IDEAS":                "request_ideas",
    "REFRESH_TOPICS":               "refresh_topics",
    "CONFIRM_NEW_PROJECT":          "confirm_new_project",
    "RESUME_PROJECT":               "resume_project",
    # 大纲审批
    "APPROVE_SYNOPSIS":             "approve_synopsis",
    "REQUEST_REVISE_SYNOPSIS":      "request_revise_synopsis",
    "SYNOPSIS_DURATION_DELTA":      "synopsis_duration_delta",
    "SYNOPSIS_DURATION_PRESET":     "synopsis_duration_preset",
    # 定妆审批
    "APPROVE_VISUALS":              "approve_visuals",
    "REJECT_VISUALS":               "reject_visuals",
    "REGEN_STAGE":                  "regen_stage",
    "REGEN_ALL_VISUALS_ONLY":       "regen_all_visuals_only",
    "REGEN_SUPPORTING":             "regen_supporting",
    # 分镜审批
    "APPROVE_STORYBOARDS":          "approve_storyboards",
    "REJECT_STORYBOARD_BATCH":      "reject_storyboard_batch",
    # 项目控制
    "CANCEL_PROJECT":               "cancel_project",
    "PAUSE_PROJECT":                "pause_project",
    "RESUME_PRODUCTION":            "resume_production",
    # 运维
    "OPS_STATUS":                   "ops_status",
    "OPS_RETRY_STEP1":              "ops_retry_step1",
    "OPS_RETRY_STEP2":              "ops_retry_step2",
    "OPS_RETRY_STEP3":              "ops_retry_step3",
    "OPS_ABORT_RUN":                "ops_abort_run",
    "RETRY_FAILED_STAGE":           "retry_failed_stage",
    "RETRY_FAILED_STEP":            "retry_failed_step",
    "SKIP_TTS_CONTINUE":            "skip_tts_continue",
    "SKIP_STAGE":                   "skip_stage",
    "RESTART_BACKEND":              "restart_backend",
    # 启动恢复
    "STARTUP_RESUME_DISMISS":       "startup_resume_dismiss",
    # 占位
    "DO_NOTHING":                   "do_nothing",
}

# ================================================================
# 五、文字消息快捷指令词表（绕过 LLM，直接匹配）
# ================================================================

# 审批通过词（用户在审批态说这些词 = 确认通过）
APPROVE_PHRASES = [
    "可以", "行", "妥", "确定", "通过", "准了", "不错", "ok", "OK",
    "下一步", "进行下一步", "开始下一步", "进入下一步", "下一步吧", "进入下一个步骤",
    "继续", "继续吧", "继续进行", "权利",
    "开始生产", "生成吧", "开始吧", "拍吧", "搞起", "搞起来", "就这个吧", "就这样吧",
]

# 审批态下过于模糊的确认词（需二次确认，防止误触发）
AMBIGUOUS_APPROVE_PHRASES = ["好", "可"]

# 大纲审批态下直接跳过的补充快速通道短语
SYNOPSIS_APPROVE_EXTRAS = []

# 定妆审批态补充
CHARACTER_APPROVE_EXTRAS = []

# 分镜审批态补充
STORYBOARD_APPROVE_EXTRAS = ["开始切分", "切分高清", "宫格通过", "分镜通过", "确认宫格", "通过宫格"]

# 取消/终止项目词
CANCEL_PHRASES = ["取消项目", "取消当前项目", "停止项目", "终止项目", "不做了", "停", "取消", "清除项目"]

# 换一批 / 刷新选题词
REFRESH_PHRASES = ["换一批", "刷新", "换个", "再来一批", "重新推荐", "不想要这些", "换一下"]

# 主动要选题词
IDEAS_PHRASES = ["盲盒", "出题", "给我出个主题", "推荐一个", "推荐主题"]

# 帮助/指令词
HELP_PHRASES = ["帮助", "救命", "指令"]

# 状态/进度查询词
STATUS_PHRASES = ["/status", "状态", "进度"]

# 重置/清空词
RESET_PHRASES = ["重置", "清空", "强行重开"]

# 重启词
RESTART_PHRASES = ["重启", "复活"]

# 闲聊探测词（用户在忙碌态发这些，返回状态卡片）
CHITCHAT_PHRASES = ["你是谁", "在吗", "你好", "你什么情况", "什么情况"]

# 忙碌态白名单（这些词即使在 BUSY_OR_ERROR_STATES 下也拦截处理）
INTERCEPT_WHITELIST = [
    "重启", "复活", "重置", "清空", "强行重开",
    "取消项目", "取消当前项目", "停止项目", "终止项目", "不做了", "取消",
    "换一批", "刷新", "换个", "再来一批", "重新推荐", "换一下",
    "帮助", "救命", "指令",
]

# ================================================================
# 六、管线子系统常量
# ================================================================

# 断点续传任务描述映射
OPS_RETRY_JOB_DESC = {
    "step1": "断点续传 step1",
    "step2": "断点续传 step2",
    "step3": "断点续传 step3",
}

def step_num_from_name(step_name: str) -> int:
    return {"step1": 1, "step2": 2, "step3": 3}.get((step_name or "").lower().strip(), 1)

# 成片时长限制（秒）
DURATION_SEC_MIN = 30
DURATION_SEC_MAX = 7200  # 与 story_planner 上限 120 分钟一致

# 定妆阶段别名映射（LLM 输出 → 标准 key）
STAGE_ALIAS = {
    "child":    "child",
    "youth":    "youth",
    "middle":   "middle",
    "old":      "elderly",
    "elderly":  "elderly",
    "all":      "__all__",
}

STAGE_NAMES = {
    "child":    {"name": "幼年期", "btn": "👶 重画幼年"},
    "youth":    {"name": "青年期", "btn": "🧑 重画青年"},
    "middle":   {"name": "中年期", "btn": "👤 重画中年"},
    "elderly":  {"name": "老年期", "btn": "👴 重画老年"},
}
STAGE_ORDER = ["child", "youth", "middle", "elderly"]

# 对话历史最大保留条数
MAX_HISTORY_LEN = 20

# 消息去重锁最大容量
MAX_PROCESSED_MSG_IDS = 2000

# ================================================================
# 七、LLM 对话 System Prompt（按阶段拆分）
# ================================================================

BASE_SYSTEM_PROMPT = """你是视频项目的沟通协调员，帮助用户和后台自动化系统对话。

你绝对不能模拟系统行为、编造进度或编造系统限制。你只负责引导用户决策和理解意图。

【管线知识】1.大纲 -> 2.定妆照 -> 3.剧本与分镜蓝图(Step1) -> 4.分镜宫格预览(Step2-A，人工审核) -> 5.裁切高清(Step2-B) -> 6.视频合成(Step3) 与交付。

【当前环境数据】
- 进行中主题：{topic}
- 流程状态：{status}

{instruction_set}

【铁律禁令 - 必须严格遵守】
1. 严禁虚构系统行为：绝对不能写"正在生成...97%...完成"、"图片已发送"之类的假进度消息。
2. 严禁编造系统限制：绝对不能说"系统暂不支持传图"、"需对接本地渲染终端"等，这些全是错误的。
3. 如果用户问图片/定妆照在哪里，只需说：后台正在处理，完成后会自动推送飞书卡片，无需用户操作。
4. 不要在没有明确意图时输出控制指令。
5. 大纲审批阶段老板说"可以/下一步/继续"=批准当前大纲，不要跳回立项。
回复控制在80字内。"""

SYSTEM_PROMPT_IDLE = """【当前权限：选题与立项】
老板还没有选定要拍的主题，引导他表达创意或选择题目。
1. 老板明确说出了要拍的主题（哪怕是一句描述），直接开机：
   指令模板：[TRIGGER_START: 主题名称, 视频时长分钟] （没提时长默认 1.25）
2. 老板想要换一批建议、不知道拍啥、让你出主意：
   指令模板：[TRIGGER_IDEAS]
⚠️ 注意：如果老板只是在随便聊聊创意，还没说"拍这个"、"就这个"、"开始"等确认词，不要输出任何指令！"""

SYSTEM_PROMPT_SYNOPSIS = """【当前权限：大纲审批】
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

SYSTEM_PROMPT_CHARACTER = """【当前权限：定妆照审批】
系统已向老板发送了主角幼/中/老三阶段定妆照。
1. 老板同意了照片（说"可以"、"不错"、"通过"、"下一步"等确认词）：
   指令模板：[TRIGGER_APPROVE_CHARACTER]
2. 老板不满意，要求重新绘制：
   指令模板：[TRIGGER_REGEN_CHARACTER: child/middle/old/all之中的一个]
   （child=幼年/童年，middle=中年/成年，old=老年，all=全部重画）"""

SYSTEM_PROMPT_STORYBOARD = """【当前权限：分镜宫格审批】
系统已向老板发送了所有批次的 16 宫格分镜预览图（一张卡片包含全部批次）。
1. 老板确认全部无误，可以进入切分高清 → [TRIGGER_APPROVE_STORYBOARDS]
2. 老板指出某批次有问题 → [TRIGGER_REJECT_STORYBOARD: 批次号]
   （例如说"第2张比例不对"、"批次3有问题"、"第1批重画"）"""

# 忙碌/生产中不接对话，返回提示
SYSTEM_PROMPT_BUSY = """【当前权限：只读旁观】
系统正在全力生产中，不接受任何修改指令。你唯一可以说的：
- 告诉老板当前进度（如实汇报状态）
- 安抚老板耐心等待
- 如果老板说要"取消/终止"，输出 [TRIGGER_STOP]
绝对不要编造进度数字或伪造系统状态。"""


def get_system_prompt(status: str, topic: str = "") -> str:
    """根据当前状态返回完整的 system prompt"""
    if status in [STATUS["IDLE"], STATUS["WAITING_TOPIC"], STATUS["COMPLETED"]]:
        instruction = SYSTEM_PROMPT_IDLE
    elif status == STATUS["WAITING_SYNOPSIS_APPROVAL"]:
        instruction = SYSTEM_PROMPT_SYNOPSIS
    elif status == STATUS["WAITING_CHARACTER_APPROVAL"]:
        instruction = SYSTEM_PROMPT_CHARACTER
    elif status == STATUS["WAITING_STORYBOARD_APPROVAL"]:
        instruction = SYSTEM_PROMPT_STORYBOARD
    else:
        instruction = SYSTEM_PROMPT_BUSY

    return BASE_SYSTEM_PROMPT.format(
        topic=topic or "暂无",
        status=status,
        instruction_set=instruction,
    )


# ================================================================
# 八、帮助文本
# ================================================================
HELP_TEXT = (
    "🛠️ **工业级管线远程控制手册**\n\n"
    "1️⃣ **选题阶段**：\n   - `换一批`: 刷新盲盒点子\n   - 任意发送您的创意即可交流\n\n"
    "2️⃣ **审批阶段**：\n   - `可以`: 准了，推进下一步\n   - `不好`: 打回重画/重写\n   - 任意反馈修改意见给大模型导演\n\n"
    "3️⃣ **系统维护**：\n   - `状态`: 查看当前流水线位置\n   - `重启`: 远程复活卡死的进程\n   - `强行重开`: 彻底清空所有任务数据库"
    "\n\n4️⃣ **运维面板命令**：\n"
    "   - `/status`: 查看当前 Run-ID 与素材就绪探针\n"
    "   - `/switch Run_YYYY...`: 切换到历史批次\n"
    "   - `/retry step1`、`/retry step2` 或 `/retry step3`: 对当前批次执行断点续传\n"
    "   - `/resend storyboard` 或 `补发分镜审核卡`: 宫格已在磁盘但飞书未收到审核卡时，仅补推分镜审核卡"
)

# 错误态下兜底提示
ERROR_TIPS = {
    STATUS["WAITING_SYNOPSIS_APPROVAL"]:   "您可以直接发送「可以」推进下一步，或直接说出修改意见。",
    STATUS["WAITING_CHARACTER_APPROVAL"]:  "您可以发送「可以」开始生产，或发送「重画」并说明哪个阶段。",
    STATUS["WAITING_STORYBOARD_APPROVAL"]: "您可以发送「可以」或「开始切分」进入裁切高清与合成，或说「打回第 N 批」重画宫格。",
}

# ================================================================
# 九、卡片视觉常量
# ================================================================
CARD_TEMPLATE = {
    "wide_screen_mode": True,
}

HEADER_TEMPLATES = {
    "turquoise": "turquoise",
    "purple":    "purple",
    "blue":      "blue",
    "orange":    "orange",
    "red":       "red",
    "green":     "green",
}

# ================================================================
# 十、分镜打回批次号正则匹配模式
# ================================================================
STORYBOARD_REJECT_PATTERNS = [
    r"打回第\s*(\d+)\s*(?:批|张)",
    r"第\s*(\d+)\s*(?:批|张)\s*(?:重画|重绘|重新生成|重新画|有问题)",
    r"(?:重画|重绘)\s*第\s*(\d+)\s*(?:批|张)",
]
