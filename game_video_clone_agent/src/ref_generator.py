"""
🎭 角色定妆器 (src/ref_generator.py) — v4.0 梗概驱动 Cast 版
==========================================================
- 以 temp_synopsis.json 整份 JSON 为唯一叙事输入，一次性 LLM 规划：主角阶段 + 至多 3 名配角 + 各张三视图英文 prompt。
- 全剧需定妆角色总数 ≤ 4（1 主角 + ≤3 配角）。
- 回写 full_story：cast_registry、physical_char_anchors、ref_display_slots、detected_life_stages。
"""

import asyncio
import json
import re
import shutil
import sys
from pathlib import Path

from openai import OpenAI

# ── Windows GBK 终端编码修复 ──
if hasattr(sys.stdout, "buffer"):
    from io import TextIOWrapper

    sys.stdout = TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 确保能找到 src 目录下的配置 ──
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(BASE_DIR / "src") not in sys.path:
    sys.path.insert(0, str(BASE_DIR / "src"))

import src.style_config as config
from src.image_engine import generate_image
from src.project_vault import backup as vault_backup
from src.run_context import get_paths

SCRIPT_TEMP_SYNOPSIS = config.SCRIPT_DIR / "temp_synopsis.json"
LEGACY_FEISHU_TEMP_SYNOPSIS = BASE_DIR / "feishu" / "temp_synopsis.json"

ALLOWED_STAGES = frozenset({"child", "youth", "middle", "elderly"})
MAX_SUPPORTING = 3
MAX_REF_CHARACTERS = 4

SUPPORTING_REGEN_SYSTEM = """You write ONE JSON object for a single SUPPORTING character reference sheet (not the protagonist).
Style: Cyanide and Happiness comic — round bean head, dot eyes, stick-figure limbs, bold black outlines, flat 2D colors.
Must include: character design sheet, triple view front side back, full body, pure white background, no environment/props.
english_prompt: 80–120 English words.
anchor_description: one short Chinese phrase (20–40 chars) for human readers.

Output ONLY: {"english_prompt":"...","anchor_description":"..."}"""


