from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime
from statistics import mean

import serial

from .base import Measurement


_OVERRANGE_THRESHOLD = 1e30


@dataclass(frozen=True)
class SerialInstrumentSettings:
    port: str
    baudrate: int = 9600
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1
    timeout_s: float = 3.0
    write_timeout_s: float = 2.0
    xonxoff: bool = False
    rtscts: bool = False
    dsrdtr: bool = False
    write_terminator: bytes = b"\n"
    read_terminators: list[bytes] | None = None
    command_delay_s: float = 0.05


@dataclass(frozen=True)
class HeliumLevelSettings:
    dmm: SerialInstrumentSettings
    psu: SerialInstrumentSettings | None = None
    heater_enabled: bool = True
    total_sensor_length_cm: float = 140.0
    normal_state_linear_resistivity_ohm_per_cm: float = 0.436
    psu_channel: str = "OUT1"
    psu_voltage_limit_v: float = 10.0
    psu_current_limit_a: float = 0.1
    dmm_range_ohm: float = 100.0
    dmm_nplc: float = 1.0
    resistance_readings: int = 3
    reading_delay_s: float = 0.1
    output_settle_s: float = 0.2


class HeliumLevelDevice:
    def __init__(self, id: str, settings: HeliumLevelSettings) -> None:
        self.id = id
        self._settings = settings
        self._psu = _SerialScpi(settings.psu) if settings.psu is not None else None
        self._dmm = _SerialScpi(settings.dmm)

    def open(self) -> None:
        try:
            if self._psu is not None:
                self._psu.open()
            self._dmm.open()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        self._dmm.close()
        if self._psu is not None:
            self._psu.close()

    def poll(self, timestamp: datetime) -> list[Measurement]:
        del timestamp
        voltage_v: float | None = None
        current_a: float | None = None
        readings: list[float] = []
        measurement_error: Exception | None = None

        try:
            if self._settings.heater_enabled:
                self._configure_psu()
            self._configure_dmm()
            if self._settings.heater_enabled:
                self._verify_psu_settings()
            self._verify_dmm_settings()

            if self._settings.heater_enabled:
                psu = self._require_psu()
                psu.write("OUTP ON", delay_s=0.1)
                time.sleep(self._settings.output_settle_s)

                voltage_v = self._query_float(psu, "MEAS:VOLT?")
                current_a = self._query_float(psu, "MEAS:CURR?")
            readings = self._read_resistances()
        except Exception as exc:
            measurement_error = exc

        shutdown_errors = self._safe_shutdown()
        if shutdown_errors:
            if measurement_error is not None:
                raise RuntimeError(
                    "Helium level measurement failed and shutdown also reported "
                    f"errors: measurement={measurement_error!r}; shutdown={shutdown_errors!r}"
                ) from shutdown_errors[0]
            raise RuntimeError(f"Failed to shut down helium level instruments: {shutdown_errors!r}")
        if measurement_error is not None:
            raise measurement_error

        if not readings:
            raise RuntimeError("No valid Keithley resistance readings")

        average_ohm = mean(readings)
        liquid_helium_level_cm = (
            self._settings.total_sensor_length_cm
            - average_ohm / self._settings.normal_state_linear_resistivity_ohm_per_cm
        )
        raw = json.dumps(
            {
                "heater_enabled": self._settings.heater_enabled,
                "psu_voltage_v": voltage_v,
                "psu_current_a": current_a,
                "resistance_readings_ohm": readings,
                "resistance_average_ohm": average_ohm,
                "total_sensor_length_cm": self._settings.total_sensor_length_cm,
                "normal_state_linear_resistivity_ohm_per_cm": (
                    self._settings.normal_state_linear_resistivity_ohm_per_cm
                ),
                "liquid_helium_level_cm": liquid_helium_level_cm,
            },
            separators=(",", ":"),
        )
        measurements = [
            Measurement("resistance_average", average_ohm, "ohm", raw),
            Measurement("liquid_helium_level", liquid_helium_level_cm, "cm", raw),
        ]
        if self._settings.heater_enabled:
            measurements = [
                Measurement("psu_voltage", voltage_v if voltage_v is not None else math.nan, "V", raw),
                Measurement("psu_current", current_a if current_a is not None else math.nan, "A", raw),
                *measurements,
            ]
        return measurements

    def _configure_psu(self) -> None:
        psu = self._require_psu()
        psu.write("*CLS")
        psu.write("SYST:REM")
        psu.write(f"INST:SEL {self._settings.psu_channel}")
        psu.write(f"VOLT {self._settings.psu_voltage_limit_v}")
        psu.write(f"CURR {self._settings.psu_current_limit_a}")

    def _configure_dmm(self) -> None:
        self._dmm.write("*CLS")
        self._dmm.write(":SYST:REM")
        self._dmm.write(":INIT:CONT OFF")
        self._dmm.write(":ABOR")
        self._dmm.write(":FUNC 'FRES'")
        self._dmm.write(":FRES:RANG:AUTO OFF")
        self._dmm.write(f":FRES:RANG {self._settings.dmm_range_ohm}")
        self._dmm.write(f":FRES:NPLC {self._settings.dmm_nplc}")
        self._dmm.write(":SAMP:COUN 1")
        self._dmm.write(":TRIG:SOUR IMM")

    def _verify_psu_settings(self) -> None:
        psu = self._require_psu()
        voltage_limit = self._query_float(psu, "VOLT?")
        current_limit = self._query_float(psu, "CURR?")
        _assert_close(
            "PSU voltage limit",
            voltage_limit,
            self._settings.psu_voltage_limit_v,
            rel_tol=0.02,
            abs_tol=0.05,
        )
        _assert_close(
            "PSU current limit",
            current_limit,
            self._settings.psu_current_limit_a,
            rel_tol=0.02,
            abs_tol=0.005,
        )

    def _verify_dmm_settings(self) -> None:
        function = self._dmm.query(":FUNC?").strip().upper().replace('"', "'")
        if "FRES" not in function:
            raise RuntimeError(f"Keithley function is not FRES: {function!r}")

        auto_range = self._dmm.query(":FRES:RANG:AUTO?").strip()
        if _parse_bool_reply(auto_range):
            raise RuntimeError("Keithley FRES autorange is still enabled")

        continuous_init = self._dmm.query(":INIT:CONT?").strip()
        if _parse_bool_reply(continuous_init):
            raise RuntimeError("Keithley continuous initiation is still enabled")

        sample_count = self._query_float(self._dmm, ":SAMP:COUN?")
        _assert_close(
            "Keithley sample count",
            sample_count,
            1.0,
            rel_tol=0.0,
            abs_tol=0.0,
        )

        range_ohm = self._query_float(self._dmm, ":FRES:RANG?")
        _assert_close(
            "Keithley FRES range",
            range_ohm,
            self._settings.dmm_range_ohm,
            rel_tol=0.02,
            abs_tol=0.05,
        )

    def _read_resistances(self) -> list[float]:
        readings: list[float] = []
        for _ in range(self._settings.resistance_readings):
            value = self._query_float(self._dmm, ":READ?")
            if abs(value) <= _OVERRANGE_THRESHOLD:
                readings.append(value)
            time.sleep(self._settings.reading_delay_s)
        return readings

    def _safe_shutdown(self) -> list[Exception]:
        errors: list[Exception] = []
        if self._settings.heater_enabled and self._psu is not None:
            try:
                self._psu.write("OUTP OFF", delay_s=0.1)
            except Exception as exc:
                errors.append(exc)
        try:
            self._dmm.write(":FUNC 'VOLT:DC'", delay_s=0.1)
        except Exception as exc:
            errors.append(exc)
        return errors

    def _require_psu(self) -> _SerialScpi:
        if self._psu is None:
            raise RuntimeError("PSU is not configured")
        return self._psu

    @staticmethod
    def _query_float(instrument: _SerialScpi, command: str) -> float:
        reply = instrument.query(command)
        try:
            return float(reply)
        except ValueError as exc:
            raise RuntimeError(f"Could not parse numeric reply {reply!r} from {command}") from exc


