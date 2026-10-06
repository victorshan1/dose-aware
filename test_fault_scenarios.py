from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from dose_aware.protocol import DeviceEvent, EventType
from dose_aware.service import DoseAwareService
from dose_aware.state_machine import DoseState, InvalidTransition


NOW = datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)


def event(event_type: EventType, *, occurred_at: datetime = NOW, compartment_id: str | None = "night-dose", event_id=None) -> DeviceEvent:
    return DeviceEvent(
        event_id=event_id or uuid4(),
        device_id="fault-test-device",
        event_type=event_type,
        occurred_at=occurred_at,
        compartment_id=compartment_id,
    )


def started_service() -> tuple[DoseAwareService, str]:
    service = DoseAwareService()
    session = service.create_session(
        device_id="fault-test-device",
        compartment_id="night-dose",
        scheduled_at=NOW,
        safety_interval_minutes=180,
    )
    service.process(session.session_id, event(EventType.REMINDER_STARTED))
    return service, session.session_id


def test_duplicate_upload_is_idempotent() -> None:
    service, session_id = started_service()
    event_id = uuid4()
    opened = event(EventType.COMPARTMENT_OPENED, event_id=event_id)
    first = service.process(session_id, opened)
    second = service.process(session_id, opened)
    assert first.duplicate is False
    assert second.duplicate is True
    assert service.sessions[session_id].state == DoseState.PROTECTED
    assert len(service.sessions[session_id].audit) == 2


def test_wrong_compartment_does_not_count_as_valid_open() -> None:
    service, session_id = started_service()
    with pytest.raises(InvalidTransition):
        service.process(session_id, event(EventType.COMPARTMENT_OPENED, compartment_id="morning-dose"))
    assert service.sessions[session_id].state == DoseState.REMINDING
    assert service.sessions[session_id].last_opened_at is None


def test_offline_then_online_enters_syncing_without_losing_state() -> None:
    service, session_id = started_service()
    service.process(session_id, event(EventType.DEVICE_OFFLINE))
    assert service.sessions[session_id].state == DoseState.OFFLINE
    service.process(session_id, event(EventType.DEVICE_ONLINE))
    assert service.sessions[session_id].state == DoseState.SYNCING


def test_low_battery_is_recorded_without_changing_safety_state() -> None:
    service, session_id = started_service()
    service.process(session_id, event(EventType.COMPARTMENT_OPENED))
    result = service.process(session_id, event(EventType.BATTERY_LOW))
    assert result.accepted is True
    assert service.sessions[session_id].state == DoseState.PROTECTED


def test_emergency_unlock_is_audited_and_generates_command() -> None:
    service, session_id = started_service()
    service.process(session_id, event(EventType.COMPARTMENT_OPENED))
    result = service.process(session_id, event(EventType.EMERGENCY_UNLOCK_REQUESTED))
    assert result.accepted is True
    assert result.state == DoseState.EMERGENCY_UNLOCKED.value
    assert result.commands[0].command == "emergency_unlock"
    assert service.sessions[session_id].audit[-1]["reason"] == "emergency_unlock_recorded"


def test_out_of_order_open_before_reminder_is_rejected() -> None:
    service = DoseAwareService()
    session = service.create_session(
        device_id="fault-test-device",
        compartment_id="night-dose",
        scheduled_at=NOW,
        safety_interval_minutes=180,
    )
    with pytest.raises(InvalidTransition):
        service.process(session.session_id, event(EventType.COMPARTMENT_OPENED))
    assert service.sessions[session.session_id].state == DoseState.SCHEDULED