def llm_regen_supporting_prompt(
    topic: str, synopsis_payload: dict, role_id: str, display_name_en: str
) -> dict | None:
    client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL.rstrip("/"))
    user = json.dumps(
        {
            "topic": topic,
            "synopsis_package": synopsis_payload,
            "role_id": role_id,
            "display_name_en": display_name_en,
        },
        ensure_ascii=False,
    )
    try:
        response = client.chat.completions.create(
            model=config.MODEL_LLM,
            messages=[
                {"role": "system", "content": SUPPORTING_REGEN_SYSTEM},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.45,
            max_tokens=2048,
        )
        raw = (response.choices[0].message.content or "").strip()
        data = json.loads(raw)
        ep = str(data.get("english_prompt") or "").strip()
        ad = str(data.get("anchor_description") or "").strip()
        if len(ep) < 40:
            return None
        return {"english_prompt": ep, "anchor_description": ad or f"配角{display_name_en}"}
    except Exception as e:
        print(f"  ⚠️ [Supporting regen] LLM 失败: {e}")
        return None


CAST_PLAN_SYSTEM = """You are a casting and character-sheet planner for a short video pipeline.

You will receive one JSON object: the story synopsis package (topic fields + synopsis text). No other narrative will be provided.

HARD RULES:
1. Total distinct characters that need a face-locking reference sheet MUST be at most 4: exactly ONE protagonist + at most THREE supporting characters.
2. protagonist.stages: choose only from ["child","youth","middle","elderly"], based on life span that actually appears in the story. Do NOT output a stage that the story does not need.
3. Each supporting role must have role_id: lowercase snake_case ASCII (letters, digits, underscores only), e.g. elder_patriarch, sheriff_kane.
4. display_name_en: short English name or epithet for on-screen prompts (e.g. Jack, Elder, Sheriff).
5. Every english_prompt MUST be usable as a character design sheet prompt: Cyanide and Happiness style, round bean head, dot eyes, stick-figure limbs, bold black outlines, flat 2D colors, triple view front side back, full body, pure white background, no props/environment. About 80–120 English words. Also include anchor_description: one short Chinese phrase (20–40 chars) for humans.
6. stage_prompts must contain one entry per stage listed in protagonist.stages with matching keys.
7. Omit supporting characters who barely appear or do not need a consistent face.

Output ONE JSON object only:
{
  "protagonist": {
    "display_name_en": "...",
    "stages": ["youth", "middle"],
    "stage_prompts": {
      "youth": {"english_prompt": "...", "anchor_description": "..."},
      "middle": {"english_prompt": "...", "anchor_description": "..."}
    }
  },
  "supporting": [
    {
      "role_id": "elder_patriarch",
      "display_name_en": "Elder",
      "english_prompt": "...",
      "anchor_description": "..."
    }
  ]
}
"""


def _load_synopsis_dict() -> dict | None:
    for p in (SCRIPT_TEMP_SYNOPSIS, LEGACY_FEISHU_TEMP_SYNOPSIS):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  ⚠️ 读取梗概失败 {p}: {e}")
    return None


def _normalize_role_id(raw: str) -> str:
    s = (raw or "").strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "supporting_extra"


def _validate_and_trim_cast(plan: dict) -> dict | None:
    if not isinstance(plan, dict):
        return None
    pro = plan.get("protagonist")
    if not isinstance(pro, dict):
        return None
    stages = pro.get("stages") or ["middle"]
    if not isinstance(stages, list):
        stages = ["middle"]
    stages = [s for s in stages if s in ALLOWED_STAGES]
    if not stages:
        stages = ["middle"]
    # de-dupe preserve order
    seen = set()
    ordered_stages = []
    for s in stages:
        if s not in seen:
            seen.add(s)
            ordered_stages.append(s)
    pro["stages"] = ordered_stages

    sprompts = pro.get("stage_prompts") or {}
    if not isinstance(sprompts, dict):
        sprompts = {}
    for st in ordered_stages:
        if st not in sprompts or not isinstance(sprompts.get(st), dict):
            sprompts[st] = {
                "english_prompt": f"Cyanide and Happiness style, flat 2D, bean head, dot eyes, stick limbs, bold outlines, "
                f"triple view front side back, full body, white background, protagonist at {st} life stage.",
                "anchor_description": f"主角{st}阶段立绘",
            }
        else:
            ep = str(sprompts[st].get("english_prompt") or "").strip()
            if len(ep) < 40:
                sprompts[st]["english_prompt"] = (
                    f"Cyanide and Happiness comic style, flat illustration, bean head, dot eyes, stick-figure limbs, "
                    f"bold black outlines, character design sheet, triple view front side back, full body, white background, "
                    f"protagonist life stage {st}."
                )
    pro["stage_prompts"] = sprompts

    name_en = str(pro.get("display_name_en") or "Protagonist").strip() or "Protagonist"
    pro["display_name_en"] = name_en
    pro["role_id"] = "protagonist"

    sup_list = plan.get("supporting")
    if not isinstance(sup_list, list):
        sup_list = []
    cleaned = []
    used_ids = set()
    for item in sup_list[:MAX_SUPPORTING]:
        if not isinstance(item, dict):
            continue
        rid = _normalize_role_id(item.get("role_id"))
        if rid in used_ids:
            rid = f"{rid}_{len(used_ids)}"
        used_ids.add(rid)
        dn = str(item.get("display_name_en") or rid).strip() or rid
        ep = str(item.get("english_prompt") or "").strip()
        if len(ep) < 40:
            ep = (
                f"Cyanide and Happiness comic style, flat 2D, bean head, dot eyes, stick limbs, bold outlines, "
                f"character design sheet, triple view front side back, full body, white background, supporting character {dn}."
            )
        cleaned.append(
            {
                "role_id": rid,
                "display_name_en": dn,
                "english_prompt": ep,
                "anchor_description": str(item.get("anchor_description") or f"配角{dn}立绘").strip() or f"配角{dn}",
            }
        )
    plan["supporting"] = cleaned

    if 1 + len(cleaned) > MAX_REF_CHARACTERS:
        plan["supporting"] = cleaned[: max(0, MAX_REF_CHARACTERS - 1)]
    return plan


def llm_plan_cast_from_synopsis(topic: str, synopsis_payload: dict) -> dict | None:
    print(f"  🧠 [Cast] 根据梗概 JSON 规划主角阶段与配角（≤{MAX_REF_CHARACTERS} 人）...")
    client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL.rstrip("/"))
    user = json.dumps({"topic": topic, "synopsis_package": synopsis_payload}, ensure_ascii=False)
    try:
        response = client.chat.completions.create(
            model=config.MODEL_LLM,
            messages=[
                {"role": "system", "content": CAST_PLAN_SYSTEM},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.35,
            max_tokens=8192,
        )
        raw = (response.choices[0].message.content or "").strip()
        plan = json.loads(raw)
        return _validate_and_trim_cast(plan)
    except Exception as e:
        print(f"  ⚠️ [Cast] LLM 规划失败: {e}")
        return None


def design_environments(topic: str):
    """使用 LLM 为当前主题构思 4 个核心场景锚点"""
    print(f"  🧠 [Design] 正在为主题【{topic}】构思核心场景锚点...")
    client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL.rstrip("/"))

    system_prompt = f"""你是一个顶级的电影美术指导。
你的任务是根据一个视频主题，构思 4 个最具代表性的电影感核心场景。

画风约束（不可违反）：
{config.STYLE_ANCHOR}

输出要求：
1. 为每个场景起一个简单的英文名（如 office, street, church）。
2. 提供 [english_prompt]：用于生成场景基准图的详细英文提示词。
3. 提供 [anchor_description]：场景的视觉细节描述，用于锁定光影和材质。

格式（仅输出 JSON 列表）:
[
  {{"name": "office", "english_prompt": "...", "anchor_description": "..."}},
  ...
]"""

    user_prompt = f"请为当前主题【{topic}】构思 4 个核心视觉场景。"

    try:
        response = client.chat.completions.create(
            model=config.MODEL_LLM,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.8,
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(content)
    except Exception as e:
        print(f"  ⚠️ 场景构思失败: {e}")
        return []


def get_needed_stages(topic: str):
    """根据梗概或全文节选判定主角人生阶段（轻量调用，不执行完整 Cast 规划）。"""
    text_to_analyze = ""
    syn = _load_synopsis_dict()
    if syn:
        text_to_analyze = (syn.get("synopsis") or "").strip()
        meta = {k: syn.get(k) for k in ("era", "identity", "duration") if syn.get(k)}
        if meta:
            text_to_analyze = text_to_analyze + "\n" + json.dumps(meta, ensure_ascii=False)
    if not text_to_analyze and config.FULL_STORY_V6_PATH.exists():
        try:
            story_data = json.loads(config.FULL_STORY_V6_PATH.read_text(encoding="utf-8"))
            text_to_analyze = (story_data.get("master_design", {}).get("full_narration", "") or "").strip()
        except Exception:
            pass
    if not text_to_analyze:
        return ["middle"]
    client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL.rstrip("/"))
    system_prompt = """你是一个专业的剧本分析师。
根据提供的文本，判定主角在整个故事中具体经历了哪些【人生阶段】。
可选阶段：child, youth, middle, elderly。只输出 JSON 列表。"""
    try:
        response = client.chat.completions.create(
            model=config.MODEL_LLM,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"主题: {topic}\n文本摘要: {text_to_analyze[:2000]}"},
            ],
            temperature=0.3,
        )
        content = response.choices[0].message.content.strip()
        if "```" in content:
            content = content.split("```")[1].replace("json", "").strip()
        stages = json.loads(content)
        return stages if stages else ["middle"]
    except Exception:
        return ["middle"]


