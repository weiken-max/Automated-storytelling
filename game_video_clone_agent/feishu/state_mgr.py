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
        """获取当前流水线状态（只读状态机，不做进程级越权篡改）"""
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT current_topic, status FROM flow_state WHERE flow_id='main_flow'")
            row = cursor.fetchone()
            topic, status = (row[0], row[1]) if row else ("", "IDLE")

            return {"topic": topic, "status": status}
