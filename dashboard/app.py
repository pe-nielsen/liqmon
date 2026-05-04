from __future__ import annotations

import argparse
import os
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import dash
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, dcc, html
from plotly.subplots import make_subplots

_LOCAL_TIMEZONE = None
_TIME_RANGES = {
    "1h": ("1h", pd.Timedelta(hours=1)),
    "6h": ("6h", pd.Timedelta(hours=6)),
    "24h": ("24h", pd.Timedelta(hours=24)),
    "7d": ("7d", pd.Timedelta(days=7)),
    "all": ("All", None),
}
_SUMMARY_METRICS = [
    ("liquid_helium_level", "helium level", "cm", "helium-level"),
    ("resistance_average", "sensor resistance", "ohm", "helium-level"),
    ("temperature", "temperature", "K", None),
    ("pressure", "pressure", "", None),
    ("heater_power", "heater power", "W", None),
    ("low_pressure", "low pressure", "", None),
    ("high_pressure", "high pressure", "", None),
]
_HELIUM_LEVEL_GUIDES_CM = [
    (14.0, "Magnet 1 Top (Sample)"),
    (35.0, "Magnet 2 Top (ADR2)"),
    (71.0, "Magnet 3 Top (ADR1)"),
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live dashboard for liqmon readings.")
    parser.add_argument(
        "--csv",
        default=os.environ.get("LIQMON_READINGS", "../collector/data/readings.csv"),
        help="Path to readings.csv",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for the Dash server.",
    )
    parser.add_argument(
        "--port",
        default=8050,
        type=int,
        help="Port for the Dash server.",
    )
    parser.add_argument(
        "--interval-ms",
        default=20000,
        type=int,
        help="Refresh interval in milliseconds.",
    )
    parser.add_argument(
        "--stale-after-minutes",
        default=10,
        type=float,
        help="Show a stale-data warning if the newest reading is older than this many minutes.",
    )
    return parser.parse_args()


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["timestamp", "metric", "value", "unit"])


def _local_timezone() -> tzinfo:
    timezone_name = os.environ.get("TZ")
    if timezone_name:
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            pass

    localtime_path = Path("/etc/localtime")
    try:
        resolved = localtime_path.resolve()
    except OSError:
        resolved = localtime_path

    parts = resolved.parts
    if "zoneinfo" in parts:
        zoneinfo_index = parts.index("zoneinfo")
        timezone_name = "/".join(parts[zoneinfo_index + 1 :])
        if timezone_name:
            try:
                return ZoneInfo(timezone_name)
            except ZoneInfoNotFoundError:
                pass

    return datetime.now().astimezone().tzinfo or ZoneInfo("Europe/London")


def _timezone_label(timezone: tzinfo) -> str:
    key = getattr(timezone, "key", None)
    if key:
        return str(key)
    return datetime.now(timezone).tzname() or "local time"


def _set_local_timezone(timezone: tzinfo) -> None:
    global _LOCAL_TIMEZONE
    _LOCAL_TIMEZONE = timezone


def _load_data(path: str) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        return _empty_frame()
    try:
        df = pd.read_csv(csv_path)
    except pd.errors.EmptyDataError:
        return _empty_frame()
    if df.empty:
        return _empty_frame()
    if (
        "timestamp" not in df.columns
        or "metric" not in df.columns
        or "value" not in df.columns
    ):
        return _empty_frame()
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"])
    timezone = _LOCAL_TIMEZONE or _local_timezone()
    df["timestamp"] = df["timestamp"].dt.tz_convert(timezone).dt.tz_localize(None)
    return df


def _csv_status(
    path: str, df: pd.DataFrame, stale_after_minutes: float
) -> dict[str, Any]:
    csv_path = Path(path)
    exists = csv_path.exists()
    size_bytes = csv_path.stat().st_size if exists else 0
    latest = (
        df["timestamp"].max() if not df.empty and "timestamp" in df.columns else None
    )
    now = datetime.now(_LOCAL_TIMEZONE or _local_timezone()).replace(tzinfo=None)
    age = (
        now - latest.to_pydatetime()
        if latest is not None and not pd.isna(latest)
        else None
    )
    stale_after = pd.Timedelta(minutes=stale_after_minutes)
    is_stale = age is None or pd.Timedelta(age) > stale_after
    return {
        "path": str(csv_path),
        "exists": exists,
        "size_bytes": size_bytes,
        "row_count": len(df),
        "latest": latest,
        "age": age,
        "is_stale": is_stale,
    }