def design_character(topic: str, role_tag: str, stage: str = "middle"):
    """单阶段重画或回退：仅 topic + 阶段，无梗概细节。"""
    stage_name_cn = {
        "child": "幼年/童年",
        "youth": "青年/求学期",
        "middle": "中年/壮年",
        "elderly": "老年/晚年",
    }.get(stage, "中年")

    print(f"  🧠 [Design] 正在构思角色: {role_tag} (阶段: {stage_name_cn})...")
    client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL.rstrip("/"))

    system_prompt = f"""你是“角色定妆提示词压缩器（Prompt Compressor）”。
目标：为“快乐氰化物 / Cyanide and Happiness 美漫风”输出可直接用于人物三视图定妆照的英文提示词。

【当前角色阶段】：{stage_name_cn} ({stage})

硬性风格约束（必须全部体现）：
- Cyanide and Happiness comic style, round bean head, dot eyes, stick-figure limbs, bold black outlines,
  flat vibrant colors, pure 2D flat cartoon
- no realistic anatomy, no 3D, no CGI, no photorealistic, no texture details

定妆照构图约束（必须写入 english_prompt）：
- character design sheet, triple view: front, side, back, full body, centered, pure white background,
  no environment, no props, no shadow

人物信息写法约束：
1) 身份辨识核心 + 年龄阶段 + 1~2 服饰锚点
2) english_prompt 控制在 80~120 个英文词

输出格式（仅输出 JSON）:
{{ "english_prompt": "...", "anchor_description": "中文一句话，20~40字" }}"""

    user_prompt = f"请为【{topic}】设计角色类型为 {role_tag} 的【{stage_name_cn}】形象。"

    try:
        response = client.chat.completions.create(
            model=config.MODEL_LLM,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.7,
        )
        content = response.choices[0].message.content.strip()
        if "```" in content:
            content = content.split("```")[1].replace("json", "").strip()
        return json.loads(content)
    except Exception:
        return {
            "english_prompt": f"A {stage} {role_tag} character for {topic}",
            "anchor_description": f"the {stage} {role_tag}",
        }


