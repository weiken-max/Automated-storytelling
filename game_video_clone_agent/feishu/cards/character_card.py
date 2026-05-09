"""
定妆审批卡片
展示主角各阶段定妆照 + 配角三视图 + 审批/重画按钮
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from feishu.cards.base_card import BaseCard
from feishu.config import ACTION, HEADER_TEMPLATES, STAGE_NAMES, STAGE_ORDER


class CharacterCard(BaseCard):
    card_type = "character"
    header_template = HEADER_TEMPLATES["blue"]

    def __init__(self, session, mgr, ref_slots: list[dict] | None = None,
                 generated_stages: list[str] | None = None,
                 expected_stages: set[str] | None = None,
                 supporting_roles: list[tuple[str, str]] | None = None):
        """
        ref_slots:    主角 + 配角的展示槽 (含 abs_path, kind, stage, display_name_en, role_id)
        generated_stages: 已生成的主角阶段列表 (如 ['child','youth','elderly'])
        expected_stages:  剧本需要的阶段集合
        supporting_roles: 配角列表 [(role_id, display_name_en), ...]
        """
        super().__init__(session, mgr)
        self.ref_slots = ref_slots or []
        self.generated_stages = generated_stages or []
        self.expected_stages = expected_stages or set()
        self.supporting_roles = supporting_roles or []
        self.topic = getattr(session, "topic", "")
        self.header_title = f"🎬 定妆照审批：{self.topic}"

        # 预上传图片，缓存 img_key
        self._img_cache: dict[str, str] = {}

    def _upload_and_cache(self, img_path: str) -> str | None:
        if img_path in self._img_cache:
            return self._img_cache[img_path]
        key = self.mgr.upload_image(img_path)
        if key:
            self._img_cache[img_path] = key
        return key

    def body_elements(self) -> list[dict]:
        els = []
        if self.ref_slots:
            els.append(self.make_md(
                "**定妆参考图**（主角各阶段 + 配角）。"
                "**English display names** 已写入剧本，后续分镜将沿用。"
            ))
            for slot in self.ref_slots:
                if not isinstance(slot, dict):
                    continue
                abs_p = slot.get("abs_path", "")
                if not abs_p:
                    continue
                char_path = Path(abs_p)
                if not char_path.is_file():
                    els.append(self.make_md(
                        f"⚠️ **{slot.get('display_name_en', '?')}**：文件缺失 `{abs_p}`"
                    ))
                    continue

                kind = slot.get("kind", "")
                name_en = slot.get("display_name_en", "Character")
                stage_key = slot.get("stage", "")
                rid = slot.get("role_id", "")

                if kind == "protagonist":
                    st_name = STAGE_NAMES.get(stage_key, {}).get("name", stage_key)
                    caption = f"🎭 **{name_en}** · 主角 · {st_name}（`{stage_key}`）"
                    if stage_key not in self.generated_stages:
                        self.generated_stages.append(stage_key)
                else:
                    caption = f"🎭 **{name_en}** · 配角 · `role_id={rid}`"

                img_key = self._upload_and_cache(str(char_path))
                if img_key:
                    els.append(self.make_md(caption))
                    els.append(self.make_img(img_key, name_en[:40]))
                else:
                    els.append(self.make_md(f"⚠️ **{name_en}** 上传失败：`{char_path}`"))
        else:
            # 回退：按固定四阶段扫描
            els.append(self.make_md("**您的主角人生阶段定妆照已出炉，请过目：**"))
            # 需要 assets 信息来定位文件，这里用 session context
            refs_root_str = (getattr(self.session, "context_json", {}) or {}).get("refs_dir", "")
            if not refs_root_str:
                refs_root_str = str(Path(__file__).resolve().parent.parent.parent / "data" / "refs")
            refs_root = Path(refs_root_str)

            for stage_key in STAGE_ORDER:
                st_info = STAGE_NAMES[stage_key]
                char_path = refs_root / f"protagonist_{stage_key}" / "triple_view.png"
                if char_path.exists():
                    img_key = self._upload_and_cache(str(char_path))
                    if img_key:
                        els.append(self.make_md(f"👤 **{st_info['name']}**"))
                        els.append(self.make_img(img_key, st_info["name"]))
                        if stage_key not in self.generated_stages:
                            self.generated_stages.append(stage_key)
                    else:
                        els.append(self.make_md(f"⚠️ **{st_info['name']}** 上传失败"))
                else:
                    if stage_key in self.expected_stages:
                        els.append(self.make_md(
                            f"⚠️ **{st_info['name']}**：该阶段应已生成但文件缺失，请重画该阶段"
                        ))
                    else:
                        els.append(self.make_md(
                            f"💡 **{st_info['name']}**：剧本未涉及该阶段，跳过"
                        ))
        return els

    def action_buttons(self) -> list[dict]:
        topic = self.topic
        rows = []

        # 全部通过
        rows.append(self.make_action_row(
            self.make_button("✅ 全部通过，开始生产视频", ACTION["APPROVE_VISUALS"], "primary", topic=topic)
        ))

        # 单阶段重画按钮
        regen_btns = []
        for sk in self.generated_stages:
            if sk in STAGE_NAMES:
                regen_btns.append(
                    self.make_button(STAGE_NAMES[sk]["btn"], ACTION["REGEN_STAGE"], "default", topic=topic, stage=sk)
                )
        if regen_btns:
            rows.append(self.make_action_row(*regen_btns))

        # 配角重画按钮
        sup_btns = []
        seen = set()
        for rid, name in self.supporting_roles:
            if rid in seen:
                continue
            seen.add(rid)
            short = name[:20] + ("..." if len(name) > 20 else "")
            sup_btns.append(
                self.make_button(f"🎭 重画配角：{short}", ACTION["REGEN_SUPPORTING"], "default",
                                 topic=topic, supporting_role_id=rid)
            )
        if sup_btns:
            rows.append(self.make_action_row(*sup_btns))

        # 全量重画 / 重写
        rows.append(self.make_action_row(
            self.make_button("🎨 保留剧本，重画全部人物", ACTION["REGEN_ALL_VISUALS_ONLY"], "default", topic=topic),
            self.make_button("🧨 重写剧本 + 全部重画", ACTION["REJECT_VISUALS"], "danger", topic=topic),
        ))

        # 取消
        rows.append(self.make_action_row(
            self.make_button("🚫 取消当前项目，重新开始", ACTION["CANCEL_PROJECT"], "default", topic=topic)
        ))

        return rows
