from __future__ import annotations

import argparse
import logging
import sys

from .alerts import build_alert_manager
from .config import AppConfig, load_config
from .devices import build_device
from .poller import DeviceTask, Poller
from .storage import CsvSink


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Poll multiple lab instruments and append readings to CSV.",
    )
    parser.add_argument(
        "--config",
        default="monitor.toml",
        help="Path to the TOML configuration file.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser.parse_args(argv)


def _build_tasks(cfg: AppConfig) -> list[DeviceTask]:
    tasks: list[DeviceTask] = []
    for device_cfg in cfg.devices:
        device = build_device(device_cfg)
        output_path = device_cfg.output or cfg.global_config.output
        sink = CsvSink(output_path)
        interval_s = _task_interval_s(device_cfg, cfg.global_config.interval_s)
        tasks.append(DeviceTask(device=device, interval_s=interval_s, sink=sink))
    return tasks


def _task_interval_s(device_cfg, global_interval_s: int) -> int:
    measurement_interval_s = device_cfg.settings.get("measurement_interval_s")
    if measurement_interval_s is not None:
        interval_s = int(measurement_interval_s)
    else:
        interval_s = device_cfg.interval_s or global_interval_s
    if interval_s < 1:
        raise ValueError(f"Poll interval for {device_cfg.id!r} must be >= 1 second")
    return interval_s


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    config = load_config(args.config)
    tasks = _build_tasks(config)
    alert_manager = build_alert_manager(config)
    poller = Poller(tasks, use_utc=config.global_config.utc, alert_manager=alert_manager)
    poller.run()
    return 0
