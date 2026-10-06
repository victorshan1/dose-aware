from __future__ import annotations

import argparse
import json

from dose_aware.service import DoseAwareService
from simulator.device import ACTION_EVENTS, VirtualPillbox


def run_interactive() -> None:
    service = DoseAwareService()
    device = VirtualPillbox()
    session = service.create_session(
        device_id=device.device_id,
        compartment_id=device.compartment_id,
        scheduled_at=device.event("remind").occurred_at,
        safety_interval_minutes=180,
    )
    print("知醒虚拟药盒已启动。输入 help 查看操作，输入 quit 退出。")
    print(json.dumps(device.telemetry(), ensure_ascii=False))
    while True:
        try:
            action = input("pillbox> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if action in {"quit", "exit", "q"}:
            break
        if action in {"help", "?"}:
            print("可用操作: " + ", ".join(sorted(ACTION_EVENTS)))
            continue
        if action == "status":
            print(json.dumps({"device": device.telemetry(), "session": service.snapshot(session.session_id)}, ensure_ascii=False, indent=2))
            continue
        try:
            event = device.event(action)
            result = service.process(session.session_id, event)
            print(json.dumps({"event": event.model_dump(mode="json"), "result": result.model_dump(mode="json"), "snapshot": service.snapshot(session.session_id)}, ensure_ascii=False, indent=2))
        except (ValueError, KeyError) as exc:
            print(f"操作失败: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="知醒 DoseAware hardware simulator")
    parser.add_argument("scenario", nargs="?", choices=["night-dose", "duplicate-open", "no-response", "post-nap"])
    parser.add_argument("--interactive", action="store_true", help="启动交互式虚拟药盒")
    args = parser.parse_args()
    if args.interactive or args.scenario is None:
        run_interactive()
        return
    outputs = DoseAwareService().run_scenario(args.scenario)
    print(json.dumps(outputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
