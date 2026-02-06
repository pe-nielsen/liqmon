#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sys

from liqmon.config import AppConfig, load_config
from liqmon.devices import build_device
from liqmon.poller import DeviceTask, Poller
from liqmon.storage import CsvSink


LOG = logging.getLogger("liqmon")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Poll multiple lab instruments and append readings to CSV.",
    )
    parser.add_argument(
        "--config",
        default="liqmon.toml",
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
        interval_s = device_cfg.interval_s or cfg.global_config.interval_s
        tasks.append(DeviceTask(device=device, interval_s=interval_s, sink=sink))
    return tasks


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    config = load_config(args.config)
    tasks = _build_tasks(config)
    poller = Poller(tasks, use_utc=config.global_config.utc)
    poller.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
