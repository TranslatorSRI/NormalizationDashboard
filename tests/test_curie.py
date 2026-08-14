"""Checks for CURIE linking and malformed-CURIE detection.

Run: uv run python tests/test_curie.py

The malformed examples are real strings taken from normalization_failures.txt.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from normalization_dashboard import curie


def main():
    # Well formed, prefix in the Biolink map -> link straight to the source.
    assert curie.malformed("MONDO:0001034") is None
    assert curie.url("MONDO:0001034") == "http://purl.obolibrary.org/obo/MONDO_0001034"
    # Prefix case does not matter, NodeNorm resolves prefixes case-insensitively.
    assert curie.url("mondo:0001034") == curie.url("MONDO:0001034")

    # Well formed but not in the Biolink map -> Bioregistry resolves it anyway.
    # PathBank is the largest such prefix: 215,953 unnormalized CURIEs.
    assert curie.url("PathBank:SMP0000055") == "https://bioregistry.io/PathBank:SMP0000055"

    # Malformed: no link, and a reason that explains the normalization failure.
    for value, reason in (
        ("rhea:RHEA:13065", "more than one ':'"),
        ("CL:0000089 ∩ UBERON:0000473", "contains whitespace"),
        ("UniProtKB:B3DHD6 Q6XCC7", "contains whitespace"),
        ("UniProtKB:", "empty local identifier"),
        ("MONDO_1034", "no ':' separator"),
        (":0001034", "empty prefix"),
    ):
        assert curie.malformed(value) == reason, f"{value}: {curie.malformed(value)}"
        assert curie.url(value) is None, value
        assert reason in curie.as_markdown(value, explain=True)
        # A table cell gets the warning sign but not the wide explanation.
        assert curie.as_markdown(value) == f"`{value}` ⚠"

    # Linked, and monospaced so the exact characters of a CURIE are visible.
    assert curie.as_markdown("MONDO:0001034").startswith("[`MONDO:0001034`](")

    print(f"OK: {len(curie.PREFIX_MAP)} Biolink prefixes loaded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
