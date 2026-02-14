"""Active system monitor CLI."""

from __future__ import annotations

import argparse
import time

from app.monitor import MonitorConfig, MonitorObserver


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Active system monitor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run monitor loop")
    run_parser.add_argument(
        "--once",
        action="store_true",
        help="Execute a single monitor cycle and exit",
    )

    subparsers.add_parser("status", help="Show monitor status summary")
    return parser.parse_args()


def cmd_run(observer: MonitorObserver, config: MonitorConfig, once: bool) -> int:
    if not config.enabled:
        print("Monitor is disabled (MONITOR_ENABLED=false). No action taken.")
        return 0

    if once:
        cycle = observer.run_cycle()
        print(observer.format_cycle_summary(cycle))
        return 0

    print(
        f"Monitor started (mode={config.mode}, interval={config.interval_seconds}s, "
        f"log={config.log_file}, state={config.state_file})"
    )
    try:
        while True:
            cycle = observer.run_cycle()
            print(observer.format_cycle_summary(cycle))
            time.sleep(config.interval_seconds)
    except KeyboardInterrupt:
        print("Monitor stopped.")
    return 0


def cmd_status(observer: MonitorObserver) -> int:
    snapshot = observer.status_snapshot(run_live_checks=True)
    print(observer.format_status(snapshot))
    return 0


def main() -> int:
    args = parse_args()
    config = MonitorConfig.from_env()
    observer = MonitorObserver(config)

    if args.command == "run":
        return cmd_run(observer, config, once=args.once)
    if args.command == "status":
        return cmd_status(observer)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
