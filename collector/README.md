# liqmon

Poll laboratory instruments over serial or TCP and append readings to CSV.

Supported device types:

- `scm10` (temperature)
- `hrc110` (pressure and heater power)
- `cpa1114` (low/high compressor pressure via Modbus TCP)

CPA1114 metrics written to CSV:

- `low_pressure`
- `high_pressure`

## Quick start

1. Copy `liqmon.example.toml` to `liqmon.toml` and edit for your devices.
2. Run:

```bash
uv run liqmon --config liqmon.toml
```

## Output format

The CSV is append-only with columns:

- `timestamp`
- `device_id`
- `metric`
- `value`
- `unit`
- `raw`

Each measurement is a separate row, so devices that return multiple values (like pressure + heater power) will produce multiple rows per poll.

## Notes

- Device-specific command strings and terminators can be overridden per device.
- `cpa1114` supports `unit_id` (default `16`) and uses TCP port `502` by default.
- Set the TCP host/port and serial parameters to match each instrument.

## Email alerts

Optional threshold alerts can be configured in `liqmon.toml` under `[alerts]`.

- Alerts are evaluated in the collector immediately after each successful poll/write.
- `require_consecutive` controls how many out-of-range readings are required before triggering.
- `max_emails_per_day` rate-limits total alert emails.
- Rules are defined with `[[alerts.rules]]` by `device_id` + `metric` and `min`/`max` bounds.

Security recommendation:

- Keep SMTP passwords out of TOML and use `password_env` to read from an environment variable.
- Example: `export LIQMON_SMTP_PASSWORD='...'` before starting the collector process.
