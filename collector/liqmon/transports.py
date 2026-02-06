from __future__ import annotations

import socket
import time
from dataclasses import dataclass
from typing import Protocol

import serial


class Transport(Protocol):
    def open(self) -> None: ...

    def close(self) -> None: ...

    def query(self, payload: bytes, read_terminators: list[bytes]) -> bytes: ...


@dataclass(frozen=True)
class SerialSettings:
    port: str
    baudrate: int = 9600
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1
    timeout_s: float = 2.0
    write_timeout_s: float = 2.0


@dataclass(frozen=True)
class TcpSettings:
    host: str
    port: int
    timeout_s: float = 2.0


class SerialTransport:
    def __init__(self, settings: SerialSettings) -> None:
        self._settings = settings
        self._serial: serial.Serial | None = None

    def open(self) -> None:
        if self._serial is not None:
            return
        self._serial = serial.Serial(
            port=self._settings.port,
            baudrate=self._settings.baudrate,
            bytesize=self._settings.bytesize,
            parity=self._settings.parity,
            stopbits=self._settings.stopbits,
            timeout=self._settings.timeout_s,
            write_timeout=self._settings.write_timeout_s,
        )
        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()

    def close(self) -> None:
        if self._serial is None:
            return
        self._serial.close()
        self._serial = None

    def query(self, payload: bytes, read_terminators: list[bytes]) -> bytes:
        if self._serial is None:
            raise RuntimeError("Serial transport is not open")
        self._serial.write(payload)
        self._serial.flush()
        timeout_s = self._settings.timeout_s
        return _read_until_any(self._serial.read, read_terminators, timeout_s)


class TcpTransport:
    def __init__(self, settings: TcpSettings) -> None:
        self._settings = settings
        self._socket: socket.socket | None = None

    def open(self) -> None:
        if self._socket is not None:
            return
        self._socket = socket.create_connection(
            (self._settings.host, self._settings.port),
            timeout=self._settings.timeout_s,
        )
        self._socket.settimeout(0.5)

    def close(self) -> None:
        if self._socket is None:
            return
        self._socket.close()
        self._socket = None

    def query(self, payload: bytes, read_terminators: list[bytes]) -> bytes:
        if self._socket is None:
            raise RuntimeError("TCP transport is not open")
        self._socket.sendall(payload)
        return _read_until_any(_socket_read(self._socket), read_terminators, self._settings.timeout_s)


def _socket_read(sock: socket.socket):
    def _inner(size: int) -> bytes:
        try:
            return sock.recv(size)
        except socket.timeout:
            return b""
    return _inner


def _read_until_any(read_fn, terminators: list[bytes], timeout_s: float) -> bytes:
    if not terminators:
        raise ValueError("At least one read terminator is required")
    buffer = bytearray()
    start = time.monotonic()
    max_term = max(len(term) for term in terminators)
    while True:
        if time.monotonic() - start > timeout_s:
            raise TimeoutError("Timed out waiting for response terminator")
        chunk = read_fn(1)
        if not chunk:
            continue
        buffer += chunk
        if len(buffer) < max_term:
            continue
        for term in terminators:
            if buffer.endswith(term):
                return bytes(buffer[: -len(term)])
