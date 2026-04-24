# liqmon monorepo

`liqmon` is a two-package Python monorepo for collecting live lab instrument readings and visualizing them in a browser.

- `collector/`: polls instruments over serial or TCP and appends normalized rows to CSV.
- `dashboard/`: a Dash + Plotly web app that reads the CSV and updates charts live.
- CLI entrypoints: `liqmon-collector` and `liqmon-dashboard`.

## Project layout

```text
.
├── collector/   # data collection service and device protocol handling
└── dashboard/   # live visualization app
```

## How it works

1. `collector` loads a TOML config (`monitor.toml`) describing devices and connection settings.
2. It opens all configured transports, polls each device on its own interval, and appends measurements to `data/readings.csv`.
3. The liquid helium level meter readout, when enabled, controls the Agilent E3647A PSU and Keithley 2000 DMM as one logical device and writes PSU voltage/current plus average 4-wire resistance.
4. `dashboard` reads that CSV on a timer and renders dedicated plots for temperature (SCM10), pressure + heater power (HRC110), CPA1114 low/high pressure, and liquid helium resistance + level.

CSV columns written by `collector`:

- `timestamp`
- `device_id`
- `metric`
- `value`
- `unit`
- `raw`

## Requirements

- Python `>=3.13`
- [`uv`](https://docs.astral.sh/uv/) for dependency management and running scripts
- Access to lab devices over serial (`pyserial`) and/or TCP

## Quick start

### 1. Configure and run collector

```bash
cd collector
cp monitor.example.toml monitor.toml
# edit monitor.toml for your environment
uv run liqmon-collector --config monitor.toml
```

Key config fields:

- `[global]`
- `interval_s`: default poll interval in seconds
- `output`: CSV path (default `data/readings.csv`)
- `utc`: write timestamps in UTC when `true`
- `[[devices]]`
- required: `id`, `type` (`scm10`/`hrc110`/`cpa1114`/`helium_level`), `transport` (`serial`/`tcp`)
- transport-specific: serial needs `port`; tcp needs `host` and `port`
- optional: per-device `interval_s`, `output`, `query`, `write_terminator`, `read_terminators`, `unit_id`
- `helium_level`: use `measurement_interval_s`, `heater_enabled`, `total_sensor_length_cm`, `normal_state_linear_resistivity_ohm_per_cm`, `dmm_port`, optional `psu_port` when the heater is enabled, `resistance_readings`, and optional PSU/DMM serial and measurement settings
- optional: `[alerts]` + `[alerts.email]` + `[[alerts.rules]]` for threshold email notifications

Minimal example:

```toml
[global]
interval_s = 60
output = "data/readings.csv"
utc = true

[[devices]]
id = "scm10-eth"
type = "scm10"
transport = "tcp"
host = "192.168.0.4"
port = 9760
```

### 2. Run dashboard

Open a second terminal:

```bash
cd dashboard
uv run liqmon-dashboard --csv ../collector/data/readings.csv
```

Then open `http://127.0.0.1:8050`.

Useful flags:

- `--host` (default `127.0.0.1`)
- `--port` (default `8050`)
- `--interval-ms` refresh interval (default `2000`)

## Packaging note

Both subprojects are configured as packages so `uv` can install stable CLI entrypoints from
`[project.scripts]` in each `pyproject.toml`:

- `liqmon-collector`
- `liqmon-dashboard`

Why this is done:

- Commands stay stable even if module filenames change.
- New users run clear CLI names instead of file paths.
- Standard packaging metadata makes build/install/release workflows possible later.

After pulling dependency or packaging changes, run `uv sync` in each subproject once so
entrypoints are installed.

## Typical workflow

1. Start `collector` and verify `collector/data/readings.csv` is being updated.
2. Start `dashboard` pointing at that CSV.
3. Adjust poll intervals or device query/terminators in `collector/monitor.toml` as needed for instrument behavior.

## Package docs

- Collector details: `collector/README.md`
- Dashboard details: `dashboard/README.md`

## Troubleshooting

- `No devices defined in config`: ensure `[[devices]]` entries exist in TOML.
- `Unsupported device type/transport`: check `type` and `transport` spelling.
- Timeout or parse errors: verify query command, terminators, and port/network access.
- Empty dashboard: confirm CSV path and that collector is writing non-empty rows.
- Alerts not sending: verify SMTP settings and ensure `password_env` is exported in the shell/session running collector.
- `Failed to spawn` for a CLI command: run `uv sync` inside the corresponding subproject.
