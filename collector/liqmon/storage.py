from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import datetime

from .devices.base import Measurement


@dataclass(frozen=True)
class CsvSink:
    path: str

    def __post_init__(self) -> None:
        _ensure_csv_header(self.path)

    def write(self, timestamp: datetime, device_id: str, measurements: list[Measurement]) -> None:
        if not measurements:
            return
        with open(self.path, "a", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS)
            for measurement in measurements:
                writer.writerow(
                    {
                        "timestamp": timestamp.isoformat(),
                        "device_id": device_id,
                        "metric": measurement.metric,
                        "value": measurement.value,
                        "unit": measurement.unit or "",
                        "raw": measurement.raw,
                    }
                )


def _ensure_csv_header(path: str) -> None:
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS)
        writer.writeheader()


_CSV_FIELDS = ["timestamp", "device_id", "metric", "value", "unit", "raw"]
