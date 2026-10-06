from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from dose_aware import api
from dose_aware.service import DoseAwareService


@pytest.fixture
def client() -> TestClient:
    api.service = DoseAwareService()
    return TestClient(api.app)


def create_session(client: TestClient) -> str:
    response = client.post(
        "/sessions",
        json={
            "device_id": "api-demo-device",
            "compartment_id": "night-dose",
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
            "safety_interval_minutes": 180,
        },
    )
    assert response.status_code == 201
    return response.json()["session_id"]


def event_payload(event_type: str, *, compartment_id: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "device_id": "api-demo-device",
        "event_type": event_type,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "source": "api",
    }
    if compartment_id is not None:
        payload["compartment_id"] = compartment_id
    return payload


def test_health_web_and_missing_session(client: TestClient) -> None:
    web = client.get("/")
    css = client.get("/static/styles.css")
    health = client.get("/health")
    missing = client.get("/sessions/not-found")

    assert web.status_code == 200
    assert "知醒 DoseAware" in web.text
    assert css.status_code == 200
    assert "--teal" in css.text
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "service": "dose-aware"}
    assert missing.status_code == 404
    assert missing.json()["detail"] == "session not found"


def test_api_runs_night_dose_core_flow(client: TestClient) -> None:
    session_id = create_session(client)

    reminder = client.post(
        f"/sessions/{session_id}/events",
        json=event_payload("reminder_started"),
    )
    opened = client.post(
        f"/sessions/{session_id}/events",
        json=event_payload("compartment_opened", compartment_id="night-dose"),
    )
    snapshot = client.get(f"/sessions/{session_id}")
    sessions = client.get("/sessions")
    audit = client.get(f"/sessions/{session_id}/audit")
    notifications = client.get(f"/notifications?session_id={session_id}")

    assert reminder.status_code == 200
    assert reminder.json()["snapshot"]["state"] == "reminding"
    assert opened.status_code == 200
    assert opened.json()["snapshot"]["state"] == "protected"
    assert {item["command"] for item in opened.json()["result"]["commands"]} == {
        "stop_reminder",
        "lock_compartment",
    }
    assert snapshot.status_code == 200
    assert snapshot.json()["last_opened_at"] is not None
    assert snapshot.json()["audit_count"] == 2
    assert sessions.status_code == 200
    assert [item["session_id"] for item in sessions.json()] == [session_id]
    assert audit.status_code == 200
    assert [item["to_state"] for item in audit.json()] == ["reminding", "protected"]
    assert notifications.status_code == 200
    assert notifications.json() == []


def test_api_rejects_invalid_transition(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.post(
        f"/sessions/{session_id}/events",
        json=event_payload("compartment_opened", compartment_id="night-dose"),
    )

    assert response.status_code == 409
    assert "invalid in scheduled" in response.json()["detail"]


def test_demo_scenario_exposes_real_state_machine_result(client: TestClient) -> None:
    response = client.post("/demo/scenarios/duplicate-open")

    assert response.status_code == 200
    body = response.json()
    assert body["scenario"] == "duplicate-open"
    assert body["outputs"][-1]["snapshot"]["state"] == "duplicate_risk"
    assert len(api.service.notifications) == 1


def test_caregiver_can_acknowledge_notification_and_patient_can_toggle_privacy(client: TestClient) -> None:
    response = client.post("/demo/scenarios/duplicate-open")
    assert response.status_code == 200

    notifications = client.get("/notifications")
    assert notifications.status_code == 200
    notification_id = notifications.json()[0]["notification_id"]
    acknowledged = client.post(f"/notifications/{notification_id}/acknowledge")
    assert acknowledged.status_code == 200
    assert acknowledged.json()["acknowledged"] is True

    privacy = client.post("/privacy", json={"enabled": False})
    assert privacy.status_code == 200
    assert privacy.json() == {"privacy_mode": False}
    assert client.get("/privacy").json() == {"privacy_mode": False}
