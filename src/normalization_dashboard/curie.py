"""Turn CURIEs into links, and spot the ones that are malformed.

A CURIE that cannot be normalized is sometimes just missing from Babel, and
sometimes malformed in a way that explains the failure by itself
(`rhea:RHEA:13065`, `CL:0000089 ∩ UBERON:0000473`, `UniProtKB:B3DHD6 Q6XCC7`).
Telling those apart is the point of this module.
"""

import json
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