def _time_range_bounds(df: pd.DataFrame, range_key: str) -> list[datetime] | None:
    if df.empty:
        return None
    _, window = _TIME_RANGES.get(range_key, _TIME_RANGES["24h"])
    if window is None:
        return None
    latest = df["timestamp"].max()
    if pd.isna(latest):
        return None
    return [latest - window, latest]


def _apply_time_range(fig, df: pd.DataFrame, range_key: str):
    bounds = _time_range_bounds(df, range_key)
    if bounds is None:
        fig.update_xaxes(autorange=True)
    else:
        fig.update_xaxes(range=bounds)
    _apply_visible_y_ranges(fig, bounds)
    return fig


def _apply_visible_y_ranges(fig, bounds: list[datetime] | None) -> None:
    values_by_axis: dict[str, list[float]] = {}
    for trace in fig.data:
        axis = getattr(trace, "yaxis", None) or "y"
        visible_y = _visible_y_values(trace, bounds)
        if visible_y:
            values_by_axis.setdefault(axis, []).extend(visible_y)

    if not values_by_axis:
        fig.update_yaxes(autorange=True)
        return

    axis_layout_names = {"y": "yaxis"}
    axis_layout_names.update(
        {f"y{index}": f"yaxis{index}" for index in range(2, 10)}
    )
    for axis, values in values_by_axis.items():
        axis_layout_name = axis_layout_names.get(axis)
        if axis_layout_name is None or not hasattr(fig.layout, axis_layout_name):
            continue
        getattr(fig.layout, axis_layout_name).update(
            range=_padded_axis_range(values),
            autorange=False,
        )


def _visible_y_values(trace, bounds: list[datetime] | None) -> list[float]:
    x_values = list(trace.x) if trace.x is not None else []
    y_values = list(trace.y) if trace.y is not None else []
    if not x_values or not y_values:
        return []

    if bounds is None:
        visible = []
        for value in y_values:
            clean_y = _clean_float(value)
            if clean_y is not None:
                visible.append(clean_y)
        return visible

    start, end = bounds
    visible = []
    for x_value, y_value in zip(x_values, y_values):
        if start <= x_value <= end:
            clean_y = _clean_float(y_value)
            if clean_y is not None:
                visible.append(clean_y)

    if visible or len(x_values) != 2:
        return visible

    x0, x1 = x_values
    if min(x0, x1) <= end and max(x0, x1) >= start:
        visible = []
        for value in y_values:
            clean_y = _clean_float(value)
            if clean_y is not None:
                visible.append(clean_y)
        return visible
    return []


def _clean_float(value) -> float | None:
    try:
        cleaned = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(cleaned):
        return None
    return cleaned


def _padded_axis_range(values: list[float]) -> list[float]:
    minimum = min(values)
    maximum = max(values)
    if minimum == maximum:
        padding = max(abs(minimum) * 0.05, 1.0)
    else:
        padding = (maximum - minimum) * 0.08
    return [minimum - padding, maximum + padding]


def _metric_unit(
    df: pd.DataFrame,
    metric: str,
    fallback: str = "",
    device_id: str | None = None,
) -> str:
    if "unit" not in df.columns:
        return fallback
    metric_df = df[df["metric"] == metric]
    if device_id is not None and "device_id" in metric_df.columns:
        metric_df = metric_df[metric_df["device_id"] == device_id]
    if metric_df.empty:
        return fallback
    units = metric_df["unit"].dropna().astype(str).str.strip()
    units = units[units != ""]
    if units.empty:
        return fallback
    return units.iloc[0]


def _label_with_unit(label: str, unit: str) -> str:
    return f"{label} ({unit})" if unit else label


