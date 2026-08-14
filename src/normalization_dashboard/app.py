"""Local Dash app: every data source x CURIE prefix, worst normalization first."""

from dash import Dash, Input, Output, callback, dash_table, dcc, html

from normalization_dashboard import curie
from normalization_dashboard.loader import load_rows, summarize

# (key, header, markdown?) -- CURIE Prefix leads, it is the row's subject.
COLUMNS = [
    ("prefix", "CURIE Prefix", False),
    ("source", "Source", False),
    ("source_versions_md", "Version", True),
    ("observed_as", "Observed as", False),
    ("total", "Total", False),
    ("succeeded", "Succeeded", False),
    ("failed", "Failed", False),
    ("success_rate", "Success %", False),
    ("normalized_to_str", "Normalized to", False),
]

# Red at 0% shading to green at 100%, so the ranking is scannable without reading numbers.
RATE_SHADING = [
    {
        "if": {
            "column_id": "success_rate",
            "filter_query": f"{{success_rate}} >= {low} && {{success_rate}} < {low + 20}",
        },
        "backgroundColor": colour,
    }
    for low, colour in (
        (0, "#f8d0d0"),
        (20, "#fae0cd"),
        (40, "#fdf3cd"),
        (60, "#e8f2d5"),
        (80, "#d5ecd8"),
    )
]

# The prefix column is effectively the row header, so it reads like one.
PREFIX_STYLE = {
    "if": {"column_id": "prefix"},
    "fontWeight": "600",
    "fontFamily": "ui-monospace, monospace",
    "backgroundColor": "#f4f4f6",
}

MAX_CURIES_SHOWN = 300

app = Dash(__name__)
ROWS = load_rows()


def table_rows(latest_only, hide_complete):
    rows = [row for row in ROWS if row["is_latest"]] if latest_only else ROWS
    summary = summarize(rows)
    if hide_complete:
        summary = [row for row in summary if row["success_rate"] < 100]
    return summary


app.layout = html.Div(
    style={"maxWidth": "1400px", "margin": "0 auto", "fontFamily": "system-ui, sans-serif"},
    children=[
        html.H1("Normalization by source and CURIE prefix"),
        html.P(
            "Prefixes are pooled case-insensitively, because NodeNorm resolves CURIE "
            "prefixes case-insensitively. Sort by Failed to rank by how many CURIEs are "
            "actually at stake rather than by percentage. Click a row to list the CURIEs "
            "that failed to normalize."
        ),
        dcc.Checklist(
            id="latest-only",
            options=[{"label": " Latest build per source only", "value": "latest"}],
            value=["latest"],
        ),
        dcc.Checklist(id="hide-complete", options=[], value=["hide"]),
        html.Div(id="row-count", style={"margin": "8px 0", "color": "#555"}),
        dash_table.DataTable(
            id="table",
            columns=[
                {"name": name, "id": key, **({"presentation": "markdown"} if md else {})}
                for key, name, md in COLUMNS
            ],
            markdown_options={"link_target": "_blank"},
            sort_action="native",
            filter_action="native",
            page_size=75,
            sort_by=[{"column_id": "success_rate", "direction": "asc"}],
            style_cell={
                "fontFamily": "system-ui, sans-serif",
                "textAlign": "left",
                "padding": "4px 8px",
            },
            style_cell_conditional=[
                {"if": {"column_id": column}, "textAlign": "right"}
                for column in ("total", "succeeded", "failed", "success_rate")
            ],
            style_data_conditional=[PREFIX_STYLE, *RATE_SHADING],
            style_header={"fontWeight": "600"},
        ),
        html.Div(id="failures", style={"marginTop": "24px"}),
    ],
)


@callback(
    Output("table", "data"),
    Output("row-count", "children"),
    Output("hide-complete", "options"),
    Input("latest-only", "value"),
    Input("hide-complete", "value"),
)
def update_table(latest_only, hide_complete):
    latest_only = "latest" in latest_only
    data = table_rows(latest_only, "hide" in hide_complete)
    complete = sum(1 for row in table_rows(latest_only, False) if row["success_rate"] == 100)
    return (
        data,
        f"{len(data)} rows across {len({row['source'] for row in data})} sources",
        [{"label": f" Hide prefixes that fully normalize (n={complete})", "value": "hide"}],
    )


@callback(
    Output("failures", "children"),
    Input("table", "active_cell"),
    # The viewport, not `data`: active_cell.row indexes the sorted, filtered page.
    Input("table", "derived_viewport_data"),
)
def show_failures(active_cell, data):
    """List the unnormalized CURIEs behind the clicked row.

    Read on demand rather than indexed up front: the biggest failures file is
    under 7 MB, and preloading all 87 of them would cost 3.2M lines for nothing.
    """
    if not active_cell or active_cell["row"] >= len(data):
        return None
    row = data[active_cell["row"]]

    prefix = row["prefix"]
    curies = []
    for path in row["failures_paths"]:
        with open(path) as failures:
            curies.extend(
                line.strip()
                for line in failures
                if line.strip() and line.split(":")[0].strip().upper() == prefix
            )
    curies = sorted(set(curies))

    if not curies:
        return html.P(
            f"No unnormalized CURIEs recorded for {prefix} in {row['source']} "
            "(some builds ship no normalization_failures.txt).",
            style={"color": "#555"},
        )

    shown = curies[:MAX_CURIES_SHOWN]
    malformed = [c for c in shown if curie.malformed(c)]
    heading = f"{len(curies):,} unnormalized {prefix} CURIEs in {row['source']}"
    if len(shown) < len(curies):
        heading += f" (showing the first {len(shown):,})"
    return [
        html.H2(heading, style={"fontSize": "1.2em"}),
        html.P(
            f"{len(malformed)} of these are malformed, which may be the whole explanation.",
            style={"color": "#a33"},
        )
        if malformed
        else None,
        dcc.Markdown(
            " · ".join(curie.as_markdown(c) for c in shown),
            link_target="_blank",
            style={"lineHeight": "2"},
        ),
    ]


def main() -> None:
    app.run(debug=True)
