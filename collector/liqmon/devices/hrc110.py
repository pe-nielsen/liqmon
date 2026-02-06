from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from ..transports import Transport
from .base import Measurement


_DEFAULT_QUERY = "MEAS? 2"
_DEFAULT_WRITE_TERMINATOR = b"\r"
_DEFAULT_READ_TERMINATORS = [b"\r\n"]

_PRESSURE_REGEX = re.compile(
    r"^\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s+([A-Za-z/]+)\s+"
    r"([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*W",
)


@dataclass
class HRC110Device:
    id: str
    transport: Transport
    read_terminators: list[bytes]
    write_terminator: bytes = _DEFAULT_WRITE_TERMINATOR
    query: str = _DEFAULT_QUERY
    parse_regex: re.Pattern[str] = _PRESSURE_REGEX

    def open(self) -> None:
        self.transport.open()

    def close(self) -> None:
        self.transport.close()

    def poll(self, timestamp: datetime) -> list[Measurement]:
        payload = self.query.encode("ascii") + self.write_terminator
        raw = self.transport.query(payload, self.read_terminators)
        text = raw.decode("ascii", errors="replace").strip()
        match = self.parse_regex.search(text)
        if not match:
            raise ValueError(f"Unable to parse HRC-110 response: {text!r}")
        pressure = float(match.group(1))
        pressure_unit = match.group(2)
        heater_power = float(match.group(3))
        return [
            Measurement(
                metric="pressure",
                value=pressure,
                unit=pressure_unit,
                raw=text,
            ),
            Measurement(
                metric="heater_power",
                value=heater_power,
                unit="W",
                raw=text,
            ),
        ]


def hrc110_read_terminators() -> list[bytes]:
    return list(_DEFAULT_READ_TERMINATORS)
