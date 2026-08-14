"""Turn CURIEs into links, and spot the ones that are malformed.

A CURIE that cannot be normalized is sometimes just missing from Babel, and
sometimes malformed in a way that explains the failure by itself
(`rhea:RHEA:13065`, `CL:0000089 ∩ UBERON:0000473`, `UniProtKB:B3DHD6 Q6XCC7`).
Telling those apart is the point of this module.
"""

import json
import re
from collections import Counter
from pathlib import Path

# Vendored from biolink-model so the app works offline; 266 prefixes, refresh with:
#   curl -sL https://raw.githubusercontent.com/biolink/biolink-model/master/src/biolink_model/prefixmaps/biolink-model-prefix-map.json \
#        -o src/normalization_dashboard/biolink-model-prefix-map.json
PREFIX_MAP_PATH = Path(__file__).parent / "biolink-model-prefix-map.json"

# Prefixes are matched case-insensitively, because NodeNorm resolves them that way.
PREFIX_MAP = {
    prefix.upper(): uri_stem
    for prefix, uri_stem in json.loads(PREFIX_MAP_PATH.read_text()).items()
}

# Resolves nearly everything the Biolink map does not, including PathBank.
BIOREGISTRY_URL = "https://bioregistry.io/{}"


def malformed(curie):
    """Why this is not a well-formed CURIE, or None if it looks fine."""
    if any(character.isspace() for character in curie):
        return "contains whitespace"
    prefix, separator, local_id = curie.partition(":")
    if not separator:
        return "no ':' separator"
    if not prefix:
        return "empty prefix"
    if not local_id:
        return "empty local identifier"
    if ":" in local_id:
        return "more than one ':'"
    return None


def url(curie):
    """A URL to look this CURIE up, or None if it is too malformed to try."""
    if malformed(curie):
        return None
    prefix, _, local_id = curie.partition(":")
    uri_stem = PREFIX_MAP.get(prefix.upper())
    return uri_stem + local_id if uri_stem else BIOREGISTRY_URL.format(curie)


MALFORMED = "malformed"
UNKNOWN_PREFIX = "prefix unknown to the Biolink model"
NO_CLIQUE = "no Babel clique for this identifier"

# Most actionable first: a malformed CURIE is a transform bug we can point at, an
# unknown prefix is a modelling gap, and the rest is ordinary Babel coverage.
PROBLEM_ORDER = {MALFORMED: 0, UNKNOWN_PREFIX: 1, NO_CLIQUE: 2}


def problem(curie):
    """Why this CURIE plausibly failed to normalize.

    The prefix check is a signal, not a proven cause -- Babel decides coverage
    for itself, not from the Biolink prefix map -- but a prefix the model has
    never heard of is rarely a coincidence when its CURIEs all fail.
    """
    reason = malformed(curie)
    if reason:
        return f"{MALFORMED}: {reason}"
    if curie.partition(":")[0].upper() not in PREFIX_MAP:
        return UNKNOWN_PREFIX
    return NO_CLIQUE


def problem_rank(label):
    return PROBLEM_ORDER.get(label.split(": ")[0], len(PROBLEM_ORDER))


def stem(curie):
    """The shape of a CURIE: everything up to its first digit.

    `PathBank:Reaction_13124` -> `PathBank:Reaction_`, `Ensembl:ENSRNOG00000019082`
    -> `Ensembl:ENSRNOG`. Grouping on this splits pathbank's failures into
    Reaction_, Compound_ and ProteinComplex_, and bgee's into one group per
    species, which says far more than a flat list of 215,953 identifiers.
    """
    prefix, _, local_id = curie.partition(":")
    return prefix + ":" + re.match(r"[^0-9]*", local_id).group(0)


# Above this many groups, the stem is not finding real structure -- InChIKeys
# have no digits to split on, so 87 of them make 87 groups of one.
MAX_USEFUL_GROUPS = 12


def group_by_stem(curies):
    """[(stem, count, [curies in that group])], biggest group first.

    Returns None when grouping would not be informative, so the caller can fall
    back to a plain list.
    """
    counts = Counter(stem(curie) for curie in curies)
    if len(counts) > MAX_USEFUL_GROUPS:
        return None
    grouped = {}
    for curie in curies:
        grouped.setdefault(stem(curie), []).append(curie)
    return [
        (shape, counts[shape], grouped[shape])
        for shape, _ in counts.most_common()
    ]


def as_markdown(curie, explain=False):
    """One CURIE, monospaced so its exact characters are visible, linked if it can be.

    Monospacing matters here: it is how `UniProtKB:B3DHD6 Q6XCC7` reads as one
    broken string rather than as ordinary prose. `explain` adds why a CURIE is
    not linkable, which is too wide for a table cell but wanted in the listing.
    """
    link = url(curie)
    if link:
        return f"[`{curie}`]({link})"
    return f"`{curie}`" + (f" ⚠ {malformed(curie)}" if explain else " ⚠")
