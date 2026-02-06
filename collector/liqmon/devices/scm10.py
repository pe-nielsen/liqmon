from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from ..transports import Transport
from .base import Measurement


_DEFAULT_QUERY = "T?"
_DEFAULT_WRITE_TERMINATOR = b"\r"
_DEFAULT_SERIAL_READ_TERMINATORS = [b"\r"]
_DEFAULT_TCP_READ_TERMINATORS = [b"\r\n"]
_DEFAULT_REGEX = re.compile(r"^T\s+([-+]?[0-9]*\.?[0-9]+)")


@dataclass
class SCM10Device:
    id: str
    transport: Transport
    read_terminators: list[bytes]
    write_terminator: bytes = _DEFAULT_WRITE_TERMINATOR
    query: str = _DEFAULT_QUERY
    parse_regex: re.Pattern[str] = _DEFAULT_REGEX

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
            raise ValueError(f"Unable to parse SCM10 response: {text!r}")
        temperature = float(match.group(1))
        return [
            Measurement(
                metric="temperature",
                value=temperature,
                unit="K",
                raw=text,
            )
        ]


def scm10_read_terminators(transport: str) -> list[bytes]:
    if transport == "tcp":
        return list(_DEFAULT_TCP_READ_TERMINATORS)
    return list(_DEFAULT_SERIAL_READ_TERMINATORS)
