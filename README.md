# Liquid helium monitoring

This app records live readings from the cryostat instruments and shows them in a
browser dashboard.

It has two parts:

- `collector`: connects to the instruments and writes readings to a CSV file.
- `dashboard`: reads that CSV file and shows live graphs.

The dashboard currently shows:

- Liquefier cold head temperature
- Liquefier pressure and heater power
- Compressor pressures
- Liquid helium level sensor readings

The app uses CSV data files. SQLite data files are not supported by this version.

## Before You Start

You need:

- Python 3.13 or newer
- `uv`, used to run the Python commands
- Access to the lab instruments over serial or network connections

If the commands below fail with a message about `uv` or a missing command, ask
the system maintainer to check the Python/uv installation.

## Run The App

You normally need two terminal windows: one for collecting data and one for the
dashboard.

### 1. Start The Collector

Open a terminal in this project folder, then run:

```bash
cd collector
uv run liqmon-collector --config monitor.toml
```

The collector reads `monitor.toml`, connects to the configured instruments, and
writes readings to:

```text
collector/data/readings.csv
```

Leave this terminal running while you want data to be collected.

### 2. Start The Dashboard

Open a second terminal in this project folder, then run:

```bash
cd dashboard
uv run liqmon-dashboard --csv ../collector/data/readings.csv
```

Then open this address in a web browser:

```text
http://127.0.0.1:8050
```

Leave this terminal running while you want the dashboard to stay available.

## First-Time Setup

If `collector/monitor.toml` does not exist yet, create it from the example file:

```bash
cd collector
cp monitor.example.toml monitor.toml
```

Then edit `monitor.toml` before starting the collector.

If `uv run liqmon-collector ...` or `uv run liqmon-dashboard ...` is not found,
run this once in the matching folder:

```bash
uv sync
```

For example, run `uv sync` inside `collector/` for the collector command, or
inside `dashboard/` for the dashboard command.

## Changing The Configuration

Most routine changes are made in:

```text
collector/monitor.toml
```

TOML files are plain text files. Lines beginning with `#` are comments and are
ignored by the app.

After changing `monitor.toml`, stop the collector with `Ctrl+C` and start it
again. The dashboard usually does not need to be restarted unless the CSV path
changes.

### Global Settings

The `[global]` section controls general collector behaviour:

```toml
[global]
interval_s = 60
output = "data/readings.csv"
utc = true
```

- `interval_s`: default time between readings, in seconds.
- `output`: CSV file written by the collector.
- `utc`: when `true`, timestamps are written in UTC.

Keep `output = "data/readings.csv"` unless you have a specific reason to change
it. If you do change it, also update the `--csv` path used when starting the
dashboard.

### Device Settings

Each instrument is configured in a `[[devices]]` block:

```toml
[[devices]]
id = "scm10-eth"
type = "scm10"
transport = "tcp"
host = "192.168.0.4"
port = 9760
```

Common fields:

- `id`: a short unique name for the device.
- `type`: the kind of device. Supported values are `scm10`, `hrc110`, `cpa1114`,
  and `helium_level`.
- `transport`: how the app connects. Use `tcp` for network devices and `serial`
  for serial/USB devices.
- `host` and `port`: network address for `tcp` devices.
- `port`: serial device path for `serial` devices, such as `/dev/ttyUSB0`.
- `interval_s`: optional per-device reading interval, in seconds.

Be careful when changing `type`, `transport`, `host`, or `port`. A small typo in
these values can stop the collector from connecting to the instrument.

### Liquid Helium Level Sensor

The liquid helium level sensor is configured as a `helium_level` device. It uses
the Keithley DMM and, when heating is enabled, the Agilent PSU.

Important fields:

- `measurement_interval_s`: time between helium level measurements, in seconds.
- `heater_enabled`: set to `true` to use the PSU heater, or `false` to read
  resistance without controlling the PSU.
- `total_sensor_length_cm`: total sensor length.
- `normal_state_linear_resistivity_ohm_per_cm`: calibration value used to convert
  resistance into level.
- `psu_port`: serial port for the PSU. Not needed when `heater_enabled = false`.
- `dmm_port`: serial port for the DMM.
- `resistance_readings`: number of resistance readings to average.

The calculated liquid helium level is:

```text
total_sensor_length_cm - resistance_average / normal_state_linear_resistivity_ohm_per_cm
```

### Email Alerts

Email alerts are optional. They are controlled by the `[alerts]` section:

```toml
[alerts]
enabled = false
require_consecutive = 2
max_emails_per_day = 1
```

Leave `enabled = false` if you do not want email alerts.

This version only supports sending email through an SMTP server. It does not
support webmail login, Microsoft Graph, Gmail API, OAuth, or other email APIs.

There are two supported SMTP setups:

- SMTP relay without a login: set `smtp_host`, `smtp_port`, `from`, and `to`.
  Leave `username` and `password_env` unset.
- Authenticated SMTP: set `smtp_host`, `smtp_port`, `from`, `to`, `username`,
  and `password_env`. Set `use_starttls = true` if your mail server requires it.

Example email settings:

```toml
[alerts.email]
smtp_host = "smtp.cam.ac.uk"
smtp_port = 25
use_starttls = false
from = "your-sender@example.com"
to = [
  "your-group@example.com",
]
```

If authenticated SMTP is needed, do not put the password directly in
`monitor.toml`. Set `password_env` to the name of an environment variable:

```toml
username = "your-smtp-user@example.com"
password_env = "LIQMON_SMTP_PASSWORD"
```

Then set that environment variable before starting the collector. The exact
method depends on the computer and operating system.

Email server settings are often specific to the institution. If you are unsure
which `smtp_host`, `smtp_port`, `use_starttls`, sender address, or authentication
settings to use, discuss this with your IT department.

Alert rules are configured with `[[alerts.rules]]` blocks. Each rule names a
device, a metric, and the allowed range:

```toml
[[alerts.rules]]
id = "scm10-temperature-max"
device_id = "scm10-eth"
metric = "temperature"
max = 5.0
unit = "K"
```

Only enable alerts after the email settings have been checked.

## Troubleshooting

- Empty dashboard: check that the collector is running and that
  `collector/data/readings.csv` is being updated.
- `No devices defined in config`: check that `monitor.toml` contains at least one
  `[[devices]]` block.
- `Unsupported device type/transport`: check the spelling of `type` and
  `transport`.
- Timeout or connection errors: check the serial port, network address, and
  instrument power/network connection.
- Dashboard will not open: check that the dashboard terminal is still running and
  open `http://127.0.0.1:8050`.
- Command not found after pulling updates: run `uv sync` inside `collector/` or
  `dashboard/`, depending on which command failed.

## More Detail

The app writes one CSV row per measurement with these columns:

- `timestamp`
- `device_id`
- `metric`
- `value`
- `unit`
- `raw`

More detailed package notes are available in:

- `collector/README.md`
- `dashboard/README.md`
