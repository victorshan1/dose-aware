from datetime import datetime, timedelta, timezone

from dose_aware.protocol import DeviceEvent, EventType
from dose_aware.repository import SQLiteRepository
from dose_aware.service import DoseAwareService
from dose_aware.state_machine import DoseState


def make_event(event_type: EventType, at: datetime, **kwargs: object) -> DeviceEvent:
    return DeviceEvent(
        device_id="persistent-device",
        event_type=event_type,
        occurred_at=at,
        **kwargs,
    )


def test_session_state_and_audit_survive_restart(tmp_path) -> None:
    database_path = tmp_path / "dose-aware-test.db"
    now = datetime.now(timezone.utc)
    first = DoseAwareService(SQLiteRepository(database_path))
    session = first.create_session(
        device_id="persistent-device",
        compartment_id="night-dose",
        scheduled_at=now,
        safety_interval_minutes=180,
    )
    first.process(session.session_id, make_event(EventType.REMINDER_STARTED, now))
    first.process(
        session.session_id,
        make_event(EventType.COMPARTMENT_OPENED, now, compartment_id="night-dose"),
    )

    restarted = DoseAwareService(SQLiteRepository(database_path))
    restored = restarted.sessions[session.session_id]

    assert restored.state == DoseState.PROTECTED
    assert restored.last_opened_at == now
    assert restored.protected_until == now + timedelta(minutes=180)
    assert len(restored.audit) == 2
    assert restarted.snapshot(session.session_id)["state"] == "protected"


def test_idempotency_survives_restart(tmp_path) -> None:
    database_path = tmp_path / "dose-aware-idempotency.db"
    now = datetime.now(timezone.utc)
    first = DoseAwareService(SQLiteRepository(database_path))
    session = first.create_session(
        device_id="persistent-device",
        compartment_id="night-dose",
        scheduled_at=now,
    )
    reminder = make_event(EventType.REMINDER_STARTED, now)
    first.process(session.session_id, reminder)

    restarted = DoseAwareService(SQLiteRepository(database_path))
    duplicate = restarted.process(session.session_id, reminder)

    assert duplicate.duplicate is True
    assert duplicate.reason == "event_already_processed"
    assert len(restarted.sessions[session.session_id].audit) == 1


def test_notification_survives_restart_without_duplicate(tmp_path) -> None:
    database_path = tmp_path / "dose-aware-notifications.db"
    now = datetime.now(timezone.utc)
    first = DoseAwareService(SQLiteRepository(database_path))
    session = first.create_session(
        device_id="persistent-device",
        compartment_id="night-dose",
        scheduled_at=now,
    )
    first.process(session.session_id, make_event(EventType.REMINDER_STARTED, now))
    first.process(
        session.session_id,
        make_event(EventType.COMPARTMENT_OPENED, now, compartment_id="night-dose"),
    )
    duplicate_open = make_event(
        EventType.COMPARTMENT_OPENED,
        now + timedelta(minutes=5),
        compartment_id="night-dose",
    )
    first.process(session.session_id, duplicate_open)
    first.process(session.session_id, duplicate_open)

    restarted = DoseAwareService(SQLiteRepository(database_path))
    counts = restarted.repository.table_counts()

    assert restarted.sessions[session.session_id].state == DoseState.DUPLICATE_RISK
    assert len(restarted.notifications) == 1
    assert restarted.notifications[0]["reason"] == "duplicate_open_risk"
    assert counts == {"sessions": 1, "notifications": 1}
