# liqmon

Poll laboratory instruments over serial or TCP and append readings to CSV.

Supported device types:

- `scm10` (temperature)
- `hrc110` (pressure and heater power)
- `cpa1114` (low/high compressor pressure via Modbus TCP)
- `helium_level` (Agilent E3647A heater PSU + Keithley 2000 4-wire resistance)

CPA1114 metrics written to CSV:

- `low_pressure`
- `high_pressure`

Helium level metrics written to CSV:

- `psu_voltage` (only when `heater_enabled = true`)
- `psu_current` (only when `heater_enabled = true`)
- `resistance_average`
- `liquid_helium_level`

## Quick start

1. Copy `monitor.example.toml` to `monitor.toml` and edit for your devices.
2. Run:

```bash
uv run liqmon-collector --config monitor.toml
```

If this command is not found, run `uv sync` in `collector/` once to install the packaged CLI entrypoint.

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
- `helium_level` uses `measurement_interval_s` instead of the global interval. With `heater_enabled = true`, it sets the PSU voltage/current limits, verifies them, briefly turns the output on, records PSU voltage/current, turns the PSU output off, and switches the Keithley back to DC voltage mode after each measurement attempt. With `heater_enabled = false`, it skips all PSU setup/output/current-voltage reads; `psu_port` can be omitted.
- `liquid_helium_level` is calculated as `total_sensor_length_cm - resistance_average / normal_state_linear_resistivity_ohm_per_cm`.

Example helium level configuration:

```toml
[[devices]]
id = "helium-level"
type = "helium_level"
transport = "serial"
measurement_interval_s = 3600
heater_enabled = true
total_sensor_length_cm = 140.0
normal_state_linear_resistivity_ohm_per_cm = 0.436
psu_port = "/dev/cu.usbserial-PSU"
dmm_port = "/dev/cu.usbserial-DMM"
psu_baudrate = 9600
dmm_baudrate = 9600
psu_channel = "OUT1"
psu_voltage_limit_v = 10.0
psu_current_limit_a = 0.1
dmm_range_ohm = 100.0
dmm_nplc = 1.0
resistance_readings = 3
reading_delay_s = 0.1
output_settle_s = 0.2
```

## Email alerts

Optional threshold alerts can be configured in `monitor.toml` under `[alerts]`.

- Alerts are evaluated in the collector immediately after each successful poll/write.
- `require_consecutive` controls how many out-of-range readings are required before triggering.
- `max_emails_per_day` rate-limits total alert emails.
- Rules are defined with `[[alerts.rules]]` by `device_id` + `metric` and `min`/`max` bounds.

SMTP configuration notes:

- Relay mode (no login), matching a simple `smtplib.SMTP(...).send_message(...)` flow:
  set `smtp_host`, optional `smtp_port` (defaults to `25`), `from`, and `to`.
- Authenticated mode: set both `username` and `password_env` (plus `use_starttls = true` if required by your provider).
- If using `password_env`, export it before starting the collector process.
