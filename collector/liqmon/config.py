from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GlobalConfig:
    interval_s: int
    output: str
    utc: bool


@dataclass(frozen=True)
class DeviceConfig:
    id: str
    type: str
    transport: str
    settings: dict[str, Any]
    interval_s: int | None
    output: str | None


@dataclass(frozen=True)
class AppConfig:
    global_config: GlobalConfig
    devices: list[DeviceConfig]


def load_config(path: str) -> AppConfig:
    data = _load_toml(path)
    global_section = data.get("global", {})
    global_cfg = GlobalConfig(
        interval_s=int(global_section.get("interval_s", 60)),
        output=str(global_section.get("output", "data/readings.csv")),
        utc=bool(global_section.get("utc", False)),
    )

    devices = []
    for entry in data.get("devices", []):
        device_id = entry.get("id")
        device_type = entry.get("type")
        transport = entry.get("transport")
        if not device_id or not device_type or not transport:
            raise ValueError("Each device must include id, type, and transport")
        interval_s = entry.get("interval_s")
        output = entry.get("output")
        settings = {k: v for k, v in entry.items() if k not in {"id", "type", "transport", "interval_s", "output"}}
        devices.append(
            DeviceConfig(
                id=str(device_id),
                type=str(device_type),
                transport=str(transport),
                settings=settings,
                interval_s=int(interval_s) if interval_s is not None else None,
                output=str(output) if output is not None else None,
            )
        )

    if not devices:
        raise ValueError("No devices defined in config")

    return AppConfig(global_config=global_cfg, devices=devices)


def decode_terminator(value: str) -> bytes:
    decoded = value.encode("utf-8").decode("unicode_escape")
    return decoded.encode("ascii")


def decode_terminators(value: Any) -> list[bytes]:
    if isinstance(value, list):
        return [decode_terminator(str(item)) for item in value]
    if isinstance(value, str):
        return [decode_terminator(value)]
    raise ValueError("read_terminators must be a string or list of strings")


def _load_toml(path: str) -> dict[str, Any]:
    with Path(path).open("rb") as handle:
        return tomllib.load(handle)
