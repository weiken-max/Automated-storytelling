"""
Session 持久化存储（SQLite）
替代旧版 state_mgr.py 的 flow_state 表 + 多个散 JSON 文件
"""
import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

# 数据库路径（与旧 state.db 共享同一个文件，新建 sessions 表）
DB_PATH = Path(__file__).resolve().parent.parent / "state.db"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class SessionStore:
    """管理所有用户会话的持久化"""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH
        self._init_db()

    # ── 建表 ──────────────────────────────────────────

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id   TEXT PRIMARY KEY,
                    open_id      TEXT NOT NULL,
                    topic        TEXT DEFAULT '',
                    status       TEXT DEFAULT 'IDLE',
                    card_id      TEXT DEFAULT '',
                    card_type    TEXT DEFAULT '',
                    prod_progress TEXT DEFAULT '{}',
                    error_context TEXT DEFAULT '',
                    context_json  TEXT DEFAULT '{}',
                    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_open_id
                ON sessions(open_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_status
                ON sessions(status)
            """)

    # ── 读操作 ────────────────────────────────────────

    def get_session(self, session_id: str) -> dict | None:
        """按 session_id 读取"""
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_active_session(self, open_id: str) -> dict | None:
        """
        获取用户最新的活跃会话，
        优先取 COMPLETED 之外的最新记录。
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                """SELECT * FROM sessions
                   WHERE open_id = ? AND status != 'COMPLETED'
                   ORDER BY updated_at DESC LIMIT 1""",
                (open_id,),
            ).fetchone()
            if not row:
                # 没有非完成态的，返回最近一条（用于展示历史）
                row = conn.execute(
                    """SELECT * FROM sessions
                       WHERE open_id = ?
                       ORDER BY updated_at DESC LIMIT 1""",
                    (open_id,),
                ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_all_active_sessions(self) -> list[dict]:
        """
        返回所有未完成/需关注的会话（用于重启恢复）
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                """SELECT * FROM sessions
                   WHERE status NOT IN ('COMPLETED', 'IDLE')
                   ORDER BY updated_at DESC"""
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ── 写操作 ────────────────────────────────────────

    def create_session(
        self,
        open_id: str,
        topic: str = "",
        status: str = "IDLE",
    ) -> dict:
        """新建一个会话"""
        session_id = self._generate_session_id(open_id)
        now = _now_iso()
        record = {
            "session_id": session_id,
            "open_id": open_id,
            "topic": topic,
            "status": status,
            "card_id": "",
            "card_type": "",
            "prod_progress": "{}",
            "error_context": "",
            "context_json": "{}",
            "created_at": now,
            "updated_at": now,
        }
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT INTO sessions
                   (session_id, open_id, topic, status, card_id, card_type,
                    prod_progress, error_context, context_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record["session_id"],
                    record["open_id"],
                    record["topic"],
                    record["status"],
                    record["card_id"],
                    record["card_type"],
                    record["prod_progress"],
                    record["error_context"],
                    record["context_json"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
        return record

    def update_status(self, session_id: str, status: str, topic: str | None = None) -> bool:
        """更新会话状态（最常用操作）"""
        fields = ["status = ?", "updated_at = ?"]
        params = [status, _now_iso()]
        if topic is not None:
            fields.append("topic = ?")
            params.append(topic)
        params.append(session_id)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                f"UPDATE sessions SET {', '.join(fields)} WHERE session_id = ?",
                params,
            )
        return True

    def update_card_id(self, session_id: str, card_id: str, card_type: str = "") -> bool:
        """更新当前卡片 message_id"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """UPDATE sessions
                   SET card_id = ?, card_type = ?, updated_at = ?
                   WHERE session_id = ?""",
                (card_id, card_type, _now_iso(), session_id),
            )
        return True

    def update_progress(self, session_id: str, progress: dict) -> bool:
        """更新生产进度"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """UPDATE sessions
                   SET prod_progress = ?, updated_at = ?
                   WHERE session_id = ?""",
                (json.dumps(progress, ensure_ascii=False), _now_iso(), session_id),
            )
        return True

    def save_error_context(self, session_id: str, error: str) -> bool:
        """记录最近一次错误上下文"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """UPDATE sessions
                   SET error_context = ?, status = 'ERROR', updated_at = ?
                   WHERE session_id = ?""",
                (str(error)[-3000:], _now_iso(), session_id),
            )
        return True

    def save_context_json(self, session_id: str, ctx: dict) -> bool:
        """保存任意上下文 JSON（如时长选择草稿）"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """UPDATE sessions
                   SET context_json = ?, updated_at = ?
                   WHERE session_id = ?""",
                (json.dumps(ctx, ensure_ascii=False), _now_iso(), session_id),
            )
        return True

    def load_context_json(self, session_id: str) -> dict:
        """读取上下文 JSON"""
        row = None
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT context_json FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row and row[0]:
            try:
                return json.loads(row[0])
            except json.JSONDecodeError:
                pass
        return {}

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        return True

    # ── 工具方法 ──────────────────────────────────────

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | tuple) -> dict:
        """将数据库行转为字典"""
        if isinstance(row, sqlite3.Row):
            return dict(row)
        # tuple → 按列序映射
        keys = [
            "session_id", "open_id", "topic", "status",
            "card_id", "card_type", "prod_progress",
            "error_context", "context_json", "created_at", "updated_at",
        ]
        d = dict(zip(keys, row))
        # 反序列化 JSON 字段
        for field in ["prod_progress", "context_json"]:
            if isinstance(d.get(field), str) and d[field]:
                try:
                    d[field] = json.loads(d[field])
                except json.JSONDecodeError:
                    d[field] = {} if field == "prod_progress" else {}
        return d

    @staticmethod
    def _generate_session_id(open_id: str) -> str:
        """生成唯一 session_id"""
        ts = time.strftime("%Y%m%d_%H%M%S")
        short_id = open_id[-8:].replace("_", "").replace("-", "")
        return f"ses_{ts}_{short_id}"

    # ── 兼容旧 state_mgr 的 get_current_state ──────────

    def get_current_state(self, open_id: str = "") -> dict:
        """
        兼容旧接口，返回 {'topic': str, 'status': str}
        """
        session = self.get_active_session(open_id) if open_id else None
        if session:
            return {"topic": session.get("topic", ""), "status": session.get("status", "IDLE")}
        return {"topic": "", "status": "IDLE"}
