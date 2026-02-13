from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass
from datetime import date, datetime
from email.message import EmailMessage
from typing import Protocol

from .config import AlertRuleConfig, AlertsConfig, AppConfig, EmailAlertConfig
from .devices.base import Measurement


LOG = logging.getLogger("liqmon.alerts")


class Notifier(Protocol):
    def notify(self, event: "AlertEvent") -> None: ...


@dataclass(frozen=True)
class AlertEvent:
    timestamp: datetime
    rule: AlertRuleConfig
    measurement: Measurement
    device_id: str


@dataclass
class _RuleState:
    consecutive_violations: int = 0
    in_alert: bool = False


class EmailNotifier:
    def __init__(self, cfg: EmailAlertConfig) -> None:
        self._cfg = cfg

    def notify(self, event: AlertEvent) -> None:
        password = os.getenv(self._cfg.password_env)
        if not password:
            raise ValueError(
                f"Environment variable {self._cfg.password_env!r} is not set; cannot send alert email"
            )

        msg = EmailMessage()
        msg["From"] = self._cfg.sender
        msg["To"] = ", ".join(self._cfg.recipients)
        msg["Subject"] = f"liqmon alert: {event.device_id} {event.measurement.metric} out of range"
        msg.set_content(_build_email_body(event))

        with smtplib.SMTP(self._cfg.smtp_host, self._cfg.smtp_port, timeout=20) as smtp:
            smtp.ehlo()
            if self._cfg.use_starttls:
                smtp.starttls()
                smtp.ehlo()
            smtp.login(self._cfg.username, password)
            smtp.send_message(msg)


class AlertManager:
    def __init__(
        self,
        rules: list[AlertRuleConfig],
        notifiers: list[Notifier],
        require_consecutive: int = 2,
        max_emails_per_day: int = 1,
    ) -> None:
        self._rules_by_key: dict[tuple[str, str], list[AlertRuleConfig]] = {}
        for rule in rules:
            self._rules_by_key.setdefault((rule.device_id, rule.metric), []).append(rule)
        self._notifiers = notifiers
        self._require_consecutive = require_consecutive
        self._max_emails_per_day = max_emails_per_day
        self._state_by_rule_id: dict[str, _RuleState] = {rule.id: _RuleState() for rule in rules}
        self._sent_count_by_date: dict[date, int] = {}

    def evaluate(
        self, timestamp: datetime, device_id: str, measurements: list[Measurement]
    ) -> None:
        for measurement in measurements:
            rules = self._rules_by_key.get((device_id, measurement.metric), [])
            if not rules:
                continue
            for rule in rules:
                self._evaluate_rule(timestamp, device_id, measurement, rule)

    def _evaluate_rule(
        self,
        timestamp: datetime,
        device_id: str,
        measurement: Measurement,
        rule: AlertRuleConfig,
    ) -> None:
        state = self._state_by_rule_id[rule.id]
        if _is_out_of_bounds(measurement.value, rule.min_value, rule.max_value):
            state.consecutive_violations += 1
            if state.in_alert:
                return
            if state.consecutive_violations < self._require_consecutive:
                return
            state.in_alert = True
            self._dispatch(AlertEvent(timestamp, rule, measurement, device_id))
            return

        state.consecutive_violations = 0
        state.in_alert = False

    def _dispatch(self, event: AlertEvent) -> None:
        day = event.timestamp.date()
        already_sent = self._sent_count_by_date.get(day, 0)
        if already_sent >= self._max_emails_per_day:
            LOG.warning(
                "Alert suppressed by max_emails_per_day=%s: %s %s (value=%s)",
                self._max_emails_per_day,
                event.device_id,
                event.measurement.metric,
                event.measurement.value,
            )
            return

        for notifier in self._notifiers:
            notifier.notify(event)
        self._sent_count_by_date[day] = already_sent + 1
        LOG.warning(
            "Alert sent for %s %s (value=%s, rule=%s)",
            event.device_id,
            event.measurement.metric,
            event.measurement.value,
            event.rule.id,
        )


def build_alert_manager(cfg: AppConfig) -> AlertManager | None:
    alerts_cfg = cfg.alerts
    if alerts_cfg is None or not alerts_cfg.enabled:
        return None

    notifiers = _build_notifiers(alerts_cfg)
    if not notifiers:
        LOG.warning("Alerts enabled but no notifiers configured; alerts will be disabled")
        return None
    return AlertManager(
        rules=alerts_cfg.rules,
        notifiers=notifiers,
        require_consecutive=alerts_cfg.require_consecutive,
        max_emails_per_day=alerts_cfg.max_emails_per_day,
    )


def _build_notifiers(cfg: AlertsConfig) -> list[Notifier]:
    notifiers: list[Notifier] = []
    if cfg.email is not None:
        notifiers.append(EmailNotifier(cfg.email))
    return notifiers


def _is_out_of_bounds(value: float, min_value: float | None, max_value: float | None) -> bool:
    if min_value is not None and value < min_value:
        return True
    if max_value is not None and value > max_value:
        return True
    return False


def _build_email_body(event: AlertEvent) -> str:
    min_text = "unset" if event.rule.min_value is None else str(event.rule.min_value)
    max_text = "unset" if event.rule.max_value is None else str(event.rule.max_value)
    unit = event.rule.unit or event.measurement.unit or ""
    return (
        "liqmon alert\n\n"
        f"timestamp: {event.timestamp.isoformat()}\n"
        f"device_id: {event.device_id}\n"
        f"metric: {event.measurement.metric}\n"
        f"value: {event.measurement.value} {unit}\n"
        f"allowed range: min={min_text} max={max_text} {unit}\n"
        f"rule_id: {event.rule.id}\n"
        f"raw: {event.measurement.raw}\n"
    )
