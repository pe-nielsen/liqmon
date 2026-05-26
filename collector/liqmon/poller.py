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
    connection_label: str
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
        try:
            self._open_all()
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
            LOG.exception(
                "Poll failed for %s using %s. Check the instrument is powered on, "
                "connected, and that monitor.toml has the correct serial port or "
                "network address.",
                task.device.id,
                task.connection_label,
            )

    def _timestamp(self) -> datetime:
        if self._use_utc:
            return datetime.now(timezone.utc)
        return datetime.now().astimezone()

    def _open_all(self) -> None:
        for task in self._tasks:
            try:
                LOG.info("Opening %s using %s", task.device.id, task.connection_label)
                task.device.open()
            except Exception as exc:
                raise RuntimeError(
                    f"Could not connect to {task.device.id} using "
                    f"{task.connection_label}. Check the instrument is powered on, "
                    "connected, and that monitor.toml has the correct serial port "
                    "or network address."
                ) from exc

    def _close_all(self) -> None:
        for task in self._tasks:
            try:
                task.device.close()
            except Exception:
                LOG.exception("Failed to close %s cleanly", task.device.id)