def _format_value(value: float) -> str:
    if pd.isna(value):
        return "--"
    abs_value = abs(value)
    if abs_value >= 100:
        return f"{value:.0f}"
    if abs_value >= 10:
        return f"{value:.2f}"
    if abs_value >= 1:
        return f"{value:.3f}"
    return f"{value:.3g}"


def _format_bytes(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size_bytes} B"


def _format_age(age) -> str:
    if age is None:
        return "no readings"
    seconds = max(int(age.total_seconds()), 0)
    if seconds < 90:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 90:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def _format_duration(age) -> str:
    if age is None:
        return "unknown duration"
    seconds = max(int(age.total_seconds()), 0)
    if seconds < 90:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 90:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h"
    return f"{hours // 24}d"


def _latest_metric(
    df: pd.DataFrame,
    metric: str,
    device_id: str | None = None,
) -> pd.Series | None:
    if df.empty:
        return None
    metric_df = df[df["metric"] == metric]
    if device_id is not None and "device_id" in metric_df.columns:
        metric_df = metric_df[metric_df["device_id"] == device_id]
    if metric_df.empty:
        return None
    return metric_df.sort_values("timestamp").iloc[-1]


def _make_summary_cards(df: pd.DataFrame) -> list[html.Div]:
    cards = []
    for metric, label, fallback_unit, device_id in _SUMMARY_METRICS:
        latest = _latest_metric(df, metric, device_id)
        if latest is None:
            continue
        unit = str(latest.get("unit") or fallback_unit)
        cards.append(
            html.Div(
                className="summary-card",
                children=[
                    html.Div(label, className="summary-label"),
                    html.Div(
                        [
                            html.Span(_format_value(float(latest["value"]))),
                            html.Span(
                                f" {unit}" if unit else "", className="summary-unit"
                            ),
                        ],
                        className="summary-value",
                    ),
                ],
            )
        )
    if cards:
        return cards
    return [
        html.Div(
            className="summary-empty",
            children="No readings loaded yet.",
        )
    ]


def _make_status(status: dict[str, Any], timezone: tzinfo) -> html.Div:
    latest = status["latest"]
    latest_text = (
        latest.strftime("%Y-%m-%d %H:%M:%S")
        if latest is not None and not pd.isna(latest)
        else "none"
    )
    warning = None
    if not status["exists"]:
        warning = "CSV file not found"
    elif status["is_stale"]:
        warning = (
            "No readings loaded"
            if status["age"] is None
            else f"No new data for {_format_duration(status['age'])}"
        )

    return html.Div(
        className="status-wrap",
        children=[
            html.Div(
                className=f"freshness {'stale' if warning else 'ok'}",
                children=[
                    html.Span("Last updated", className="status-label"),
                    html.Span(f"{latest_text} ({_timezone_label(timezone)})"),
                    html.Span(
                        f" · {_format_age(status['age'])}", className="status-age"
                    ),
                ],
            ),
            html.Div(warning, className="stale-warning") if warning else None,
            html.Div(
                className="file-meta",
                children=(
                    f"{status['path']} · {_format_bytes(status['size_bytes'])} · "
                    f"{status['row_count']:,} rows"
                ),
            ),
        ],
    )


def _make_temperature_figure(df: pd.DataFrame):
    temp_unit = _metric_unit(df, "temperature", "K")
    if df.empty:
        fig = px.line()
        fig.update_layout(
            title="No data yet",
            xaxis_title="timestamp",
            yaxis_title=_label_with_unit("temperature", temp_unit),
            uirevision="keep",
        )
        return fig
    df = df[df["metric"] == "temperature"]
    if df.empty:
        fig = px.line()
        fig.update_layout(
            title="No temperature data yet",
            xaxis_title="timestamp",
            yaxis_title=_label_with_unit("temperature", temp_unit),
            uirevision="keep",
        )
        return fig
    fig = px.line(df, x="timestamp", y="value", color="metric")
    fig.update_layout(
        title="Temperature",
        xaxis_title="timestamp",
        yaxis_title=_label_with_unit("temperature", temp_unit),
        uirevision="keep",
        showlegend=False,
    )
    return fig