def _archive_and_clean_category(category: str, target_stage: str = None):
    target_dirs = []
    if category == "protagonist":
        if target_stage:
            target_dirs = [config.CHARACTER_REF_MAP.get(target_stage, config.REFS_PROTAGONIST_MIDDLE)]
        else:
            target_dirs = [
                config.REFS_PROTAGONIST_CHILD,
                config.REFS_PROTAGONIST_YOUTH,
                config.REFS_PROTAGONIST_MIDDLE,
                config.REFS_PROTAGONIST_ELDERLY,
                config.REFS_DIR / "supporting",
            ]
    elif category == "supporting":
        target_dirs = [config.REFS_SUPPORTING]
    elif category == "other":
        target_dirs = [config.REFS_OTHER]

    for target_dir in target_dirs:
        if not target_dir or not target_dir.exists():
            continue
        files = list(target_dir.glob("*"))
        if not files:
            continue
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = config.REFS_BACKUP_DIR / f"{timestamp}_{target_dir.name}"
        backup_path.mkdir(parents=True, exist_ok=True)
        for f in files:
            try:
                shutil.move(str(f), str(backup_path / f.name))
            except Exception:
                pass
        print(f"  🧹 [Clean] {target_dir.name} 目录已物理归档清理。")


def _archive_supporting_subdir(role_id: str):
    d = config.REFS_DIR / "supporting" / role_id
    if not d.exists():
        return
    files = list(d.glob("*"))
    if not files:
        return
    import datetime

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = config.REFS_BACKUP_DIR / f"{timestamp}_supporting_{role_id}"
    backup_path.mkdir(parents=True, exist_ok=True)
    for f in files:
        try:
            shutil.move(str(f), str(backup_path / f.name))
        except Exception:
            pass
    print(f"  🧹 [Clean] supporting/{role_id} 已归档。")


async def generate_ref_sheet_at(out_dir: Path, english_prompt: str, ref_image_path: Path | None = None) -> Path | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "triple_view.png"
    label = out_dir.name
    print(f"  🎨 [Generate] 定妆输出 {label} (参考: {ref_image_path.name if ref_image_path else 'None'})...")

    full_prompt = (
        "Background: PURE FLAT WHITE #FFFFFF BACKGROUND, NO ENVIRONMENT, NO shadows. "
        f"CHARACTER DESIGN SHEET, {config.STYLE_ANCHOR} "
        "SAME character from 3 angles: 1. FRONT view. 2. SIDE profile. 3. BACK view. "
        f"Character appearance: {english_prompt}"
    )

    try:
        img_refs = [str(ref_image_path)] if ref_image_path else None
        img_bytes = await generate_image(prompt=full_prompt, size="2k", image_refs=img_refs)
        if img_bytes:
            out_path.write_bytes(img_bytes)
            rel = str(out_path.relative_to(BASE_DIR)).replace("\\", "/")
            vault_backup(out_path, rel)
            print(f"  ✅ [Done] 已存入: {out_path}")
            return out_path
    except Exception as e:
        print(f"  ❌ [Error] 生图失败: {e}")
    return None


