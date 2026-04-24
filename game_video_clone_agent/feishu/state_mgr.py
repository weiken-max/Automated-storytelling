import os
import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "state.db"

class FeishuStateMgr:
    """自动化流水线状态管家 (SQLite 持久化)"""
    def __init__(self):
        self.init_db()

    def init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS flow_state (
                    flow_id TEXT PRIMARY KEY,
                    current_topic TEXT,
                    status TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # 初始化一个单例状态
            conn.execute('''
                INSERT OR IGNORE INTO flow_state (flow_id, current_topic, status)
                VALUES ('main_flow', '', 'IDLE')
            ''')

    def set_status(self, status: str, topic: str = None):
        """更改当前流水线状态"""
        with sqlite3.connect(DB_PATH) as conn:
            if topic is not None:
                conn.execute(
                    "UPDATE flow_state SET status=?, current_topic=?, last_updated=CURRENT_TIMESTAMP WHERE flow_id='main_flow'",
                    (status, topic)
                )
            else:
                conn.execute(
                    "UPDATE flow_state SET status=?, last_updated=CURRENT_TIMESTAMP WHERE flow_id='main_flow'",
                    (status,)
                )

    def get_current_state(self) -> dict:
        """获取当前流水线状态 (集成系统级监控)"""
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT current_topic, status FROM flow_state WHERE flow_id='main_flow'")
            row = cursor.fetchone()
            topic, status = (row[0], row[1]) if row else ("", "IDLE")

            # 🛠️ 工业级加固：如果数据库说闲着，但系统后台正冒火星子，以系统为准
            # BUG-08 修复：psutil 替代 wmic（wmic Win11 22H2+ 废弃，gbk 解码非中文系统崩溃）
            if status in ["IDLE", "WAITING_TOPIC", "COMPLETED"]:
                try:
                    import psutil
                    all_cmds = ' '.join(
                        ' '.join(p.cmdline())
                        for p in psutil.process_iter(['cmdline'])
                        if p.pid != os.getpid()
                    )
                    if "step1_writer_v6" in all_cmds:        status = "STEP1_WRITING"
                    elif "step2_comic_generator_v6" in all_cmds: status = "STEP2_GENERATING"
                    elif "step3_assembler_v6" in all_cmds:       status = "STEP3_ASSEMBLING"
                    elif "story_planner_v6" in all_cmds:         status = "GENERATING_VISUALS"
                except Exception:
                    pass

            return {"topic": topic, "status": status}
