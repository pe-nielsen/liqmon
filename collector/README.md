# liqmon

Poll laboratory instruments over serial or TCP and append readings to CSV.

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
- Set the TCP host/port and serial parameters to match each instrument.