async def generate_ref_sheet(category: str, english_prompt: str, stage: str = "middle", ref_image_path: Path = None):
    """兼容旧 API：主角阶段目录。"""
    if category == "protagonist":
        target_dir = config.CHARACTER_REF_MAP.get(stage, config.REFS_PROTAGONIST_MIDDLE)
    else:
        target_dir = config.CHARACTER_REF_MAP.get(category, config.REFS_OTHER)
    return await generate_ref_sheet_at(target_dir, english_prompt, ref_image_path)


def _sync_full_story_cast(
    target_story_path: Path,
    cast_registry: dict,
    physical_anchors: dict,
    ref_display_slots: list,
    stages: list,
):
    if not target_story_path.exists():
        print(f"  ⚠️ [Sync] 剧本不存在，跳过: {target_story_path}")
        return
    try:
        story_data = json.loads(target_story_path.read_text(encoding="utf-8"))
        master_design = story_data.setdefault("master_design", {})
        master_design["cast_registry"] = cast_registry
        master_design["physical_char_anchors"] = physical_anchors
        master_design["ref_display_slots"] = ref_display_slots
        master_design["detected_life_stages"] = stages

        if not master_design.get("stage_map"):
            ordered = [s for s in stages if s in physical_anchors] or list(physical_anchors.keys()) or ["middle"]
            pro_keys = {k for k in physical_anchors if not str(k).startswith("supporting_")}
            ordered = [s for s in stages if s in pro_keys] or list(pro_keys) or ["middle"]
            if len(ordered) == 1:
                master_design["stage_map"] = [{"stage": ordered[0], "start_shot": 1, "end_shot": 999999}]
            else:
                rough = []
                span = max(1, 999 // len(ordered))
                start = 1
                for idx, st in enumerate(ordered):
                    end = 999999 if idx == len(ordered) - 1 else (start + span - 1)
                    rough.append({"stage": st, "start_shot": start, "end_shot": end})
                    start = end + 1
                master_design["stage_map"] = rough

        target_story_path.write_text(json.dumps(story_data, ensure_ascii=False, indent=2), encoding="utf-8")
        vault_backup(target_story_path, f"scripts/{target_story_path.name}")
        print(f"  ✅ [Sync] cast_registry + anchors 已回写: {list(physical_anchors.keys())}")
        print(f"  📍 [Sync] {target_story_path}")
    except Exception as e:
        print(f"  ⚠️ [Sync] 回写失败: {e}")


def _build_ref_display_slots(cast_registry: dict, physical_anchors: dict) -> list:
    slots = []
    pro = cast_registry.get("protagonist") or {}
    for st in pro.get("stages") or []:
        p = physical_anchors.get(st)
        if p:
            slots.append(
                {
                    "kind": "protagonist",
                    "stage": st,
                    "display_name_en": pro.get("display_name_en", "Protagonist"),
                    "path_key": st,
                    "abs_path": p,
                }
            )
    for sup in cast_registry.get("supporting") or []:
        rid = sup.get("role_id")
        pk = f"supporting_{rid}"
        p = physical_anchors.get(pk)
        if p:
            slots.append(
                {
                    "kind": "supporting",
                    "role_id": rid,
                    "display_name_en": sup.get("display_name_en", rid),
                    "path_key": pk,
                    "abs_path": p,
                }
            )
    return slots


async def _run_synopsis_driven_protagonist_pipeline(topic: str):
    syn = _load_synopsis_dict()
    if not syn:
        print("  ⚠️ [Cast] 未找到 temp_synopsis.json，回退旧流水线。")
        await _run_legacy_protagonist_only(topic, target_stage=None)
        return

    plan = llm_plan_cast_from_synopsis(topic, syn)
    if not plan:
        print("  ⚠️ [Cast] 规划失败，回退旧流水线。")
        await _run_legacy_protagonist_only(topic, target_stage=None)
        return

    cast_registry = {
        "protagonist": {
            "role_id": "protagonist",
            "display_name_en": plan["protagonist"]["display_name_en"],
            "stages": plan["protagonist"]["stages"],
        },
        "supporting": [{"role_id": x["role_id"], "display_name_en": x["display_name_en"]} for x in plan["supporting"]],
    }

    stages = plan["protagonist"]["stages"]
    stage_prompts = plan["protagonist"]["stage_prompts"]
    physical_anchors: dict = {}

    anchor_ref_path: Path | None = None
    for st in stages:
        design = stage_prompts[st]
        tdir = config.CHARACTER_REF_MAP.get(st, config.REFS_PROTAGONIST_MIDDLE)
        gen_path = await generate_ref_sheet_at(tdir, design["english_prompt"], anchor_ref_path)
        if gen_path:
            desc_f = gen_path.parent / "description.txt"
            desc_f.write_text(design.get("anchor_description", ""), encoding="utf-8")
            physical_anchors[st] = str(gen_path.resolve())
            anchor_ref_path = gen_path

    for sup in plan["supporting"]:
        rid = sup["role_id"]
        sdir = config.REFS_DIR / "supporting" / rid
        gen_path = await generate_ref_sheet_at(sdir, sup["english_prompt"], None)
        if gen_path:
            desc_f = gen_path.parent / "description.txt"
            desc_f.write_text(sup.get("anchor_description", ""), encoding="utf-8")
            k = f"supporting_{rid}"
            physical_anchors[k] = str(gen_path.resolve())

    ref_slots = _build_ref_display_slots(cast_registry, physical_anchors)
    paths = get_paths(create_if_missing=False)
    run_full = (paths or {}).get("scripts_dir")
    run_full = (run_full / "full_story_v6.json") if run_full else None
    target = run_full if (run_full and run_full.exists()) else config.FULL_STORY_V6_PATH
    _sync_full_story_cast(target, cast_registry, physical_anchors, ref_slots, stages)
    print(f"\n✨ Cast 定妆完成：主角阶段 {stages}，配角 {len(plan['supporting'])} 人。")


async def _run_legacy_protagonist_only(topic: str, target_stage: str | None):
    stages = get_needed_stages(topic)
    if target_stage:
        stages = [target_stage]

    middle_ref_path = config.CHARACTER_REF_MAP.get("middle", config.REFS_PROTAGONIST_MIDDLE) / "triple_view.png"
    if not middle_ref_path.exists():
        middle_ref_path = None

    if "middle" in stages:
        design = design_character(topic, "protagonist", "middle")
        gen_path = await generate_ref_sheet("protagonist", design["english_prompt"], "middle")
        if gen_path:
            desc_f = gen_path.parent / "description.txt"
            desc_f.write_text(design["anchor_description"], encoding="utf-8")
            middle_ref_path = gen_path

    for stage in [s for s in stages if s != "middle"]:
        design = design_character(topic, "protagonist", stage)
        result_path = await generate_ref_sheet("protagonist", design["english_prompt"], stage, middle_ref_path)
        if result_path:
            desc_f = result_path.parent / "description.txt"
            desc_f.write_text(design["anchor_description"], encoding="utf-8")

    paths = get_paths(create_if_missing=False)
    run_full_story_path = (paths or {}).get("scripts_dir")
    run_full_story_path = (run_full_story_path / "full_story_v6.json") if run_full_story_path else None
    target_story_path = run_full_story_path if (run_full_story_path and run_full_story_path.exists()) else config.FULL_STORY_V6_PATH

    if target_story_path.exists():
        try:
            story_data = json.loads(target_story_path.read_text(encoding="utf-8"))
            physical_anchors = {}
            for _stage, _dir in [
                ("child", config.REFS_PROTAGONIST_CHILD),
                ("youth", config.REFS_PROTAGONIST_YOUTH),
                ("middle", config.REFS_PROTAGONIST_MIDDLE),
                ("elderly", config.REFS_PROTAGONIST_ELDERLY),
            ]:
                _img = _dir / "triple_view.png"
                if _img.exists():
                    physical_anchors[_stage] = str(_img.resolve())
            master_design = story_data.setdefault("master_design", {})
            master_design["physical_char_anchors"] = physical_anchors
            master_design["detected_life_stages"] = stages
            default_name = str(story_data.get("metadata", {}).get("topic") or topic or "Protagonist")
            master_design["cast_registry"] = {
                "protagonist": {"role_id": "protagonist", "display_name_en": default_name[:32], "stages": stages},
                "supporting": [],
            }
            master_design["ref_display_slots"] = _build_ref_display_slots(master_design["cast_registry"], physical_anchors)
            if not master_design.get("stage_map"):
                ordered = [s for s in stages if s in physical_anchors] or list(physical_anchors.keys()) or ["middle"]
                if len(ordered) == 1:
                    master_design["stage_map"] = [{"stage": ordered[0], "start_shot": 1, "end_shot": 999999}]
                else:
                    rough = []
                    span = max(1, 999 // len(ordered))
                    start = 1
                    for idx, st in enumerate(ordered):
                        end = 999999 if idx == len(ordered) - 1 else (start + span - 1)
                        rough.append({"stage": st, "start_shot": start, "end_shot": end})
                        start = end + 1
                    master_design["stage_map"] = rough
            target_story_path.write_text(json.dumps(story_data, ensure_ascii=False, indent=2), encoding="utf-8")
            vault_backup(target_story_path, f"scripts/{target_story_path.name}")
            print(f"  ✅ [Sync] physical_char_anchors: {list(physical_anchors.keys())}")
        except Exception as e:
            print(f"  ⚠️ [Sync] 写入失败: {e}")


def _merge_stage_anchor_into_full_story(stage_key: str, abs_img: str | None):
    if not abs_img:
        return
    paths = get_paths(create_if_missing=False)
    scripts = (paths or {}).get("scripts_dir")
    target = (scripts / "full_story_v6.json") if scripts else config.FULL_STORY_V6_PATH
    if not target.exists():
        target = config.FULL_STORY_V6_PATH
    if not target.exists():
        print("  ⚠️ [Sync] 无 full_story，跳过重画回写")
        return
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        md = data.setdefault("master_design", {})
        pa = md.setdefault("physical_char_anchors", {})
        pa[stage_key] = abs_img
        cr = md.get("cast_registry") or {}
        md["ref_display_slots"] = _build_ref_display_slots(cr, pa)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        vault_backup(target, f"scripts/{target.name}")
        print(f"  ✅ [Sync] 已更新 {stage_key} 物理锚点")
    except Exception as e:
        print(f"  ⚠️ [Sync] 单阶段回写失败: {e}")


def _merge_supporting_anchor_into_full_story(role_id: str, abs_img: str | None):
    if not abs_img or not role_id:
        return
    key = f"supporting_{role_id}"
    paths = get_paths(create_if_missing=False)
    scripts = (paths or {}).get("scripts_dir")
    target = (scripts / "full_story_v6.json") if scripts else config.FULL_STORY_V6_PATH
    if not target.exists():
        target = config.FULL_STORY_V6_PATH
    if not target.exists():
        print("  ⚠️ [Sync] 无 full_story，跳过配角回写")
        return
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        md = data.setdefault("master_design", {})
        pa = md.setdefault("physical_char_anchors", {})
        pa[key] = abs_img
        cr = md.get("cast_registry") or {}
        md["ref_display_slots"] = _build_ref_display_slots(cr, pa)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        vault_backup(target, f"scripts/{target.name}")
        print(f"  ✅ [Sync] 已更新配角锚点 {key}")
    except Exception as e:
        print(f"  ⚠️ [Sync] 配角回写失败: {e}")


async def run_regen_supporting_character(topic: str, role_id: str) -> int:
    """
    仅重画单个配角三视图：读 cast_registry + 梗概 → LLM 提示词 → 生图 → 回写 physical_char_anchors。
    返回 0 成功，1 失败。
    """
    role_id = _normalize_role_id(role_id)
    print(f"\n🔄 [Supporting Regen] 重画配角 role_id={role_id} …")
    paths = get_paths(create_if_missing=False)
    scripts = (paths or {}).get("scripts_dir")
    target = (scripts / "full_story_v6.json") if scripts else config.FULL_STORY_V6_PATH
    if not target.exists():
        target = config.FULL_STORY_V6_PATH
    if not target.exists():
        print("  ❌ 找不到 full_story_v6.json")
        return 1
    try:
        story_data = json.loads(target.read_text(encoding="utf-8"))
        md = story_data.get("master_design") or {}
        cr = md.get("cast_registry") or {}
        sup_list = cr.get("supporting") or []
        hit = None
        for s in sup_list:
            if isinstance(s, dict) and _normalize_role_id(s.get("role_id")) == role_id:
                hit = s
                break
        if not hit:
            print(f"  ❌ cast_registry 中未找到配角: {role_id}")
            return 1
        display_name_en = str(hit.get("display_name_en") or role_id).strip()
    except Exception as e:
        print(f"  ❌ 读取剧本失败: {e}")
        return 1

    syn = _load_synopsis_dict() or {}

    _archive_supporting_subdir(role_id)
    sdir = config.REFS_DIR / "supporting" / role_id
    sdir.mkdir(parents=True, exist_ok=True)

    design = llm_regen_supporting_prompt(topic, syn, role_id, display_name_en)
    if not design:
        design = design_character(topic, f"supporting_{role_id}", "middle")
        if not isinstance(design, dict):
            print("  ❌ 无法生成配角提示词")
            return 1

    gen_path = await generate_ref_sheet_at(sdir, design["english_prompt"], None)
    if not gen_path:
        print("  ❌ 配角生图失败")
        return 1
    desc_f = gen_path.parent / "description.txt"
    desc_f.write_text(str(design.get("anchor_description", "")), encoding="utf-8")

    _merge_supporting_anchor_into_full_story(role_id, str(gen_path.resolve()))
    print(f"\n✨ 配角 [{display_name_en}] (`{role_id}`) 重画完成。")
    return 0


async def run_ref_process(topic: str, category: str, target_stage: str = None):
    print(f"\n🚀 [Ref Pipeline] 开始为【{topic}】定制 {category} 流水线...")
    _archive_and_clean_category(category, target_stage)

    if category == "other":
        scenes = design_environments(topic)
        for scene in scenes:
            name, prompt, desc = scene["name"], scene["english_prompt"], scene["anchor_description"]
            full_p = f"WIDE ANGLE CINEMATIC BACKGROUND, {config.STYLE_ANCHOR}, No characters, {prompt}"
            img_b = await generate_image(prompt=full_p, size="2k")
            if img_b:
                p = config.REFS_OTHER / f"{name}.png"
                p.write_bytes(img_b)
                d_p = config.REFS_OTHER / f"description_{name}.txt"
                d_p.write_text(desc, encoding="utf-8")
                vault_backup(p, f"refs/other/{name}.png")
                vault_backup(d_p, f"refs/other/description_{name}.txt")
        print("\n✨ 环境锚点全量完成！")
        return

    if category == "protagonist":
        if target_stage:
            design = design_character(topic, "protagonist", target_stage)
            tdir = config.CHARACTER_REF_MAP.get(target_stage, config.REFS_PROTAGONIST_MIDDLE)
            mid = config.REFS_PROTAGONIST_MIDDLE / "triple_view.png"
            refp = mid if mid.exists() else None
            gen_path = await generate_ref_sheet_at(tdir, design["english_prompt"], refp)
            if gen_path:
                (gen_path.parent / "description.txt").write_text(design["anchor_description"], encoding="utf-8")
                _merge_stage_anchor_into_full_story(target_stage, str(gen_path.resolve()))
            print("\n✨ 单阶段重画完成并已同步剧本。")
            return
        await _run_synopsis_driven_protagonist_pipeline(topic)
        return

    design = design_character(topic, category, "middle")
    result_path = await generate_ref_sheet(category, design["english_prompt"], "middle")
    if result_path:
        desc_f = result_path.parent / "description.txt"
        desc_f.write_text(design["anchor_description"], encoding="utf-8")
        vault_backup(desc_f, f"refs/{category}/description.txt")
    print(f"\n✨ {category} 定妆完成！")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="角色定妆器 v4.0")
    parser.add_argument("--topic", type=str, required=True, help="视频主题")
    parser.add_argument(
        "--role",
        type=str,
        default="protagonist",
        choices=["protagonist", "supporting", "other"],
        help="角色类别",
    )
    parser.add_argument("--stage", type=str, default=None, help="仅重画指定主角阶段")
    parser.add_argument(
        "--regen-supporting",
        type=str,
        default=None,
        metavar="ROLE_ID",
        help="仅重画 cast_registry 中该 role_id 的配角三视图",
    )
    args = parser.parse_args()
    if args.regen_supporting:
        code = asyncio.run(run_regen_supporting_character(args.topic, args.regen_supporting.strip()))
        sys.exit(code)
    asyncio.run(run_ref_process(args.topic, args.role, args.stage))
