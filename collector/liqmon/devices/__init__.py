from __future__ import annotations

from typing import Any

from ..config import DeviceConfig, decode_terminator, decode_terminators
from ..transports import SerialSettings, SerialTransport, TcpSettings, TcpTransport
from .base import Device
from .cpa1114 import CPA1114Device
from .hrc110 import HRC110Device, hrc110_read_terminators
from .scm10 import SCM10Device, scm10_read_terminators


def build_device(cfg: DeviceConfig) -> Device:
    if cfg.type.lower() == "cpa1114":
        return _build_cpa1114(cfg)

    transport = _build_transport(cfg.transport, cfg.settings)
    if cfg.type.lower() == "scm10":
        return _build_scm10(cfg, transport)
    if cfg.type.lower() == "hrc110":
        return _build_hrc110(cfg, transport)
    raise ValueError(f"Unsupported device type: {cfg.type}")


def _build_transport(transport: str, settings: dict[str, Any]):
    if transport == "serial":
        return SerialTransport(_serial_settings(settings))
    if transport == "tcp":
        return TcpTransport(_tcp_settings(settings))
    raise ValueError(f"Unsupported transport: {transport}")


def _build_cpa1114(cfg: DeviceConfig) -> CPA1114Device:
    if cfg.transport != "tcp":
        raise ValueError("CPA1114 supports only tcp transport")
    tcp = _tcp_settings(cfg.settings)
    unit_id = int(cfg.settings.get("unit_id", 16))
    return CPA1114Device(
        id=cfg.id,
        host=tcp.host,
        port=tcp.port,
        unit_id=unit_id,
        timeout_s=tcp.timeout_s,
    )


def _build_scm10(cfg: DeviceConfig, transport) -> SCM10Device:
    write_terminator = decode_terminator(cfg.settings.get("write_terminator", "\\r"))
    read_terminators = cfg.settings.get("read_terminators")
    if read_terminators is None:
        read_terminators = scm10_read_terminators(cfg.transport)
    else:
        read_terminators = decode_terminators(read_terminators)
    query = cfg.settings.get("query", "T?")
    return SCM10Device(
        id=cfg.id,
        transport=transport,
        read_terminators=list(read_terminators),
        write_terminator=write_terminator,
        query=str(query),
    )


def _build_hrc110(cfg: DeviceConfig, transport) -> HRC110Device:
    write_terminator = decode_terminator(cfg.settings.get("write_terminator", "\\r"))
    read_terminators = cfg.settings.get("read_terminators")
    if read_terminators is None:
        read_terminators = hrc110_read_terminators()
    else:
        read_terminators = decode_terminators(read_terminators)
    channel = cfg.settings.get("channel", 2)
    query = cfg.settings.get("query", f"MEAS? {channel}")
    return HRC110Device(
        id=cfg.id,
        transport=transport,
        read_terminators=list(read_terminators),
        write_terminator=write_terminator,
        query=str(query),
    )


def _serial_settings(settings: dict[str, Any]) -> SerialSettings:
    port = settings.get("port")
    if not port:
        raise ValueError("Serial transport requires 'port'")
    return SerialSettings(
        port=str(port),
        baudrate=int(settings.get("baudrate", 9600)),
        bytesize=int(settings.get("bytesize", 8)),
        parity=str(settings.get("parity", "N")),
        stopbits=float(settings.get("stopbits", 1)),
        timeout_s=float(settings.get("timeout_s", 2.0)),
        write_timeout_s=float(settings.get("write_timeout_s", 2.0)),
    )


def _tcp_settings(settings: dict[str, Any]) -> TcpSettings:
    host = settings.get("host")
    port = settings.get("port")
    if not host or port is None:
        raise ValueError("TCP transport requires 'host' and 'port'")
    return TcpSettings(
        host=str(host),
        port=int(port),
        timeout_s=float(settings.get("timeout_s", 2.0)),
    )
