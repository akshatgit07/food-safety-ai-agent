from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    """Durable dashboard journal separate from LangGraph's checkpoint tables."""

    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS feature_runs (
                    run_id TEXT PRIMARY KEY, feature_request TEXT NOT NULL,
                    status TEXT NOT NULL, state_json TEXT NOT NULL,
                    blocker_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS human_decisions (
                    approval_id TEXT PRIMARY KEY, action_id TEXT NOT NULL UNIQUE,
                    run_id TEXT NOT NULL, decision_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    dedupe_key TEXT PRIMARY KEY, transport TEXT NOT NULL,
                    payload_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS executions (
                    idempotency_key TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                    task_id TEXT NOT NULL, result_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
            """)
            self.conn.commit()

    def create_run(self, run_id: str, feature_request: str, initial_state: dict[str, Any]) -> None:
        timestamp = now_iso()
        with self.lock:
            self.conn.execute("INSERT INTO feature_runs VALUES (?, ?, ?, ?, NULL, ?, ?)",
                              (run_id, feature_request, "queued", json.dumps(initial_state), timestamp, timestamp))
            self.conn.commit()

    def save_state(self, run_id: str, state: dict[str, Any], status: str, blocker: dict[str, Any] | None = None) -> None:
        with self.lock:
            self.conn.execute("UPDATE feature_runs SET status=?, state_json=?, blocker_json=?, updated_at=? WHERE run_id=?",
                              (status, json.dumps(state, default=str), json.dumps(blocker) if blocker else None, now_iso(), run_id))
            self.conn.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM feature_runs WHERE run_id=?", (run_id,)).fetchone()
        return self._run(row) if row else None

    def list_runs(self, status: str | None = None) -> list[dict[str, Any]]:
        query, args = "SELECT * FROM feature_runs", ()
        if status:
            query, args = query + " WHERE status=?", (status,)
        query += " ORDER BY updated_at DESC"
        with self.lock:
            rows = self.conn.execute(query, args).fetchall()
        return [self._run(row) for row in rows]

    @staticmethod
    def _run(row: sqlite3.Row) -> dict[str, Any]:
        return {"run_id": row["run_id"], "feature_request": row["feature_request"], "status": row["status"],
                "state": json.loads(row["state_json"]), "blocker": json.loads(row["blocker_json"]) if row["blocker_json"] else None,
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def register_decision(self, approval_id: str, action_id: str, run_id: str, decision: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        with self.lock:
            existing = self.conn.execute("SELECT decision_json FROM human_decisions WHERE approval_id=? OR action_id=?",
                                         (approval_id, action_id)).fetchone()
            if existing:
                return False, json.loads(existing["decision_json"])
            self.conn.execute("INSERT INTO human_decisions VALUES (?, ?, ?, ?, ?)",
                              (approval_id, action_id, run_id, json.dumps(decision), now_iso()))
            self.conn.commit()
        return True, decision

    def get_decision(self, approval_id: str, action_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute("SELECT run_id, approval_id, action_id, decision_json FROM human_decisions WHERE approval_id=? OR action_id=?",
                                    (approval_id, action_id)).fetchone()
        return ({"run_id": row["run_id"], "approval_id": row["approval_id"], "action_id": row["action_id"],
                 "decision": json.loads(row["decision_json"])} if row else None)

    def save_notification(self, dedupe_key: str, transport: str, payload: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        with self.lock:
            row = self.conn.execute("SELECT payload_json FROM notifications WHERE dedupe_key=?", (dedupe_key,)).fetchone()
            if row:
                return False, json.loads(row["payload_json"])
            self.conn.execute("INSERT INTO notifications VALUES (?, ?, ?, ?)",
                              (dedupe_key, transport, json.dumps(payload, default=str), now_iso()))
            self.conn.commit()
        return True, payload

    def get_execution(self, key: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute("SELECT result_json FROM executions WHERE idempotency_key=?", (key,)).fetchone()
        return json.loads(row["result_json"]) if row else None

    def save_execution(self, key: str, run_id: str, task_id: str, result: dict[str, Any]) -> None:
        with self.lock:
            self.conn.execute("INSERT OR IGNORE INTO executions VALUES (?, ?, ?, ?, ?)",
                              (key, run_id, task_id, json.dumps(result), now_iso()))
            self.conn.commit()

    def close(self) -> None:
        with self.lock:
            self.conn.close()


class LocalSlackAdapter:
    """Slack-shaped notification adapter with durable duplicate protection."""

    def __init__(self, store: RunStore):
        self.store = store

    def send_escalation(self, payload: dict[str, Any], dedupe_key: str) -> dict[str, Any]:
        created, saved = self.store.save_notification(dedupe_key, "mock_slack", payload)
        return {"transport": "mock_slack", "sent": created, "deduplicated": not created, "payload": saved}
