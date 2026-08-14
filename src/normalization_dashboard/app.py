"""Local Dash app: every data source x CURIE prefix, worst normalization first."""

from dash import Dash, Input, Output, callback, dash_table, dcc, html

from normalization_dashboard.loader import load_rows, summarize

COLUMNS = [
    ("source", "Source"),
    ("source_versions", "Version"),
    ("prefix", "Prefix"),
    ("observed_as", "Observed as"),
    ("total", "Total"),
    ("succeeded", "Succeeded"),
    ("failed", "Failed"),
    ("success_rate", "Success %"),
    ("normalized_to_str", "Normalized to"),
]

# Red at 0% shading to green at 100%, so the ranking is scannable without reading numbers.
RATE_SHADING = [
    {
        "if": {"column_id": "success_rate", "filter_query": f"{{success_rate}} >= {low} && {{success_rate}} < {low + 20}"},
        "backgroundColor": colour,
    }
    for low, colour in ((0, "#f8d0d0"), (20, "#fae0cd"), (40, "#fdf3cd"), (60, "#e8f2d5"), (80, "#d5ecd8"))
]

app = Dash(__name__)
ROWS = load_rows()


def _table_data(latest_only):
    rows = [row for row in ROWS if row["is_latest"]] if latest_only else ROWS
    return summarize(rows)


app.layout = html.Div(
    style={"maxWidth": "1400px", "margin": "0 auto", "fontFamily": "system-ui, sans-serif"},
    children=[
        html.H1("Normalization by source and prefix"),
        html.P(
            "Prefixes are pooled case-insensitively, because NodeNorm resolves CURIE "
            "prefixes case-insensitively. Sort by Failed to rank by how many CURIEs are "
            "actually at stake rather than by percentage.",
        ),
        dcc.Checklist(
            id="latest-only",
            options=[{"label": " Latest build per source only", "value": "latest"}],
            value=["latest"],
        ),
        html.Div(id="row-count", style={"margin": "8px 0", "color": "#555"}),
        dash_table.DataTable(
            id="table",
            columns=[{"name": name, "id": key} for key, name in COLUMNS],
            sort_action="native",
            filter_action="native",
            page_size=50,
            sort_by=[{"column_id": "success_rate", "direction": "asc"}],
            style_cell={"fontFamily": "system-ui, sans-serif", "textAlign": "left", "padding": "4px 8px"},
            style_cell_conditional=[
                {"if": {"column_id": c}, "textAlign": "right"}
                for c in ("total", "succeeded", "failed", "success_rate")
            ],
            style_data_conditional=RATE_SHADING,
            style_header={"fontWeight": "600"},
        ),
    ],
)


@callback(
    Output("table", "data"),
    Output("row-count", "children"),
    Input("latest-only", "value"),
)
def update_table(latest_only):
    data = _table_data("latest" in latest_only)
    return data, f"{len(data)} rows across {len({row['source'] for row in data})} sources"


def main() -> None:
    app.run(debug=True)
