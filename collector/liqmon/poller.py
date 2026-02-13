from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from .alerts import AlertManager
from .devices.base import Device
from .storage import CsvSink


LOG = logging.getLogger("liqmon.poller")


@dataclass
class DeviceTask:
    device: Device
    interval_s: int
    sink: CsvSink
    next_poll: float = 0.0


class Poller:
    def __init__(
        self,
        tasks: list[DeviceTask],
        use_utc: bool,
        alert_manager: AlertManager | None = None,
    ) -> None:
        self._tasks = tasks
        self._use_utc = use_utc
        self._alert_manager = alert_manager

    def run(self) -> None:
        if not self._tasks:
            raise ValueError("No device tasks configured")
        self._open_all()
        try:
            now = time.monotonic()
            for task in self._tasks:
                task.next_poll = now
            while True:
                now = time.monotonic()
                for task in self._tasks:
                    if now < task.next_poll:
                        continue
                    self._poll_device(task)
                    while task.next_poll <= now:
                        task.next_poll += task.interval_s
                delay = min(task.next_poll for task in self._tasks) - time.monotonic()
                time.sleep(max(0.0, delay))
        finally:
            self._close_all()

    def _poll_device(self, task: DeviceTask) -> None:
        try:
            timestamp = self._timestamp()
            measurements = task.device.poll(timestamp)
            task.sink.write(timestamp, task.device.id, measurements)
            if self._alert_manager is not None:
                self._alert_manager.evaluate(timestamp, task.device.id, measurements)
            LOG.info("Recorded %s measurements from %s", len(measurements), task.device.id)
        except Exception:
            LOG.exception("Poll failed for %s", task.device.id)

    def _timestamp(self) -> datetime:
        if self._use_utc:
            return datetime.now(timezone.utc)
        return datetime.now().astimezone()

    def _open_all(self) -> None:
        for task in self._tasks:
            task.device.open()

    def _close_all(self) -> None:
        for task in self._tasks:
            task.device.close()
