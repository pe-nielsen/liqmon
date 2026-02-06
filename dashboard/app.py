from __future__ import annotations

import argparse
import os
from pathlib import Path

import dash
import pandas as pd
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.graph_objects as go
from dash import Input, Output, dcc, html


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
        default=2000,
        type=int,
        help="Refresh interval in milliseconds.",
    )
    return parser.parse_args()


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["timestamp", "metric", "value"])


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
    if "timestamp" not in df.columns or "metric" not in df.columns or "value" not in df.columns:
        return _empty_frame()
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    return df


def _make_temperature_figure(df: pd.DataFrame):
    if df.empty:
        fig = px.line()
        fig.update_layout(
            title="No data yet",
            xaxis_title="timestamp",
            yaxis_title="value",
            uirevision="keep",
        )
        return fig
    df = df[df["metric"] == "temperature"]
    if df.empty:
        fig = px.line()
        fig.update_layout(
            title="No temperature data yet",
            xaxis_title="timestamp",
            yaxis_title="temperature",
            uirevision="keep",
        )
        return fig
    fig = px.line(df, x="timestamp", y="value", color="metric")
    fig.update_layout(
        title="Temperature",
        xaxis_title="timestamp",
        yaxis_title="temperature",
        uirevision="keep",
        showlegend=False,
    )
    return fig


def _make_pressure_heater_figure(df: pd.DataFrame):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.update_layout(
        title="Pressure + Heater Power",
        xaxis_title="timestamp",
        uirevision="keep",
    )
    if df.empty:
        fig.update_yaxes(title_text="pressure", secondary_y=False)
        fig.update_yaxes(title_text="heater_power", secondary_y=True)
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
    fig.update_yaxes(title_text="pressure", secondary_y=False)
    fig.update_yaxes(title_text="heater_power", secondary_y=True)
    return fig


def main() -> None:
    args = _parse_args()

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
                --bg: #f5f2ee;
                --card: #ffffff;
                --ink: #1c1c1c;
                --muted: #6b6b6b;
                --accent: #1f6feb;
                --border: #e6e0d8;
            }
            * { box-sizing: border-box; }
            body {
                margin: 0;
                font-family: "IBM Plex Sans", system-ui, -apple-system, sans-serif;
                color: var(--ink);
                background: radial-gradient(1200px 600px at 10% -10%, #fff 0%, var(--bg) 60%);
            }
            .page {
                max-width: 1100px;
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
            .grid {
                display: grid;
                grid-template-columns: 1fr;
                gap: 18px;
            }
            .card {
                background: var(--card);
                border: 1px solid var(--border);
                border-radius: 14px;
                padding: 12px 14px 6px;
                box-shadow: 0 8px 24px rgba(16, 16, 16, 0.06);
            }
            @media (min-width: 900px) {
                .grid {
                    grid-template-columns: 1fr 1fr;
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
                        f"source: {args.csv} · refresh: {args.interval_ms} ms",
                        className="subtitle",
                    ),
                ],
            ),
            html.Div(
                className="grid",
                children=[
                    html.Div(dcc.Graph(id="temp-graph"), className="card"),
                    html.Div(dcc.Graph(id="pressure-graph"), className="card"),
                ],
            ),
            dcc.Interval(id="interval", interval=args.interval_ms, n_intervals=0),
        ],
    )

    @app.callback(
        Output("temp-graph", "figure"),
        Output("pressure-graph", "figure"),
        Input("interval", "n_intervals"),
    )
    def _update(_):
        df = _load_data(args.csv)
        return _make_temperature_figure(df), _make_pressure_heater_figure(df)

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
