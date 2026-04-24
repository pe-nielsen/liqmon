from __future__ import annotations

from typing import Any

from ..config import DeviceConfig, decode_terminator, decode_terminators
from ..transports import SerialSettings, SerialTransport, TcpSettings, TcpTransport
from .base import Device
from .cpa1114 import CPA1114Device
from .helium_level import HeliumLevelDevice, HeliumLevelSettings, SerialInstrumentSettings
from .hrc110 import HRC110Device, hrc110_read_terminators
from .scm10 import SCM10Device, scm10_read_terminators


def build_device(cfg: DeviceConfig) -> Device:
    if cfg.type.lower() == "cpa1114":
        return _build_cpa1114(cfg)
    if cfg.type.lower() in {"helium_level", "helium-level"}:
        return _build_helium_level(cfg)

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


def _build_helium_level(cfg: DeviceConfig) -> HeliumLevelDevice:
    if cfg.transport != "serial":
        raise ValueError("helium_level supports only serial transport")
    settings = cfg.settings
    heater_enabled = _bool_setting(settings.get("heater_enabled", True))
    psu_port = settings.get("psu_port")
    dmm_port = settings.get("dmm_port")
    if not dmm_port:
        raise ValueError("helium_level requires dmm_port")
    if heater_enabled and not psu_port:
        raise ValueError("helium_level requires psu_port when heater_enabled is true")
    resistance_readings = int(settings.get("resistance_readings", 3))
    if resistance_readings < 1:
        raise ValueError("helium_level resistance_readings must be >= 1")
    normal_state_linear_resistivity = float(
        settings.get("normal_state_linear_resistivity_ohm_per_cm", 0.436)
    )
    if normal_state_linear_resistivity <= 0:
        raise ValueError("helium_level normal_state_linear_resistivity_ohm_per_cm must be > 0")

    psu_settings = None
    if psu_port:
        psu_settings = _serial_instrument_settings(
            settings,
            prefix="psu",
            port=str(psu_port),
            default_write_terminator="\\n",
            default_read_terminators=["\\n"],
            default_rtscts=True,
            default_dsrdtr=True,
            default_command_delay_s=0.3,
        )
    dmm_settings = _serial_instrument_settings(
        settings,
        prefix="dmm",
        port=str(dmm_port),
        default_write_terminator="\\r",
        default_read_terminators=["\\r\\n", "\\n", "\\r"],
        default_rtscts=False,
        default_dsrdtr=False,
        default_command_delay_s=0.05,
    )
    return HeliumLevelDevice(
        id=cfg.id,
        settings=HeliumLevelSettings(
            psu=psu_settings,
            dmm=dmm_settings,
            heater_enabled=heater_enabled,
            total_sensor_length_cm=float(settings.get("total_sensor_length_cm", 140.0)),
            normal_state_linear_resistivity_ohm_per_cm=normal_state_linear_resistivity,
            psu_channel=str(settings.get("psu_channel", "OUT1")),
            psu_voltage_limit_v=float(settings.get("psu_voltage_limit_v", 10.0)),
            psu_current_limit_a=float(settings.get("psu_current_limit_a", 0.1)),
            dmm_range_ohm=float(settings.get("dmm_range_ohm", 100.0)),
            dmm_nplc=float(settings.get("dmm_nplc", 1.0)),
            resistance_readings=resistance_readings,
            reading_delay_s=float(settings.get("reading_delay_s", 0.1)),
            output_settle_s=float(settings.get("output_settle_s", 0.2)),
        ),
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


def _serial_instrument_settings(
    settings: dict[str, Any],
    prefix: str,
    port: str,
    default_write_terminator: str,
    default_read_terminators: list[str],
    default_rtscts: bool,
    default_dsrdtr: bool,
    default_command_delay_s: float,
) -> SerialInstrumentSettings:
    def get(name: str, default: Any) -> Any:
        return settings.get(f"{prefix}_{name}", settings.get(name, default))

    read_terminators = get("read_terminators", default_read_terminators)
    return SerialInstrumentSettings(
        port=port,
        baudrate=int(get("baudrate", 9600)),
        bytesize=int(get("bytesize", 8)),
        parity=str(get("parity", "N")),
        stopbits=float(get("stopbits", 1)),
        timeout_s=float(get("timeout_s", 3.0)),
        write_timeout_s=float(get("write_timeout_s", 2.0)),
        xonxoff=_bool_setting(get("xonxoff", False)),
        rtscts=_bool_setting(get("rtscts", default_rtscts)),
        dsrdtr=_bool_setting(get("dsrdtr", default_dsrdtr)),
        write_terminator=decode_terminator(str(get("write_terminator", default_write_terminator))),
        read_terminators=decode_terminators(read_terminators),
        command_delay_s=float(get("command_delay_s", default_command_delay_s)),
    )


def _bool_setting(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return bool(value)


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