def _make_pressure_heater_figure(df: pd.DataFrame):
    pressure_unit = _metric_unit(df, "pressure")
    heater_unit = _metric_unit(df, "heater_power", "W")
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.update_layout(
        title="Pressure + Heater Power",
        xaxis_title="timestamp",
        uirevision="keep",
    )
    if df.empty:
        fig.update_yaxes(
            title_text=_label_with_unit("pressure", pressure_unit), secondary_y=False
        )
        fig.update_yaxes(
            title_text=_label_with_unit("heater power", heater_unit), secondary_y=True
        )
        return fig
    pressure = df[df["metric"] == "pressure"]
    heater = df[df["metric"] == "heater_power"]
    if not pressure.empty:
        fig.add_trace(
            go.Scatter(
                x=pressure["timestamp"],
                y=pressure["value"],
                name="pressure",
                mode="lines",
            ),
            secondary_y=False,
        )
    if not heater.empty:
        fig.add_trace(
            go.Scatter(
                x=heater["timestamp"],
                y=heater["value"],
                name="heater_power",
                mode="lines",
            ),
            secondary_y=True,
        )
    fig.update_yaxes(
        title_text=_label_with_unit("pressure", pressure_unit), secondary_y=False
    )
    fig.update_yaxes(
        title_text=_label_with_unit("heater power", heater_unit), secondary_y=True
    )
    return fig


def _make_cpa_pressures_figure(df: pd.DataFrame):
    low_unit = _metric_unit(df, "low_pressure")
    high_unit = _metric_unit(df, "high_pressure")
    cpa_unit = low_unit or high_unit
    fig = px.line()
    fig.update_layout(
        title="CPA1114 Pressures",
        xaxis_title="timestamp",
        yaxis_title=_label_with_unit("pressure", cpa_unit),
        uirevision="keep",
    )
    if df.empty:
        return fig

    cpa = df[df["metric"].isin(["low_pressure", "high_pressure"])]
    if cpa.empty:
        fig.update_layout(title="No CPA1114 pressure data yet")
        return fig

    fig = px.line(cpa, x="timestamp", y="value", color="metric")
    fig.update_layout(
        title="CPA1114 Pressures",
        xaxis_title="timestamp",
        yaxis_title=_label_with_unit("pressure", cpa_unit),
        uirevision="keep",
        legend_title_text="metric",
    )
    return fig


def _make_helium_level_figure(df: pd.DataFrame):
    resistance_unit = _metric_unit(
        df, "resistance_average", "ohm", device_id="helium-level"
    )
    level_unit = _metric_unit(df, "liquid_helium_level", "cm", device_id="helium-level")
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.update_layout(
        title="Liquid Helium Level",
        xaxis_title="timestamp",
        uirevision="keep",
        legend={
            "title": {"text": "readings"},
            "orientation": "v",
            "yanchor": "top",
            "y": -0.28,
            "xanchor": "left",
            "x": 0,
        },
        legend2={
            "title": {"text": "magnet indicators"},
            "orientation": "v",
            "yanchor": "top",
            "y": -0.28,
            "xanchor": "left",
            "x": 0.48,
        },
        margin={"r": 92, "b": 150},
    )
    fig.update_yaxes(
        title_text=_label_with_unit("sensor resistance", resistance_unit),
        secondary_y=False,
    )
    fig.update_yaxes(
        title_text=_label_with_unit("liquid helium level", level_unit),
        title_standoff=16,
        secondary_y=True,
    )
    if df.empty:
        return fig

    helium = df[df["metric"].isin(["resistance_average", "liquid_helium_level"])]
    if "device_id" in helium.columns:
        helium = helium[helium["device_id"] == "helium-level"]
    if helium.empty:
        fig.update_layout(title="No liquid helium level data yet")
        return fig

    resistance = helium[helium["metric"] == "resistance_average"]
    level = helium[helium["metric"] == "liquid_helium_level"]
    if not resistance.empty:
        fig.add_trace(
            go.Scatter(
                x=resistance["timestamp"],
                y=resistance["value"],
                name="sensor resistance",
                mode="lines+markers",
                line={"color": "#6f4e7c", "width": 2},
                marker={"size": 5},
            ),
            secondary_y=False,
        )
    if not level.empty:
        fig.add_trace(
            go.Scatter(
                x=level["timestamp"],
                y=level["value"],
                name="liquid helium level",
                mode="lines+markers",
                line={"color": "#16836f", "width": 2},
                marker={"size": 5},
            ),
            secondary_y=True,
        )
        _add_helium_level_guides(fig, level)
    return fig


