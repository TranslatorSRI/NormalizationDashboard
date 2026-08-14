"""Local Dash app: every data source x CURIE prefix, worst normalization first."""

import os
from collections import defaultdict

from dash import Dash, Input, Output, callback, dash_table, dcc, html

from normalization_dashboard import curie, loader
from normalization_dashboard.loader import load_failure_examples, load_rows, summarize

EXAMPLE_COUNT = 5

# (key, header, markdown?) -- CURIE Prefix leads, it is the row's subject.
COLUMNS = [
    ("prefix", "CURIE Prefix", False),
    ("source", "Source", False),
    ("source_versions_md", "Version", True),
    # No "Observed as" column: it equals the prefix in every row today, and the
    # Example columns show the original casing anyway. summarize() still carries
    # the field for whenever one source does spell a prefix two ways.
    ("total", "Total", False),
    ("succeeded", "Succeeded", False),
    ("failed", "Failed", False),
    ("success_rate", "Success %", False),
    *[(f"example_{n}", f"Example {n}", True) for n in range(1, EXAMPLE_COUNT + 1)],
    # No "Normalized to" column: at 200+ characters for semmeddb it was the one
    # value wide enough to force a scrollbar by itself, and where a prefix
    # normalizes *to* is a renormalization-diff question, not a today question.
    # summarize() still carries normalized_to_str for when that work starts.
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

# Clicking anywhere in a row highlights the whole row; the single active cell
# gets no colour of its own, since which cell you happened to hit means nothing.
ACTIVE_CELL_STYLE = {"if": {"state": "active"}, "backgroundColor": "transparent"}
SELECTED_ROW_COLOUR = "#dbe6ff"

MAX_CURIES_SHOWN = 30
EXAMPLES_PER_GROUP = 6

app = Dash(__name__)
ROWS = load_rows()
EXAMPLES = load_failure_examples(ROWS, limit=EXAMPLE_COUNT)


def table_rows(latest_only, hide_complete):
    rows = [row for row in ROWS if row["is_latest"]] if latest_only else ROWS
    summary = summarize(rows)
    if hide_complete:
        summary = [row for row in summary if row["success_rate"] < 100]
    for row in summary:
        examples = EXAMPLES.get((row["source"], row["prefix"]), ())
        for number in range(1, EXAMPLE_COUNT + 1):
            example = examples[number - 1] if number <= len(examples) else None
            row[f"example_{number}"] = curie.as_markdown(example) if example else ""
    return summary


app.layout = html.Div(
    # No maxWidth anywhere: the table wants every pixel the window has, and the
    # intro should line up with it rather than sit in a narrow column.
    style={"margin": "0 auto", "padding": "0 16px", "fontFamily": "system-ui, sans-serif"},
    children=[
        html.H1("Normalization by source and CURIE prefix"),
        html.Ul(id="summary", style={"lineHeight": "1.7"}),
        dcc.Checklist(
            id="latest-only",
            options=[{"label": " Latest build per source only", "value": "latest"}],
            value=["latest"],
        ),
        dcc.Checklist(id="hide-complete", options=[], value=["hide"]),
        html.Div(id="row-count", style={"margin": "8px 0"}),
        dash_table.DataTable(
            id="table",
            columns=[
                {"name": name, "id": key, **({"presentation": "markdown"} if md else {})}
                for key, name, md in COLUMNS
            ],
            markdown_options={"link_target": "_blank"},
            # Safety net for narrow windows: scroll the table, never the page.
            style_table={"overflowX": "auto"},
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
            style_data_conditional=[PREFIX_STYLE, *RATE_SHADING, ACTIVE_CELL_STYLE],
            style_header={"fontWeight": "600"},
        ),
        html.Div(id="failures", style={"marginTop": "24px"}),
    ],
)


# Fixed notes, listed after the figures so the numbers come first.
NOTES = [
    "Prefixes are pooled case-insensitively, because NodeNorm resolves CURIE "
    "prefixes case-insensitively.",
    "Sort by Failed to rank by how many CURIEs are at stake rather than by "
    "percentage: 0% of 3 and 0% of 215,953 rank identically by rate.",
    "Click a row to list the CURIEs that failed to normalize, grouped by why "
    "they plausibly failed.",
    "CURIEs are counted once per source, so one appearing in three sources "
    "counts three times.",
]


@callback(
    Output("table", "data"),
    Output("summary", "children"),
    Output("row-count", "children"),
    Output("hide-complete", "options"),
    Input("latest-only", "value"),
    Input("hide-complete", "value"),
)
def update_table(latest_only, hide_complete):
    latest_only = "latest" in latest_only
    everything = table_rows(latest_only, False)
    data = table_rows(latest_only, "hide" in hide_complete)
    complete = sum(1 for row in everything if row["success_rate"] == 100)
    return (
        data,
        summary_items(everything),
        f"{len(data):,} rows displayed",
        [{"label": f" Hide prefixes that fully normalize (n={complete})", "value": "hide"}],
    )


def summary_items(everything):
    """The headline figures, then the fixed notes, as one scannable list.

    These describe the whole build selection rather than the visible rows: an
    overall score that moved when you hid the fully-normalizing prefixes would
    be worse than useless.
    """
    total = sum(row["total"] for row in everything)
    succeeded = sum(row["succeeded"] for row in everything)
    figures = [
        f"{succeeded:,} of {total:,} CURIEs normalized "
        f"({100 * succeeded / total:.1f}%)",
        f"{total - succeeded:,} CURIEs failed to normalize",
        f"{len({row['source'] for row in everything})} sources, "
        f"{len({row['prefix'] for row in everything})} CURIE prefixes, "
        f"{len(everything):,} source/prefix pairs",
    ]
    return [html.Li(html.Strong(figure)) for figure in figures] + [
        html.Li(note) for note in NOTES
    ]


def failures_paths(source, prefix, latest_only):
    """The failures files behind one summary row.

    Looked up here rather than carried in the table: DataTable cells may only
    hold scalars, and the browser rejects the whole table if a row holds a list.
    """
    return sorted(
        {
            row["failures_path"]
            for row in ROWS
            if row["source"] == source
            and row["prefix_key"] == prefix
            and row["failures_path"]
            and (row["is_latest"] or not latest_only)
        }
    )


@callback(
    Output("table", "style_data_conditional"),
    Input("table", "active_cell"),
    Input("table", "derived_viewport_data"),
)
def highlight_selected_row(active_cell, data):
    """Colour the whole clicked row, matched on identity rather than position.

    A row index would follow the viewport rather than the row once the table is
    re-sorted or filtered.
    """
    styles = [PREFIX_STYLE, *RATE_SHADING, ACTIVE_CELL_STYLE]
    if active_cell and data and active_cell["row"] < len(data):
        row = data[active_cell["row"]]
        styles.append(
            {
                "if": {
                    "filter_query": f'{{prefix}} = "{row["prefix"]}" '
                    f'&& {{source}} = "{row["source"]}"'
                },
                "backgroundColor": SELECTED_ROW_COLOUR,
            }
        )
    return styles


@callback(
    Output("failures", "children"),
    Input("table", "active_cell"),
    # The viewport, not `data`: active_cell.row indexes the sorted, filtered page.
    Input("table", "derived_viewport_data"),
    Input("latest-only", "value"),
)
def show_failures(active_cell, data, latest_only):
    """List the unnormalized CURIEs behind the clicked row.

    Read on demand rather than indexed up front: the biggest failures file is
    under 7 MB, and preloading all 87 of them would cost 3.2M lines for nothing.
    """
    if not active_cell or not data or active_cell["row"] >= len(data):
        return None
    row = data[active_cell["row"]]

    prefix = row["prefix"]
    curies = []
    for path in failures_paths(row["source"], prefix, "latest" in latest_only):
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

    by_problem = defaultdict(list)
    for value in curies:
        by_problem[curie.problem(value)].append(value)
    ordered = sorted(
        by_problem.items(), key=lambda item: (curie.problem_rank(item[0]), -len(item[1]))
    )
    return [
        html.H2(
            f"{len(curies):,} unnormalized {prefix} CURIEs in {row['source']}",
            style={"fontSize": "1.2em"},
        ),
        html.Ul(
            [_problem_item(label, members) for label, members in ordered],
            style={"lineHeight": "1.8"},
        ),
    ]


def _problem_item(label, members):
    """One reason these CURIEs failed, broken down by CURIE shape underneath.

    A single shape is rendered inline: nesting one bullet under another says
    nothing.
    """
    heading = html.Strong(
        f"{len(members):,} — {label}",
        style={"color": "#a33"} if label.startswith(curie.MALFORMED) else None,
    )
    shapes = curie.group_by_stem(members)
    if shapes and len(shapes) > 1:
        return html.Li([heading, html.Ul([_shape_item(*shape) for shape in shapes])])
    if shapes:
        return html.Li([heading, " ", _examples(members)])
    # No shared shape to group on, so just list them, spread across the whole set.
    listed = loader.spread(members, MAX_CURIES_SHOWN)
    note = (
        f" (showing {len(listed)} spread across {len(members):,})"
        if len(listed) < len(members)
        else ""
    )
    return html.Li(
        [
            heading,
            note,
            html.Ul([html.Li(_examples([value], 1)) for value in listed]),
        ]
    )


def _shape_item(shape, count, members):
    return html.Li([html.Strong(f"{count:,} × {shape}…  "), _examples(members)])


def _examples(members, limit=EXAMPLES_PER_GROUP):
    """A few members spread across the whole group, linked."""
    return dcc.Markdown(
        " · ".join(
            curie.as_markdown(value, explain=True)
            for value in loader.spread(members, limit)
        ),
        link_target="_blank",
        style={"display": "inline"},
    )


def main() -> None:
    # PORT= lets a second instance run alongside one already on 8050.
    app.run(debug=True, port=int(os.environ.get("PORT", 8050)))
