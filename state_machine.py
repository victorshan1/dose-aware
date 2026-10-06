"""确定性服药会话状态机。

这是安全核心：AI 不参与状态转换、间隔判断或解锁决策。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Callable

from .protocol import DeviceCommand, DeviceEvent, EventResult, EventType


class DoseState(StrEnum):
    SCHEDULED = "scheduled"
    REMINDING = "reminding"
    ACKNOWLEDGED = "acknowledged"
    OPENED = "opened"
    PROTECTED = "protected"
    COMPLETED = "completed"
    ESCALATING = "escalating"
    CAREGIVER_NOTIFIED = "caregiver_notified"
    DUPLICATE_RISK = "duplicate_risk"
    EMERGENCY_UNLOCKED = "emergency_unlocked"
    OFFLINE = "offline"
    SYNCING = "syncing"


class InvalidTransition(ValueError):
    """Raised when an event cannot be applied to the current state."""


@dataclass
class DoseSession:
    session_id: str
    device_id: str
    compartment_id: str
    scheduled_at: datetime
    safety_interval: timedelta
    state: DoseState = DoseState.SCHEDULED
    last_opened_at: datetime | None = None
    protected_until: datetime | None = None
    processed_event_ids: set[str] = field(default_factory=set)
    audit: list[dict[str, str]] = field(default_factory=list)

    def _audit(self, event: DeviceEvent, from_state: DoseState, reason: str) -> None:
        self.audit.append(
            {
                "event_id": str(event.event_id),
                "event_type": event.event_type.value,
                "from_state": from_state.value,
                "to_state": self.state.value,
                "reason": reason,
                "occurred_at": event.occurred_at.isoformat(),
            }
        )

    def _command(self, command: str, event: DeviceEvent, reason: str, until: datetime | None = None) -> DeviceCommand:
        return DeviceCommand(
            device_id=self.device_id,
            command=command,
            compartment_id=self.compartment_id,
            reason=reason,
            until=until,
        )

    def apply(self, event: DeviceEvent, now: datetime | None = None) -> EventResult:
        """Apply one event exactly once and return observable effects."""
        event_key = str(event.event_id)
        if event_key in self.processed_event_ids:
            return EventResult(
                accepted=True,
                duplicate=True,
                state=self.state.value,
                reason="event_already_processed",
            )

        now = now or datetime.now(timezone.utc)
        if event.occurred_at.tzinfo is None:
            event.occurred_at = event.occurred_at.replace(tzinfo=timezone.utc)

        previous = self.state
        result = self._transition(event, now)
        self.processed_event_ids.add(event_key)
        self._audit(event, previous, result.reason)
        if previous == self.state and not result.accepted:
            raise InvalidTransition(f"{event.event_type.value} is invalid in {previous.value}")
        return result

    def _transition(self, event: DeviceEvent, now: datetime) -> EventResult:
        event_type = event.event_type

        if event_type in {
            EventType.COMPARTMENT_OPENED,
            EventType.COMPARTMENT_CLOSED,
            EventType.DUPLICATE_OPEN_ATTEMPTED,
            EventType.LOCK_ENGAGED,
            EventType.LOCK_RELEASED,
            EventType.EMERGENCY_UNLOCK_REQUESTED,
        } and event.compartment_id not in {None, self.compartment_id}:
            raise InvalidTransition(
                f"{event_type.value} targets {event.compartment_id}, expected {self.compartment_id}"
            )

        if event_type == EventType.REMINDER_STARTED and self.state == DoseState.SCHEDULED:
            self.state = DoseState.REMINDING
            return EventResult(accepted=True, state=self.state.value, reason="reminder_started")

        if event_type == EventType.PATIENT_ACKNOWLEDGED and self.state in {
            DoseState.REMINDING,
            DoseState.ESCALATING,
        }:
            self.state = DoseState.ACKNOWLEDGED
            return EventResult(accepted=True, state=self.state.value, reason="patient_acknowledged")

        if event_type == EventType.COMPARTMENT_OPENED:
            if self.state in {DoseState.REMINDING, DoseState.ESCALATING, DoseState.ACKNOWLEDGED}:
                self.last_opened_at = event.occurred_at
                self.protected_until = event.occurred_at + self.safety_interval
                self.state = DoseState.PROTECTED
                return EventResult(
                    accepted=True,
                    state=self.state.value,
                    reason="compartment_opened_and_protected",
                    commands=[
                        self._command("stop_reminder", event, "valid_compartment_open"),
                        self._command("lock_compartment", event, "safety_interval_active", self.protected_until),
                    ],
                )
            if self.state == DoseState.PROTECTED:
                self.state = DoseState.DUPLICATE_RISK
                return EventResult(
                    accepted=True,
                    state=self.state.value,
                    reason="duplicate_open_during_safety_interval",
                    generated_events=[
                        DeviceEvent(
                            device_id=self.device_id,
                            event_type=EventType.DUPLICATE_OPEN_ATTEMPTED,
                            occurred_at=event.occurred_at,
                            compartment_id=self.compartment_id,
                            source=event.source,
                        )
                    ],
                    commands=[
                        self._command("keep_locked", event, "duplicate_open_risk", self.protected_until),
                        self._command("notify_caregiver", event, "duplicate_open_risk"),
                    ],
                )

        if event_type == EventType.REMINDER_ESCALATED and self.state in {
            DoseState.REMINDING,
            DoseState.ESCALATING,
        }:
            self.state = DoseState.ESCALATING
            return EventResult(accepted=True, state=self.state.value, reason="reminder_escalated")

        if event_type == EventType.CAREGIVER_NOTIFIED and self.state in {
            DoseState.ESCALATING,
            DoseState.DUPLICATE_RISK,
        }:
            self.state = DoseState.CAREGIVER_NOTIFIED
            return EventResult(accepted=True, state=self.state.value, reason="caregiver_notified")

        if event_type == EventType.EMERGENCY_UNLOCK_REQUESTED and self.state in {
            DoseState.PROTECTED,
            DoseState.DUPLICATE_RISK,
            DoseState.CAREGIVER_NOTIFIED,
        }:
            self.state = DoseState.EMERGENCY_UNLOCKED
            return EventResult(
                accepted=True,
                state=self.state.value,
                reason="emergency_unlock_recorded",
                commands=[self._command("emergency_unlock", event, "user_requested_emergency_unlock")],
            )

        if event_type == EventType.DEVICE_OFFLINE and self.state != DoseState.COMPLETED:
            self.state = DoseState.OFFLINE
            return EventResult(accepted=True, state=self.state.value, reason="device_offline_local_mode")

        if event_type == EventType.DEVICE_ONLINE and self.state == DoseState.OFFLINE:
            self.state = DoseState.SYNCING
            return EventResult(accepted=True, state=self.state.value, reason="device_online_sync_pending")

        if event_type == EventType.BATTERY_LOW:
            return EventResult(accepted=True, state=self.state.value, reason="battery_low_recorded")

        if event_type == EventType.ACTIVITY_RESUMED and self.state in {
            DoseState.REMINDING,
            DoseState.ESCALATING,
            DoseState.OFFLINE,
        }:
            self.state = DoseState.REMINDING
            return EventResult(accepted=True, state=self.state.value, reason="activity_resumed_retrigger_reminder")

        raise InvalidTransition(f"{event_type.value} is invalid in {self.state.value}")

    def complete_if_protection_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if self.state in {DoseState.PROTECTED, DoseState.EMERGENCY_UNLOCKED} and self.protected_until and now >= self.protected_until:
            self.state = DoseState.COMPLETED
            return True
        return False
