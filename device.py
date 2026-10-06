"""交互式虚拟药盒：只产生设备事实，不直接做安全判断。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dose_aware.protocol import DeviceEvent, DeviceSource, EventType


ACTION_EVENTS: dict[str, EventType] = {
    "remind": EventType.REMINDER_STARTED,
    "ack": EventType.PATIENT_ACKNOWLEDGED,
    "open": EventType.COMPARTMENT_OPENED,
    "close": EventType.COMPARTMENT_CLOSED,
    "escalate": EventType.REMINDER_ESCALATED,
    "caregiver": EventType.CAREGIVER_NOTIFIED,
    "nap": EventType.NAP_STARTED,
    "resume": EventType.ACTIVITY_RESUMED,
    "offline": EventType.DEVICE_OFFLINE,
    "online": EventType.DEVICE_ONLINE,
    "low-battery": EventType.BATTERY_LOW,
    "emergency-unlock": EventType.EMERGENCY_UNLOCK_REQUESTED,
}


class VirtualPillbox:
    """模拟真实药盒的传感器事件和设备遥测。"""

    def __init__(self, device_id: str = "doseaware-virtual-001", compartment_id: str = "night-dose") -> None:
        self.device_id = device_id
        self.compartment_id = compartment_id
        self.battery_percent = 86
        self.online = True

    def event(self, action: str, *, metadata: dict[str, Any] | None = None) -> DeviceEvent:
        if action not in ACTION_EVENTS:
            choices = ", ".join(sorted(ACTION_EVENTS))
            raise ValueError(f"unknown device action: {action}; choices: {choices}")
        event_type = ACTION_EVENTS[action]
        if event_type == EventType.DEVICE_OFFLINE:
            self.online = False
        elif event_type == EventType.DEVICE_ONLINE:
            self.online = True
        elif event_type == EventType.BATTERY_LOW:
            self.battery_percent = min(self.battery_percent, 15)
        elif event_type in {EventType.REMINDER_STARTED, EventType.REMINDER_ESCALATED}:
            self.battery_percent = max(0, self.battery_percent - 1)
        return DeviceEvent(
            device_id=self.device_id,
            event_type=event_type,
            compartment_id=self.compartment_id,
            occurred_at=datetime.now(timezone.utc),
            battery_percent=self.battery_percent,
            source=DeviceSource.SIMULATOR,
            metadata={"online": self.online, **(metadata or {})},
        )

    def telemetry(self) -> dict[str, object]:
        return {
            "device_id": self.device_id,
            "compartment_id": self.compartment_id,
            "battery_percent": self.battery_percent,
            "online": self.online,
        }