class _SerialScpi:
    def __init__(self, settings: SerialInstrumentSettings) -> None:
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
            xonxoff=self._settings.xonxoff,
            rtscts=self._settings.rtscts,
            dsrdtr=self._settings.dsrdtr,
        )
        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()

    def close(self) -> None:
        if self._serial is None:
            return
        self._serial.close()
        self._serial = None

    def write(self, command: str, delay_s: float | None = None) -> None:
        if self._serial is None:
            raise RuntimeError("Serial instrument is not open")
        self._serial.write(command.encode("ascii") + self._settings.write_terminator)
        self._serial.flush()
        time.sleep(self._settings.command_delay_s if delay_s is None else delay_s)

    def query(self, command: str) -> str:
        if self._serial is None:
            raise RuntimeError("Serial instrument is not open")
        self.write(command)
        terminators = self._settings.read_terminators or [b"\n"]
        raw = _read_until_any(self._serial.read, terminators, self._settings.timeout_s)
        return raw.decode("ascii", errors="replace").strip()


def _read_until_any(read_fn, terminators: list[bytes], timeout_s: float) -> bytes:
    buffer = bytearray()
    start = time.monotonic()
    max_term = max(len(term) for term in terminators)
    while True:
        if time.monotonic() - start > timeout_s:
            if buffer:
                return bytes(buffer)
            raise TimeoutError("Timed out waiting for serial instrument response")
        chunk = read_fn(1)
        if not chunk:
            continue
        buffer += chunk
        if len(buffer) < max_term:
            continue
        for term in terminators:
            if buffer.endswith(term):
                return bytes(buffer[: -len(term)])


def _assert_close(
    name: str,
    actual: float,
    expected: float,
    rel_tol: float,
    abs_tol: float,
) -> None:
    if not math.isclose(actual, expected, rel_tol=rel_tol, abs_tol=abs_tol):
        raise RuntimeError(f"{name} is {actual}, expected {expected}")


def _parse_bool_reply(value: str) -> bool:
    normalized = value.strip().upper()
    return normalized in {"1", "ON", "TRUE"}
