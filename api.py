"""FastAPI entrypoint for the first runnable DoseAware slice."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .protocol import DeviceEvent
from .repository import SQLiteRepository
from .service import DoseAwareService

app = FastAPI(
    title="知醒 DoseAware API",
    version="0.1.0",
    description="开源服药安全系统的确定性核心 API。开盒不等于已服药。",
)
database_path = os.getenv("DOSE_AWARE_DATABASE_PATH", "dose_aware.db")
service = DoseAwareService(SQLiteRepository(database_path))
web_directory = Path(__file__).resolve().parents[2] / "web"
if web_directory.exists():
    app.mount("/static", StaticFiles(directory=web_directory), name="static")


class SessionCreateRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)
    compartment_id: str = Field(min_length=1, max_length=100)
    scheduled_at: datetime
    safety_interval_minutes: int = Field(default=180, ge=1, le=24 * 60)


class PrivacyModeRequest(BaseModel):
    enabled: bool


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    index_path = web_directory / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="web app not found")
    return FileResponse(index_path)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "dose-aware"}


@app.post("/demo/scenarios/{name}")
def run_demo_scenario(name: str) -> dict[str, object]:
    try:
        outputs = service.run_scenario(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    snapshot = outputs[-1]["snapshot"]
    return {
        "scenario": name,
        "session_id": snapshot["session_id"],
        "outputs": outputs,
    }


@app.post("/sessions", status_code=201)
def create_session(request: SessionCreateRequest) -> dict[str, object]:
    session = service.create_session(**request.model_dump())
    return service.snapshot(session.session_id)


@app.get("/sessions")
def list_sessions() -> list[dict[str, object]]:
    return service.list_sessions()


@app.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, object]:
    if session_id not in service.sessions:
        raise HTTPException(status_code=404, detail="session not found")
    return service.snapshot(session_id)


@app.get("/sessions/{session_id}/audit")
def get_audit_log(session_id: str) -> list[dict[str, str]]:
    if session_id not in service.sessions:
        raise HTTPException(status_code=404, detail="session not found")
    return service.audit_log(session_id)


@app.get("/notifications")
def list_notifications(session_id: str | None = None) -> list[dict[str, object]]:
    if session_id is not None and session_id not in service.sessions:
        raise HTTPException(status_code=404, detail="session not found")
    return service.list_notifications(session_id)


@app.post("/notifications/{notification_id}/acknowledge")
def acknowledge_notification(notification_id: int) -> dict[str, object]:
    try:
        return service.acknowledge_notification(notification_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/privacy")
def get_privacy_mode() -> dict[str, bool]:
    return {"privacy_mode": service.privacy_mode}


@app.post("/privacy")
def set_privacy_mode(request: PrivacyModeRequest) -> dict[str, bool]:
    return service.set_privacy_mode(request.enabled)


@app.post("/sessions/{session_id}/events")
def ingest_event(session_id: str, event: DeviceEvent) -> dict[str, object]:
    if session_id not in service.sessions:
        raise HTTPException(status_code=404, detail="session not found")
    try:
        result = service.process(session_id, event)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "result": result.model_dump(mode="json"),
        "snapshot": service.snapshot(session_id),
    }
