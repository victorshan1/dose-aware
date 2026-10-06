from datetime import datetime, timedelta, timezone

import pytest

from dose_aware.protocol import DeviceEvent, EventType
from dose_aware.service import DoseAwareService
from dose_aware.state_machine import DoseState, InvalidTransition


@pytest.fixture
def service() -> DoseAwareService:
    return DoseAwareService()


def event(event_type: EventType, at: datetime, **kwargs: object) -> DeviceEvent:
    return DeviceEvent(device_id="demo-device", event_type=event_type, occurred_at=at, **kwargs)


def test_night_dose_enters_protection_and_stops_reminder(service: DoseAwareService) -> None:
    now = datetime.now(timezone.utc)
    session = service.create_session(
        device_id="demo-device",
        compartment_id="night-dose",
        scheduled_at=now,
        safety_interval_minutes=180,
    )

    service.process(session.session_id, event(EventType.REMINDER_STARTED, now))
    result = service.process(
        session.session_id,
        event(EventType.COMPARTMENT_OPENED, now, compartment_id="night-dose"),
    )

    assert result.accepted is True
    assert service.sessions[session.session_id].state == DoseState.PROTECTED
    assert {command.command for command in result.commands} == {"stop_reminder", "lock_compartment"}
    assert service.snapshot(session.session_id)["last_opened_at"] == now.isoformat()


def test_duplicate_open_creates_risk_and_caregiver_notification(service: DoseAwareService) -> None:
    now = datetime.now(timezone.utc)
    session = service.create_session(
        device_id="demo-device",
        compartment_id="night-dose",
        scheduled_at=now,
        safety_interval_minutes=180,
    )
    service.process(session.session_id, event(EventType.REMINDER_STARTED, now))
    service.process(session.session_id, event(EventType.COMPARTMENT_OPENED, now, compartment_id="night-dose"))

    result = service.process(
        session.session_id,
        event(EventType.COMPARTMENT_OPENED, now + timedelta(minutes=5), compartment_id="night-dose"),
    )

    assert result.reason == "duplicate_open_during_safety_interval"
    assert service.sessions[session.session_id].state == DoseState.DUPLICATE_RISK
    assert len(service.notifications) == 1
    assert service.notifications[0]["reason"] == "duplicate_open_risk"


def test_duplicate_event_is_idempotent(service: DoseAwareService) -> None:
    now = datetime.now(timezone.utc)
    session = service.create_session(
        device_id="demo-device",
        compartment_id="night-dose",
        scheduled_at=now,
    )
    reminder = event(EventType.REMINDER_STARTED, now)

    first = service.process(session.session_id, reminder)
    second = service.process(session.session_id, reminder)

    assert first.duplicate is False
    assert second.duplicate is True
    assert len(service.sessions[session.session_id].audit) == 1


def test_no_response_escalates_to_caregiver(service: DoseAwareService) -> None:
    now = datetime.now(timezone.utc)
    session = service.create_session(
        device_id="demo-device",
        compartment_id="night-dose",
        scheduled_at=now,
    )
    service.process(session.session_id, event(EventType.REMINDER_STARTED, now))
    service.process(session.session_id, event(EventType.REMINDER_ESCALATED, now + timedelta(minutes=10)))
    result = service.process(session.session_id, event(EventType.CAREGIVER_NOTIFIED, now + timedelta(minutes=20)))

    assert result.accepted is True
    assert service.sessions[session.session_id].state == DoseState.CAREGIVER_NOTIFIED
    assert len(service.notifications) == 1
    assert service.notifications[0]["reason"] == "caregiver_notified"


def test_invalid_transition_is_rejected(service: DoseAwareService) -> None:
    now = datetime.now(timezone.utc)
    session = service.create_session(
        device_id="demo-device",
        compartment_id="night-dose",
        scheduled_at=now,
    )

    with pytest.raises(InvalidTransition):
        service.process(session.session_id, event(EventType.COMPARTMENT_OPENED, now, compartment_id="night-dose"))
