# Changelog

## v0.1.0 - Initial Feature-Complete Release

This is the first release intended for routine lab use.

### Included

- Collector for polling configured cryostat instruments over serial or TCP.
- CSV output with one row per measurement.
- Browser dashboard for live diagnostic information.
- Dashboard plots for:
  - Liquefier cold head temperature
  - Liquefier pressure and heater power
  - Compressor pressures
  - Liquid helium level sensor readings
- Liquid helium level measurement using the Keithley DMM and optional Agilent PSU heater control.
- Optional SMTP email alerts for threshold rules.
- Dashboard stale-data warnings and large-CSV protection.
- User-facing README instructions for running the collector, running the dashboard, editing TOML configuration, and stopping the app.

### Supported Data Format

- CSV readings files are supported.
- SQLite readings files are not supported in this release.

### Known Limitations

- Email alerts currently support SMTP only.
- The dashboard defaults to plotting the latest 100,000 CSV data rows to keep the browser responsive.
- Users should check serial ports, IP addresses, and email server settings with local IT or lab support before deployment.
