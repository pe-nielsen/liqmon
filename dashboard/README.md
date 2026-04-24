# liqmon dashboard

Minimal Dash + Plotly app that plots `readings.csv` live.

CSV timestamps are parsed from the timezone recorded in the file and displayed
in the timezone of the computer running the dashboard, including daylight-saving
time where the local timezone database provides it.

## What it shows

- Temperature (`metric = temperature`)
- HRC110 pressure + heater power (`pressure`, `heater_power`)
- CPA1114 low/high pressures (`low_pressure`, `high_pressure`)
- Liquid helium sensor resistance + calculated level (`resistance_average`, `liquid_helium_level`)

## Run

```bash
uv run liqmon-dashboard --csv ../collector/data/readings.csv
```

Then open `http://127.0.0.1:8050`.

You can also run `uv run app.py --csv ../collector/data/readings.csv`, but
`uv run liqmon-dashboard ...` is the packaged entrypoint defined in `pyproject.toml`.
If this command is not found, run `uv sync` in `dashboard/` once.

Useful flags:

- `--host` (default `127.0.0.1`)
- `--port` (default `8050`)
- `--interval-ms` refresh interval in milliseconds (default `2000`)
