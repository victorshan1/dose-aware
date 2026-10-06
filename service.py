"""Minimal in-memory application service for the first runnable slice."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .protocol import DeviceEvent, EventResult, EventType
from .repository import SQLiteRepository
from .state_machine import DoseSession, DoseState


class DoseAwareService:
    def __init__(self, repository: SQLiteRepository | None = None) -> None:
        self.repository = repository
        self.sessions: dict[str, DoseSession] = repository.load_sessions() if repository else {}
        self.notifications: list[dict[str, object]] = repository.load_notifications() if repository else []
        self.privacy_mode = True
        self.acknowledged_notifications: set[int] = set()

    def create_session(
        self,
        *,
        device_id: str,
        compartment_id: str,
        scheduled_at: datetime,
        safety_interval_minutes: int = 180,
    ) -> DoseSession:
        session = DoseSession(
            session_id=str(uuid4()),
            device_id=device_id,
            compartment_id=compartment_id,
            scheduled_at=scheduled_at,
            safety_interval=timedelta(minutes=safety_interval_minutes),
        )
        self.sessions[session.session_id] = session
        if self.repository:
            self.repository.save_session(session)
        return session

    def process(self, session_id: str, event: DeviceEvent) -> EventResult:
        session = self.sessions[session_id]
        result = session.apply(event)
        new_notifications: list[dict[str, str]] = []
        if not result.duplicate and event.event_type == EventType.CAREGIVER_NOTIFIED:
            new_notifications.append(
                {
                    "session_id": session_id,
                    "reason": result.reason,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        if not result.duplicate:
            for command in result.commands:
                if command.command == "notify_caregiver":
                    new_notifications.append(
                        {
                            "session_id": session_id,
                            "reason": command.reason,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
        self.notifications.extend(new_notifications)
        if self.repository:
            self.repository.save_session(session)
            for notification in new_notifications:
                self.repository.add_notification(notification)
        return result

    def snapshot(self, session_id: str) -> dict[str, object]:
        session = self.sessions[session_id]
        return {
            "session_id": session.session_id,
            "state": session.state.value,
            "device_id": session.device_id,
            "compartment_id": session.compartment_id,
            "scheduled_at": session.scheduled_at.isoformat(),
            "last_opened_at": session.last_opened_at.isoformat() if session.last_opened_at else None,
            "protected_until": session.protected_until.isoformat() if session.protected_until else None,
            "audit_count": len(session.audit),
        }

    def list_sessions(self) -> list[dict[str, object]]:
        return [
            self.snapshot(session_id)
            for session_id in sorted(
                self.sessions,
                key=lambda item: self.sessions[item].scheduled_at,
                reverse=True,
            )
        ]

    def audit_log(self, session_id: str) -> list[dict[str, str]]:
        return list(self.sessions[session_id].audit)

    def list_notifications(self, session_id: str | None = None) -> list[dict[str, object]]:
        items = self.notifications if session_id is None else [
            item for item in self.notifications if item["session_id"] == session_id
        ]
        return [
            {**item, "notification_id": index, "acknowledged": index in self.acknowledged_notifications}
            for index, item in enumerate(items, start=1)
        ]

    def acknowledge_notification(self, notification_id: int) -> dict[str, object]:
        if notification_id < 1 or notification_id > len(self.notifications):
            raise KeyError("notification not found")
        self.acknowledged_notifications.add(notification_id)
        return self.list_notifications()[notification_id - 1]

    def set_privacy_mode(self, enabled: bool) -> dict[str, object]:
        self.privacy_mode = enabled
        return {"privacy_mode": self.privacy_mode}

    def run_scenario(self, name: str) -> list[dict[str, object]]:
        now = datetime.now(timezone.utc)
        session = self.create_session(
            device_id="wakedose-demo-001",
            compartment_id="night-dose",
            scheduled_at=now,
            safety_interval_minutes=180,
        )
        outputs: list[dict[str, object]] = []
        events = {
            "night-dose": [
                DeviceEvent(device_id=session.device_id, event_type=EventType.REMINDER_STARTED, occurred_at=now),
                DeviceEvent(device_id=session.device_id, event_type=EventType.COMPARTMENT_OPENED, compartment_id=session.compartment_id, occurred_at=now),
            ],
            "duplicate-open": [
                DeviceEvent(device_id=session.device_id, event_type=EventType.REMINDER_STARTED, occurred_at=now),
                DeviceEvent(device_id=session.device_id, event_type=EventType.COMPARTMENT_OPENED, compartment_id=session.compartment_id, occurred_at=now),
                DeviceEvent(device_id=session.device_id, event_type=EventType.COMPARTMENT_OPENED, compartment_id=session.compartment_id, occurred_at=now),
            ],
            "no-response": [
                DeviceEvent(device_id=session.device_id, event_type=EventType.REMINDER_STARTED, occurred_at=now),
                DeviceEvent(device_id=session.device_id, event_type=EventType.REMINDER_ESCALATED, occurred_at=now),
                DeviceEvent(device_id=session.device_id, event_type=EventType.CAREGIVER_NOTIFIED, occurred_at=now),
            ],
            "post-nap": [
                DeviceEvent(device_id=session.device_id, event_type=EventType.REMINDER_STARTED, occurred_at=now),
                DeviceEvent(device_id=session.device_id, event_type=EventType.ACTIVITY_RESUMED, occurred_at=now),
            ],
        }
        if name not in events:
            raise ValueError(f"unknown scenario: {name}")
        for event in events[name]:
            result = self.process(session.session_id, event)
            outputs.append({"event": event.event_type.value, "result": result.model_dump(mode="json")})
        outputs.append({"snapshot": self.snapshot(session.session_id)})
        return outputs
