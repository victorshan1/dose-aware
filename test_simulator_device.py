from __future__ import annotations

from simulator.device import VirtualPillbox
from dose_aware.protocol import EventType


def test_virtual_pillbox_emits_hardware_compatible_events() -> None:
    device = VirtualPillbox()
    opened = device.event("open")
    assert opened.event_type == EventType.COMPARTMENT_OPENED
    assert opened.source.value == "simulator"
    assert opened.compartment_id == "night-dose"
    assert opened.metadata["online"] is True


def test_virtual_pillbox_tracks_connectivity_and_battery() -> None:
    device = VirtualPillbox()
    offline = device.event("offline")
    low_battery = device.event("low-battery")
    online = device.event("online")
    assert offline.metadata["online"] is False
    assert low_battery.battery_percent == 15
    assert online.metadata["online"] is True
    assert device.telemetry()["online"] is True
