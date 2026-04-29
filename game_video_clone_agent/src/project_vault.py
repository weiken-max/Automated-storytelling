"""
🏛️ 项目金库 (Project Vault) — 实时增量备份系统 v1.0
=====================================================
每个项目所有素材按主题实时镜像到 data/anchors/{topic}/
工作台（data/refs, data/scripts 等）可以安全覆盖，金库永久保存。
"""
import json
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VAULT_ROOT = BASE_DIR / "data" / "anchors"
CURRENT_PROJECT_FILE = BASE_DIR / "data" / "scripts" / "current_project.json"


def init_project(topic: str) -> Path:
    """
    初始化一个新项目的金库（在 story_planner 解析到 --topic 后立即调用）。
    在 data/anchors/{topic}/ 下创建标准子目录结构。
    同时将当前项目写入 current_project.json，供后续所有脚本读取。
    并且进行 Nuclear Cleanup 清理上一个项目的残留数据。
    """
    # [Nuclear Cleanup] 清空工作台，防止上一个项目的数据重叠
    working_dirs = ["scripts", "refs", "storyboards", "audio", "output"]
    for d in working_dirs:
        work_dir = BASE_DIR / "data" / d
        if work_dir.exists():
            for item in work_dir.iterdir():
                if item.is_file() and item.name != "current_project.json":
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)

    vault = VAULT_ROOT / topic
    for sub in ["scripts", 
                "refs/protagonist_child", "refs/protagonist_youth", 
                "refs/protagonist_middle", "refs/protagonist_elderly",
                "refs/supporting", "refs/other",
                "storyboards", "audio", "output"]:
        (vault / sub).mkdir(parents=True, exist_ok=True)

    # 记录当前激活的项目
    CURRENT_PROJECT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CURRENT_PROJECT_FILE.write_text(
        json.dumps({"topic": topic}, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"\n  🏛️ [Vault] 项目金库已就绪: data/anchors/{topic}/")
    return vault


def get_current_topic() -> str | None:
    """读取当前激活的项目主题名称"""
    if not CURRENT_PROJECT_FILE.exists():
        return None
    try:
        return json.loads(CURRENT_PROJECT_FILE.read_text(encoding="utf-8")).get("topic")
    except Exception:
        return None


def get_current_vault() -> Path | None:
    """获取当前项目的金库路径，未初始化则返回 None"""
    topic = get_current_topic()
    return (VAULT_ROOT / topic) if topic else None


def backup(src: Path, vault_subpath: str) -> bool:
    """
    实时备份一个文件到当前项目金库。

    Args:
        src: 源文件的绝对路径
        vault_subpath: 金库内的相对路径，例如:
                       "scripts/full_story_v6.json"
                       "storyboards/0001.png"
                       "audio/chapter_001.mp3"
                       "refs/protagonist/triple_view.png"
    Returns:
        True 表示成功，False 表示失败或无金库
    """
    vault = get_current_vault()
    if not vault:
        # 没有激活的项目时静默跳过，不阻断正常流程
        return False

    dest = vault / vault_subpath
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.copy2(str(src), str(dest))
        return True
    except Exception as e:
        print(f"  ⚠️ [Vault] 备份失败 {src.name} → {vault_subpath}: {e}")
        return False
