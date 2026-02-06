from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class Measurement:
    metric: str
    value: float
    unit: str | None
    raw: str


class Device(Protocol):
    id: str

    def open(self) -> None: ...

    def close(self) -> None: ...

    def poll(self, timestamp: datetime) -> list[Measurement]: ...
