# liqmon monorepo

`liqmon` is a two-package Python monorepo for collecting live lab instrument readings and visualizing them in a browser.

- `collector/`: polls instruments over serial or TCP and appends normalized rows to CSV.
- `dashboard/`: a Dash + Plotly web app that reads the CSV and updates charts live.

## Project layout

```text
.
├── collector/   # data collection service and device protocol handling
└── dashboard/   # live visualization app
```

## How it works

1. `collector` loads a TOML config (`liqmon.toml`) describing devices and connection settings.
2. It opens all configured transports, polls each device on its own interval, and appends measurements to `data/readings.csv`.
3. `dashboard` reads that CSV on a timer and renders dedicated plots for temperature (SCM10), pressure + heater power (HRC110), and CPA1114 low/high pressure.

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
cp liqmon.example.toml liqmon.toml
# edit liqmon.toml for your environment
uv run liqmon --config liqmon.toml
```

Key config fields:

- `[global]`
- `interval_s`: default poll interval in seconds
- `output`: CSV path (default `data/readings.csv`)
- `utc`: write timestamps in UTC when `true`
- `[[devices]]`
- required: `id`, `type` (`scm10`/`hrc110`/`cpa1114`), `transport` (`serial`/`tcp`)
- transport-specific: serial needs `port`; tcp needs `host` and `port`
- optional: per-device `interval_s`, `output`, `query`, `write_terminator`, `read_terminators`, `unit_id`
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

## Typical workflow

1. Start `collector` and verify `collector/data/readings.csv` is being updated.
2. Start `dashboard` pointing at that CSV.
3. Adjust poll intervals or device query/terminators in `collector/liqmon.toml` as needed for instrument behavior.

## Package docs

- Collector details: `collector/README.md`
- Dashboard details: `dashboard/README.md`

## Troubleshooting

- `No devices defined in config`: ensure `[[devices]]` entries exist in TOML.
- `Unsupported device type/transport`: check `type` and `transport` spelling.
- Timeout or parse errors: verify query command, terminators, and port/network access.
- Empty dashboard: confirm CSV path and that collector is writing non-empty rows.
- Alerts not sending: verify SMTP settings and ensure `password_env` is exported in the shell/session running collector.
