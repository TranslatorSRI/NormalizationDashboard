"""Invariants for the metadata loader. Run: uv run python tests/test_loader.py

Checks against the real mirror rather than a fixture -- the failure mode worth
catching is a new DINGO build whose shape we did not expect.
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from normalization_dashboard.loader import DEFAULT_MIRROR, load_rows, summarize


def main():
    if not DEFAULT_MIRROR.exists():
        print(f"SKIP: no mirror at {DEFAULT_MIRROR}; run scripts/sync-kgx-normalization.sh")
        return 0

    rows = load_rows()
    assert rows, "no rows loaded"

    for row in rows:
        where = f"{row['source']} {row['source_version']} {row['prefix']}"
        assert row["succeeded"] + row["failed"] == row["total"], where
        if row["total"]:
            expected = round(100 * row["succeeded"] / row["total"], 2)
            assert abs(row["success_rate"] - expected) <= 0.01, f"{where}: {row['success_rate']} != {expected}"
        if row["normalized_to"]:
            assert sum(row["normalized_to"].values()) == row["succeeded"], where
        assert row["failures_path"] is None or Path(row["failures_path"]).exists(), where

    latest = {(row["source"], row["source_version"], row["transform"]) for row in rows if row["is_latest"]}
    per_source = Counter(source for source, _, _ in latest)
    assert all(count == 1 for count in per_source.values()), f"multiple latest builds: {per_source}"
    assert per_source.keys() == {row["source"] for row in rows}, "a source has no latest build"

    summary = summarize(rows)
    assert sum(row["total"] for row in summary) == sum(row["total"] for row in rows), "summarize lost rows"
    keys = Counter((row["source"], row["prefix"]) for row in summary)
    assert all(count == 1 for count in keys.values()), "summarize left duplicate (source, prefix)"
    assert all(row["prefix"] == row["prefix"].upper() for row in summary), "summary prefix not case-folded"

    latest_summary = summarize([row for row in rows if row["is_latest"]])
    print(
        f"OK: {len(rows)} rows over {len(per_source)} sources, "
        f"{len({row['prefix_key'] for row in rows})} case-insensitive prefixes; "
        f"{len(summary)} summary rows ({len(latest_summary)} latest-only)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
