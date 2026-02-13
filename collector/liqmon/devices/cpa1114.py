from __future__ import annotations

import socket
from dataclasses import dataclass
from datetime import datetime

from .base import Measurement


_DEFAULT_PORT = 502
_DEFAULT_UNIT_ID = 16
_DEFAULT_TIMEOUT_S = 2.0

_PRESSURE_SCALE_UNITS = {
    0: "psi",
    1: "bar",
    2: "kPa",
}


@dataclass
class CPA1114Device:
    id: str
    host: str
    port: int = _DEFAULT_PORT
    unit_id: int = _DEFAULT_UNIT_ID
    timeout_s: float = _DEFAULT_TIMEOUT_S

    def __post_init__(self) -> None:
        self._socket: socket.socket | None = None
        self._transaction_id = 0

    def open(self) -> None:
        if self._socket is not None:
            return
        self._socket = socket.create_connection((self.host, self.port), timeout=self.timeout_s)
        self._socket.settimeout(self.timeout_s)

    def close(self) -> None:
        if self._socket is None:
            return
        self._socket.close()
        self._socket = None

    def poll(self, timestamp: datetime) -> list[Measurement]:
        del timestamp
        try:
            registers = self._read_input_registers(start_register=29, count=18)
        except Exception:
            self.close()
            raise

        pressure_scale = registers[0]
        low_pressure = registers[15] / 10.0
        high_pressure = registers[17] / 10.0
        unit = _PRESSURE_SCALE_UNITS.get(pressure_scale, "")

        raw = (
            f"scale={pressure_scale},"
            f"low_raw={registers[15]},high_raw={registers[17]},"
            f"low={low_pressure},high={high_pressure}"
        )
        return [
            Measurement(metric="low_pressure", value=low_pressure, unit=unit, raw=raw),
            Measurement(metric="high_pressure", value=high_pressure, unit=unit, raw=raw),
        ]

    def _read_input_registers(self, start_register: int, count: int) -> list[int]:
        if self._socket is None:
            self.open()
        if self._socket is None:
            raise RuntimeError("CPA1114 socket is not open")

        self._transaction_id = (self._transaction_id + 1) & 0xFFFF
        # Manual register mapping is 1-based relative to 30000 (30001 -> address 1).
        register_address = start_register
        pdu = bytes(
            [
                0x04,  # Read Input Registers
                (register_address >> 8) & 0xFF,
                register_address & 0xFF,
                (count >> 8) & 0xFF,
                count & 0xFF,
            ]
        )
        mbap = (
            self._transaction_id.to_bytes(2, "big")
            + b"\x00\x00"  # protocol id
            + (len(pdu) + 1).to_bytes(2, "big")
            + bytes([self.unit_id])
        )
        self._socket.sendall(mbap + pdu)

        header = _recv_exact(self._socket, 7)
        transaction_id = int.from_bytes(header[0:2], "big")
        protocol_id = int.from_bytes(header[2:4], "big")
        length = int.from_bytes(header[4:6], "big")
        unit_id = header[6]

        if protocol_id != 0:
            raise ValueError(f"Unexpected Modbus protocol id: {protocol_id}")
        if transaction_id != self._transaction_id:
            raise ValueError(
                f"Transaction mismatch: expected {self._transaction_id}, got {transaction_id}"
            )
        if unit_id != self.unit_id:
            raise ValueError(f"Unit id mismatch: expected {self.unit_id}, got {unit_id}")

        payload = _recv_exact(self._socket, length - 1)
        if not payload:
            raise ValueError("Empty Modbus payload")

        function_code = payload[0]
        if function_code == 0x84:
            exception_code = payload[1] if len(payload) > 1 else None
            raise ValueError(f"Modbus exception response: code={exception_code}")
        if function_code != 0x04:
            raise ValueError(f"Unexpected function code: {function_code}")

        byte_count = payload[1]
        register_bytes = payload[2:]
        expected_bytes = count * 2
        if byte_count != expected_bytes or len(register_bytes) != expected_bytes:
            raise ValueError(
                f"Unexpected register payload length: expected {expected_bytes}, got {len(register_bytes)}"
            )

        registers: list[int] = []
        for idx in range(0, len(register_bytes), 2):
            registers.append(int.from_bytes(register_bytes[idx : idx + 2], "big"))
        return registers


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("Connection closed while reading Modbus response")
        data.extend(chunk)
    return bytes(data)
