"""设备事件和命令协议。

协议只描述设备观察到的事实，不把开盒事件解释为已经服药。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventType(StrEnum):
    REMINDER_STARTED = "reminder_started"
    REMINDER_ESCALATED = "reminder_escalated"
    PATIENT_ACKNOWLEDGED = "patient_acknowledged"
    COMPARTMENT_OPENED = "compartment_opened"
    COMPARTMENT_CLOSED = "compartment_closed"
    DUPLICATE_OPEN_ATTEMPTED = "duplicate_open_attempted"
    LOCK_ENGAGED = "lock_engaged"
    LOCK_RELEASED = "lock_released"
    EMERGENCY_UNLOCK_REQUESTED = "emergency_unlock_requested"
    CAREGIVER_NOTIFIED = "caregiver_notified"
    NAP_STARTED = "nap_started"
    ACTIVITY_RESUMED = "activity_resumed"
    DEVICE_OFFLINE = "device_offline"
    DEVICE_ONLINE = "device_online"
    BATTERY_LOW = "battery_low"


class DeviceSource(StrEnum):
    SIMULATOR = "simulator"
    HARDWARE = "hardware"
    API = "api"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DeviceEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    device_id: str = Field(min_length=1, max_length=100)
    event_type: EventType
    occurred_at: datetime = Field(default_factory=utc_now)
    compartment_id: str | None = Field(default=None, max_length=100)
    battery_percent: int | None = Field(default=None, ge=0, le=100)
    source: DeviceSource = DeviceSource.SIMULATOR
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeviceCommand(BaseModel):
    command_id: UUID = Field(default_factory=uuid4)
    device_id: str = Field(min_length=1, max_length=100)
    command: str
    compartment_id: str | None = None
    reason: str
    until: datetime | None = None


class EventResult(BaseModel):
    accepted: bool
    duplicate: bool = False
    state: str
    reason: str
    generated_events: list[DeviceEvent] = Field(default_factory=list)
    commands: list[DeviceCommand] = Field(default_factory=list)
