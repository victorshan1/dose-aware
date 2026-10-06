"""SQLite persistence for DoseAware session snapshots and notifications."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .state_machine import DoseSession, DoseState


class SQLiteRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._memory_connection: sqlite3.Connection | None = None
        if self.database_path == ":memory:":
            self._memory_connection = sqlite3.connect(":memory:")
            self._memory_connection.row_factory = sqlite3.Row
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        if self._memory_connection is not None:
            return self._memory_connection
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _close(self, connection: sqlite3.Connection) -> None:
        if connection is not self._memory_connection:
            connection.close()

    def initialize(self) -> None:
        connection = self._connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS dose_sessions (
                    session_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    compartment_id TEXT NOT NULL,
                    scheduled_at TEXT NOT NULL,
                    safety_interval_seconds INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    last_opened_at TEXT,
                    protected_until TEXT,
                    processed_event_ids TEXT NOT NULL,
                    audit TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS caregiver_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            connection.commit()
        finally:
            self._close(connection)

    def save_session(self, session: DoseSession) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO dose_sessions (
                    session_id, device_id, compartment_id, scheduled_at,
                    safety_interval_seconds, state, last_opened_at, protected_until,
                    processed_event_ids, audit, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id) DO UPDATE SET
                    device_id = excluded.device_id,
                    compartment_id = excluded.compartment_id,
                    scheduled_at = excluded.scheduled_at,
                    safety_interval_seconds = excluded.safety_interval_seconds,
                    state = excluded.state,
                    last_opened_at = excluded.last_opened_at,
                    protected_until = excluded.protected_until,
                    processed_event_ids = excluded.processed_event_ids,
                    audit = excluded.audit,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    session.session_id,
                    session.device_id,
                    session.compartment_id,
                    session.scheduled_at.isoformat(),
                    int(session.safety_interval.total_seconds()),
                    session.state.value,
                    session.last_opened_at.isoformat() if session.last_opened_at else None,
                    session.protected_until.isoformat() if session.protected_until else None,
                    json.dumps(sorted(session.processed_event_ids), ensure_ascii=False),
                    json.dumps(session.audit, ensure_ascii=False),
                ),
            )
            connection.commit()
        finally:
            self._close(connection)

    def load_sessions(self) -> dict[str, DoseSession]:
        connection = self._connect()
        try:
            rows = connection.execute("SELECT * FROM dose_sessions ORDER BY updated_at").fetchall()
        finally:
            self._close(connection)

        sessions: dict[str, DoseSession] = {}
        for row in rows:
            session = DoseSession(
                session_id=row["session_id"],
                device_id=row["device_id"],
                compartment_id=row["compartment_id"],
                scheduled_at=datetime.fromisoformat(row["scheduled_at"]),
                safety_interval=timedelta(seconds=row["safety_interval_seconds"]),
                state=DoseState(row["state"]),
                last_opened_at=datetime.fromisoformat(row["last_opened_at"]) if row["last_opened_at"] else None,
                protected_until=datetime.fromisoformat(row["protected_until"]) if row["protected_until"] else None,
                processed_event_ids=set(json.loads(row["processed_event_ids"])),
                audit=list(json.loads(row["audit"])),
            )
            sessions[session.session_id] = session
        return sessions

    def add_notification(self, notification: dict[str, str]) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO caregiver_notifications (session_id, reason, created_at)
                VALUES (?, ?, ?)
                """,
                (
                    notification["session_id"],
                    notification["reason"],
                    notification["created_at"],
                ),
            )
            connection.commit()
        finally:
            self._close(connection)

    def load_notifications(self) -> list[dict[str, str]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT session_id, reason, created_at FROM caregiver_notifications ORDER BY id"
            ).fetchall()
        finally:
            self._close(connection)
        return [dict(row) for row in rows]

    def table_counts(self) -> dict[str, int]:
        connection = self._connect()
        try:
            sessions = connection.execute("SELECT COUNT(*) FROM dose_sessions").fetchone()[0]
            notifications = connection.execute("SELECT COUNT(*) FROM caregiver_notifications").fetchone()[0]
        finally:
            self._close(connection)
        return {"sessions": sessions, "notifications": notifications}
