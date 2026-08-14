"""Load normalization metadata out of a local KGX Storage mirror.

Pure data, no Dash imports, so a notebook or a static-JSON exporter can reuse it.
See CLAUDE.md for the mirror layout and what each file contains.
"""

import json
from collections import defaultdict
from pathlib import Path

MIRROR_NAME = Path("data/kgx-storage.ci.transltr.io")


def _default_mirror():
    """Find the mirror whether or not we were started from the repo root.

    An IDE run configuration or a `uv run --project` from elsewhere sets a
    different working directory, which used to load zero rows in silence.
    """
    from_repo = Path(__file__).parents[2] / MIRROR_NAME  # src/<pkg>/loader.py -> repo
    return next(
        (path for path in (MIRROR_NAME, from_repo) if path.is_dir()),
        from_repo if from_repo.parent.parent.is_dir() else MIRROR_NAME,
    )


DEFAULT_MIRROR = _default_mirror()

# The mirror directory is named after the host, so the remote URL of any mirrored
# file is the host plus its path under the mirror root.
KGX_STORAGE_URL = "https://kgx-storage.ci.transltr.io/data"


def _normalized_to_str(normalized_to):
    """'NCBIGene (91678); UniProtKB (82176)', biggest target first.

    The count is bracketed so a prefix and its count cannot be misread as a
    CURIE: 'CHEBI 5' looked like a malformed one.
    """
    return "; ".join(
        f"{prefix} ({count})"
        for prefix, count in sorted(normalized_to.items(), key=lambda kv: -kv[1])
    )


def spread(values, limit):
    """`limit` values spaced evenly across the list, not just its head.

    A prefix's failures are usually grouped in file order, so the first few are
    often all alike; a spread shows whether the rest of them differ.
    """
    if len(values) <= limit:
        return list(values)
    step = len(values) / limit
    return [values[int(index * step)] for index in range(limit)]


def load_failure_examples(rows, limit=5):
    """A few real unnormalized CURIEs per (source, uppercased prefix).

    One pass per failures file rather than per row -- 87 files, 3.2M lines, under
    a second, holding only one file's CURIEs at a time. CURIEs keep the case the
    file spells them with, which is half the point: seeing `Ensembl:ENSRNOG…` or
    `PathBank:Reaction_13124` says more about why a prefix fails than the folded
    prefix name does.
    """
    paths = {}
    for row in rows:
        if row["failures_path"]:
            paths.setdefault(row["failures_path"], (row["source"], row["is_latest"]))

    examples = {}
    # Latest builds first, so a source's examples come from its current build.
    for path, (source, _) in sorted(paths.items(), key=lambda item: not item[1][1]):
        by_prefix = defaultdict(list)
        with open(path) as failures:
            for line in failures:
                curie = line.strip()
                if curie:
                    by_prefix[curie.split(":")[0].upper()].append(curie)
        for prefix, curies in by_prefix.items():
            examples.setdefault(
                (source, prefix), spread(list(dict.fromkeys(curies)), limit)
            )
    return examples


def load_rows(mirror=DEFAULT_MIRROR):
    """One row per (build, prefix), with the prefix spelled as the file spells it.

    `prefix_key` is the case-insensitive grouping key: NodeNorm resolves CURIE
    prefixes case-insensitively, so ENSEMBL and Ensembl are the same prefix.
    """
    mirror = Path(mirror)
    if not mirror.is_dir():
        raise FileNotFoundError(
            f"No KGX Storage mirror at {mirror.resolve()} -- run "
            "./scripts/sync-kgx-normalization.sh from the repository root first."
        )
    rows = []
    for metadata_path in sorted(mirror.glob("*/*/*/*/normalization-metadata.json")):
        source, source_version, transform, normalization = metadata_path.relative_to(
            mirror
        ).parts[:4]
        metadata = json.loads(metadata_path.read_text())
        failures_path = metadata_path.parent / "normalization_failures.txt"
        for prefix, stats in metadata.get("normalization_by_prefix", {}).items():
            normalized_to = stats.get("normalized_to", {})
            rows.append(
                {
                    "source": source,
                    "source_version": source_version,
                    "transform": transform.removeprefix("transform_"),
                    "normalization": normalization.removeprefix("normalization_"),
                    "babel_version": metadata.get("babel_version"),
                    "build_url": "/".join(
                        (KGX_STORAGE_URL, source, source_version, transform, normalization, "")
                    ),
                    "prefix": prefix,
                    "prefix_key": prefix.upper(),
                    "total": stats["total"],
                    "succeeded": stats["succeeded"],
                    "failed": stats["failed"],
                    # Recomputed, not taken from the file: the pipeline truncates
                    # success_rate (99.556 -> 99.55), which would not agree with the
                    # rates summarize() derives from pooled counts.
                    "success_rate": round(100 * stats["succeeded"] / stats["total"], 2)
                    if stats["total"]
                    else 0.0,
                    "normalized_to": normalized_to,
                    "normalized_to_str": _normalized_to_str(normalized_to),
                    "failures_path": str(failures_path)
                    if failures_path.exists()
                    else None,
                }
            )
    _mark_latest(rows, mirror)
    return rows


def _mark_latest(rows, mirror):
    """Flag the rows belonging to each source's current build.

    latest-build.json names the current transform; where it is missing (or names a
    build we have not mirrored) fall back to the most recently modified build.
    """
    builds = defaultdict(set)  # source -> {(source_version, transform)}
    for row in rows:
        builds[row["source"]].add((row["source_version"], row["transform"]))

    latest = {}
    for source, source_builds in builds.items():
        current = None
        try:
            build = json.loads((mirror / source / "latest-build.json").read_text())
            current = (build["source_version"], build["transform_version"])
        except (OSError, KeyError, json.JSONDecodeError):
            pass
        if current not in source_builds:
            current = max(
                source_builds,
                key=lambda b: (mirror / source / b[0] / f"transform_{b[1]}").stat().st_mtime,
            )
        latest[source] = current

    for row in rows:
        row["is_latest"] = (
            latest[row["source"]] == (row["source_version"], row["transform"])
        )


def summarize(rows):
    """Pool rows by (source, case-insensitive prefix).

    Rates are recomputed from the summed counts rather than averaged, and the
    spellings actually seen are reported so a case merge is never silent.
    """
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["source"], row["prefix_key"])].append(row)

    summary = []
    for (source, prefix_key), group in grouped.items():
        total = sum(row["total"] for row in group)
        succeeded = sum(row["succeeded"] for row in group)
        normalized_to = defaultdict(int)
        for row in group:
            for target, count in row["normalized_to"].items():
                normalized_to[target.upper()] += count
        # One link per build the row pools, pointing at the normalization output
        # directory these numbers came from.
        build_links = {
            row["source_version"]: row["build_url"]
            for row in sorted(group, key=lambda row: row["source_version"])
        }
        summary.append(
            {
                "source": source,
                "source_versions": ", ".join(build_links),
                "source_versions_md": ", ".join(
                    f"[{version}]({url})" for version, url in build_links.items()
                ),
                "builds": len({(r["source_version"], r["transform"]) for r in group}),
                "prefix": prefix_key,
                "observed_as": ", ".join(sorted({row["prefix"] for row in group})),
                "total": total,
                "succeeded": succeeded,
                "failed": total - succeeded,
                "success_rate": round(100 * succeeded / total, 2) if total else 0.0,
                "normalized_to_str": _normalized_to_str(normalized_to),
            }
        )
    return sorted(summary, key=lambda row: (row["success_rate"], -row["failed"]))
