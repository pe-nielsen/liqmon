# liqmon dashboard

Minimal Dash + Plotly app that plots `readings.csv` live.

## What it shows

- Temperature (`metric = temperature`)
- HRC110 pressure + heater power (`pressure`, `heater_power`)
- CPA1114 low/high pressures (`low_pressure`, `high_pressure`)

## Run

```bash
uv run liqmon-dashboard --csv ../collector/data/readings.csv
```

Then open `http://127.0.0.1:8050`.

Useful flags:

- `--host` (default `127.0.0.1`)
- `--port` (default `8050`)
- `--interval-ms` refresh interval in milliseconds (default `2000`)