def _add_helium_level_guides(fig, level: pd.DataFrame) -> None:
    if level.empty:
        return
    x0 = level["timestamp"].min()
    x1 = level["timestamp"].max()
    for level_cm, label in _HELIUM_LEVEL_GUIDES_CM:
        fig.add_trace(
            go.Scatter(
                x=[x0, x1],
                y=[level_cm, level_cm],
                name=label,
                legend="legend2",
                mode="lines",
                line={"color": "rgba(80, 90, 110, 0.55)", "width": 1.5, "dash": "dot"},
                hovertemplate=f"{label}<br>{level_cm:.0f} cm<extra></extra>",
            ),
            secondary_y=True,
        )


def main() -> None:
    args = _parse_args()
    timezone = _local_timezone()
    _set_local_timezone(timezone)

    app = dash.Dash(__name__)
    app.index_string = """<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            @import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400;600&display=swap");
            :root {
                --bg: #f6f7f8;
                --card: #ffffff;
                --ink: #1c1c1c;
                --muted: #6b6b6b;
                --accent: #1f6feb;
                --border: #e3e7ec;
                --warning: #8a5a00;
                --warning-bg: #fff7df;
            }
            * { box-sizing: border-box; }
            body {
                margin: 0;
                font-family: "IBM Plex Sans", system-ui, -apple-system, sans-serif;
                color: var(--ink);
                background: var(--bg);
            }
            .page {
                max-width: 1180px;
                margin: 32px auto 48px;
                padding: 0 20px;
            }
            .header {
                display: flex;
                flex-direction: column;
                gap: 6px;
                margin-bottom: 20px;
                animation: fadeIn 500ms ease-out;
            }
            .title {
                font-size: 28px;
                font-weight: 600;
                letter-spacing: 0.2px;
            }
            .subtitle {
                color: var(--muted);
                font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
                font-size: 13px;
            }
            .top-panel {
                display: flex;
                flex-direction: column;
                gap: 12px;
                margin-bottom: 18px;
            }
            .summary-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 10px;
            }
            .summary-card {
                background: var(--card);
                border: 1px solid var(--border);
                border-radius: 8px;
                padding: 12px 14px;
            }
            .summary-label {
                color: var(--muted);
                font-size: 12px;
                line-height: 1.2;
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .summary-value {
                margin-top: 6px;
                font-size: 24px;
                font-weight: 600;
                line-height: 1.1;
            }
            .summary-unit {
                color: var(--muted);
                font-size: 15px;
                font-weight: 400;
            }
            .summary-empty {
                color: var(--muted);
                background: var(--card);
                border: 1px solid var(--border);
                border-radius: 8px;
                padding: 14px;
            }
            .controls-row {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                gap: 14px;
                flex-wrap: wrap;
            }
            .range-control {
                display: inline-flex;
                gap: 4px;
                padding: 4px;
                background: #edf1f5;
                border: 1px solid var(--border);
                border-radius: 8px;
            }
            .range-control label {
                display: inline-flex;
                align-items: center;
                min-height: 32px;
                padding: 0 12px;
                border-radius: 6px;
                color: #3d4652;
                font-size: 13px;
                font-weight: 600;
                cursor: pointer;
            }
            .range-control input {
                display: none;
            }
            .range-control label:has(input:checked) {
                color: var(--ink);
                background: var(--card);
                box-shadow: 0 1px 4px rgba(20, 32, 46, 0.12);
            }
            .status-wrap {
                min-width: 280px;
                flex: 1;
                color: var(--muted);
                font-size: 13px;
                line-height: 1.45;
            }
            .freshness {
                color: #35513a;
                font-weight: 600;
            }
            .freshness.stale {
                color: var(--warning);
            }
            .status-label {
                color: var(--muted);
                font-weight: 400;
                margin-right: 8px;
            }
            .status-age {
                color: var(--muted);
                font-weight: 400;
            }
            .stale-warning {
                display: inline-block;
                margin-top: 5px;
                padding: 5px 8px;
                color: var(--warning);
                background: var(--warning-bg);
                border: 1px solid #f1d48a;
                border-radius: 6px;
                font-weight: 600;
            }
            .file-meta {
                margin-top: 5px;
                font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
                font-size: 12px;
                overflow-wrap: anywhere;
            }
            .grid {
                display: grid;
                grid-template-columns: 1fr;
                gap: 18px;
            }
            .card {
                background: var(--card);
                border: 1px solid var(--border);
                border-radius: 8px;
                padding: 12px 14px 6px;
                box-shadow: 0 4px 16px rgba(16, 24, 40, 0.05);
            }
            @media (min-width: 900px) {
                .grid {
                    grid-template-columns: 1fr 1fr;
                }
            }
            @media (max-width: 640px) {
                .summary-grid {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
                .summary-value {
                    font-size: 21px;
                }
                .range-control {
                    width: 100%;
                    justify-content: space-between;
                }
                .range-control label {
                    flex: 1;
                    justify-content: center;
                    padding: 0 8px;
                }
            }
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(6px); }
                to { opacity: 1; transform: translateY(0); }
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>"""
    app.layout = html.Div(
        className="page",
        children=[
            html.Div(
                className="header",
                children=[
                    html.Div("liqmon live readings", className="title"),
                    html.Div(
                        (
                            f"refresh: {args.interval_ms} ms · "
                            f"timezone: {_timezone_label(timezone)}"
                        ),
                        className="subtitle",
                    ),
                ],
            ),
            html.Div(
                className="top-panel",
                children=[
                    html.Div(id="summary-cards", className="summary-grid"),
                    html.Div(
                        className="controls-row",
                        children=[
                            dcc.RadioItems(
                                id="time-range",
                                className="range-control",
                                options=[
                                    {"label": label, "value": value}
                                    for value, (label, _window) in _TIME_RANGES.items()
                                ],
                                value="24h",
                                inline=True,
                            ),
                            html.Div(id="csv-status"),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="grid",
                children=[
                    html.Div(dcc.Graph(id="temp-graph"), className="card"),
                    html.Div(dcc.Graph(id="pressure-graph"), className="card"),
                    html.Div(dcc.Graph(id="cpa-pressure-graph"), className="card"),
                    html.Div(dcc.Graph(id="helium-level-graph"), className="card"),
                ],
            ),
            dcc.Interval(id="interval", interval=args.interval_ms, n_intervals=0),
        ],
    )

    @app.callback(
        Output("summary-cards", "children"),
        Output("csv-status", "children"),
        Output("temp-graph", "figure"),
        Output("pressure-graph", "figure"),
        Output("cpa-pressure-graph", "figure"),
        Output("helium-level-graph", "figure"),
        Input("interval", "n_intervals"),
        Input("time-range", "value"),
    )
    def _update(_, time_range):
        df = _load_data(args.csv)
        status = _csv_status(args.csv, df, args.stale_after_minutes)
        temp_fig = _apply_time_range(_make_temperature_figure(df), df, time_range)
        pressure_fig = _apply_time_range(
            _make_pressure_heater_figure(df), df, time_range
        )
        cpa_fig = _apply_time_range(_make_cpa_pressures_figure(df), df, time_range)
        helium_fig = _apply_time_range(_make_helium_level_figure(df), df, time_range)
        return (
            _make_summary_cards(df),
            _make_status(status, timezone),
            temp_fig,
            pressure_fig,
            cpa_fig,
            helium_fig,
        )

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
