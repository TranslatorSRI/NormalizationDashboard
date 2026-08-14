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

    # Grouping on CURIE shape: everything up to the first digit.
    assert curie.stem("PathBank:Reaction_13124") == "PathBank:Reaction_"
    assert curie.stem("Ensembl:ENSRNOG00000019082") == "Ensembl:ENSRNOG"
    assert curie.stem("FOODON:02021990") == "FOODON:"

    groups = curie.group_by_stem(
        ["PathBank:Reaction_1", "PathBank:Reaction_2", "PathBank:Compound_9"]
    )
    assert [(shape, count) for shape, count, _ in groups] == [
        ("PathBank:Reaction_", 2),
        ("PathBank:Compound_", 1),
    ], groups

    # InChIKeys have no digits to split on, so every one becomes its own group.
    # Grouping declines rather than printing a list of groups of one.
    inchikeys = [f"INCHIKEY:{chr(65 + n)}FOFVIBWSLOHFR-QDMKHBRRSA-N" for n in range(20)]
    assert curie.group_by_stem(inchikeys) is None

    print(f"OK: {len(curie.PREFIX_MAP)} Biolink prefixes loaded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
