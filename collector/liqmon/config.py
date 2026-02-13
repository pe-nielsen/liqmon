from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GlobalConfig:
    interval_s: int
    output: str
    utc: bool


@dataclass(frozen=True)
class DeviceConfig:
    id: str
    type: str
    transport: str
    settings: dict[str, Any]
    interval_s: int | None
    output: str | None


@dataclass(frozen=True)
class EmailAlertConfig:
    smtp_host: str
    smtp_port: int
    use_starttls: bool
    username: str
    password_env: str
    sender: str
    recipients: list[str]


@dataclass(frozen=True)
class AlertRuleConfig:
    id: str
    device_id: str
    metric: str
    min_value: float | None
    max_value: float | None
    unit: str | None


@dataclass(frozen=True)
class AlertsConfig:
    enabled: bool
    require_consecutive: int
    max_emails_per_day: int
    email: EmailAlertConfig | None
    rules: list[AlertRuleConfig]


@dataclass(frozen=True)
class AppConfig:
    global_config: GlobalConfig
    devices: list[DeviceConfig]
    alerts: AlertsConfig | None


def load_config(path: str) -> AppConfig:
    data = _load_toml(path)
    global_section = data.get("global", {})
    global_cfg = GlobalConfig(
        interval_s=int(global_section.get("interval_s", 60)),
        output=str(global_section.get("output", "data/readings.csv")),
        utc=bool(global_section.get("utc", False)),
    )

    devices = []
    for entry in data.get("devices", []):
        device_id = entry.get("id")
        device_type = entry.get("type")
        transport = entry.get("transport")
        if not device_id or not device_type or not transport:
            raise ValueError("Each device must include id, type, and transport")
        interval_s = entry.get("interval_s")
        output = entry.get("output")
        settings = {k: v for k, v in entry.items() if k not in {"id", "type", "transport", "interval_s", "output"}}
        devices.append(
            DeviceConfig(
                id=str(device_id),
                type=str(device_type),
                transport=str(transport),
                settings=settings,
                interval_s=int(interval_s) if interval_s is not None else None,
                output=str(output) if output is not None else None,
            )
        )

    if not devices:
        raise ValueError("No devices defined in config")

    alerts_cfg = _parse_alerts(data.get("alerts"))
    return AppConfig(global_config=global_cfg, devices=devices, alerts=alerts_cfg)


def decode_terminator(value: str) -> bytes:
    decoded = value.encode("utf-8").decode("unicode_escape")
    return decoded.encode("ascii")


def decode_terminators(value: Any) -> list[bytes]:
    if isinstance(value, list):
        return [decode_terminator(str(item)) for item in value]
    if isinstance(value, str):
        return [decode_terminator(value)]
    raise ValueError("read_terminators must be a string or list of strings")


def _load_toml(path: str) -> dict[str, Any]:
    with Path(path).open("rb") as handle:
        return tomllib.load(handle)


def _parse_alerts(section: Any) -> AlertsConfig | None:
    if section is None:
        return None
    if not isinstance(section, dict):
        raise ValueError("alerts must be a table")

    enabled = bool(section.get("enabled", False))
    require_consecutive = int(section.get("require_consecutive", 2))
    max_emails_per_day = int(section.get("max_emails_per_day", 1))
    if require_consecutive < 1:
        raise ValueError("alerts.require_consecutive must be >= 1")
    if max_emails_per_day < 1:
        raise ValueError("alerts.max_emails_per_day must be >= 1")

    email_cfg = _parse_alert_email(section.get("email"))
    rules = _parse_alert_rules(section.get("rules", []))
    if enabled and not rules:
        raise ValueError("alerts.enabled=true requires at least one [[alerts.rules]] entry")
    if enabled and email_cfg is None:
        raise ValueError("alerts.enabled=true requires [alerts.email]")

    return AlertsConfig(
        enabled=enabled,
        require_consecutive=require_consecutive,
        max_emails_per_day=max_emails_per_day,
        email=email_cfg,
        rules=rules,
    )


def _parse_alert_email(section: Any) -> EmailAlertConfig | None:
    if section is None:
        return None
    if not isinstance(section, dict):
        raise ValueError("alerts.email must be a table")

    smtp_host = section.get("smtp_host")
    username = section.get("username")
    password_env = section.get("password_env")
    sender = section.get("from")
    recipients = section.get("to")
    if not smtp_host or not username or not password_env or not sender or not recipients:
        raise ValueError(
            "alerts.email requires smtp_host, username, password_env, from, and to"
        )
    if not isinstance(recipients, list):
        raise ValueError("alerts.email.to must be a list of email addresses")

    recipients_clean = [str(addr) for addr in recipients if str(addr).strip()]
    if not recipients_clean:
        raise ValueError("alerts.email.to must include at least one email address")

    return EmailAlertConfig(
        smtp_host=str(smtp_host),
        smtp_port=int(section.get("smtp_port", 587)),
        use_starttls=bool(section.get("use_starttls", True)),
        username=str(username),
        password_env=str(password_env),
        sender=str(sender),
        recipients=recipients_clean,
    )


def _parse_alert_rules(entries: Any) -> list[AlertRuleConfig]:
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise ValueError("alerts.rules must be an array of tables")

    rules: list[AlertRuleConfig] = []
    seen_rule_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each alerts.rules entry must be a table")
        rule_id = entry.get("id")
        device_id = entry.get("device_id")
        metric = entry.get("metric")
        if not rule_id or not device_id or not metric:
            raise ValueError("Each alerts.rules entry requires id, device_id, and metric")
        if str(rule_id) in seen_rule_ids:
            raise ValueError(f"Duplicate alerts rule id: {rule_id!r}")
        seen_rule_ids.add(str(rule_id))

        min_raw = entry.get("min")
        max_raw = entry.get("max")
        min_value = float(min_raw) if min_raw is not None else None
        max_value = float(max_raw) if max_raw is not None else None
        if min_value is None and max_value is None:
            raise ValueError(f"alerts rule {rule_id!r} must set min and/or max")

        unit_raw = entry.get("unit")
        rules.append(
            AlertRuleConfig(
                id=str(rule_id),
                device_id=str(device_id),
                metric=str(metric),
                min_value=min_value,
                max_value=max_value,
                unit=str(unit_raw) if unit_raw is not None else None,
            )
        )
    return rules
