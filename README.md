# NormalizationDashboard

A dashboard to track normalization across KGX releases.

The NCATS Translator DINGO pipeline normalizes KGX node CURIEs through
[NodeNorm](https://github.com/biothings/NodeNormalizationAPI), which uses cliques from
[Babel](https://github.com/NCATSTranslator/Babel), and publishes the results to
[KGX Storage](https://kgx-storage.ci.transltr.io/). This project summarizes how that normalization
went: which prefixes normalized to what, and which CURIEs failed to normalize (so they can be
prioritized for a future Babel ingest).

## Syncing the normalization data

Each KGX build directory contains `normalization-metadata.json`, `normalization_failures.txt`, and
`normalization_map.json` alongside multi-gigabyte `normalized_nodes.jsonl` / `normalized_edges.jsonl`
files. The sync script mirrors *only* the three normalization files, preserving KGX Storage's folder
layout, and deletes local files that have disappeared upstream.

```bash

brew install rclone            # or apt install rclone
./scripts/sync-kgx-normalization.sh
```

That writes ~970 MB into `data/kgx-storage.ci.transltr.io/` (gitignored). Any extra arguments are
passed through to `rclone`:

```bash
./scripts/sync-kgx-normalization.sh /tmp/kgxtest --dry-run
./scripts/sync-kgx-normalization.sh data/kgx-storage.ci.transltr.io --exclude "**/normalization_map.json"
```

Skipping the maps with that last `--exclude` brings the mirror down to ~56 MB, which is enough for
the prefix-summary and normalization-failure reports.

**Known upstream issue:** ubergraph's 247 MB `normalization_map.json` returns 502 from KGX Storage
and cannot be downloaded, so a full sync exits non-zero. See [CLAUDE.md](CLAUDE.md) for details.

## Running the dashboard

```bash
uv run normalization-dashboard     # http://127.0.0.1:8050
```

A local [Dash](https://plotly.com/dash/) app. The first view is every data source × CURIE prefix,
sorted from the worst normalization rate to the best — the ranking that says which prefixes Babel
should ingest next. Sort by **Failed** instead to rank by how many CURIEs are actually at stake: a
prefix at 0% of 3 CURIEs and one at 0% of 216,000 sort identically by percentage.

Prefixes are pooled case-insensitively, because NodeNorm resolves CURIE prefixes case-insensitively
(`ENSEMBL:`, `Ensembl:` and `ensembl:` all resolve alike); the spellings actually seen in the files
are shown in the "Observed as" column. Prefixes that fully normalize are hidden by default, and each
version links back to the normalization output directory in KGX Storage that the numbers came from.

Each row carries up to five **Example** CURIEs that actually failed to normalize, spelled and cased
as the source spells them — often the fastest explanation of a 0% row. PathBank's failures turn out
to be `PathBank:Reaction_13124` and `PathBank:Compound_102409`, not pathway identifiers at all.

**Click a row** to list the CURIEs that failed to normalize for that source and prefix, grouped by
*why* they plausibly failed — malformed first (`rhea:RHEA:13065`, `CL:0000089 ∩ UBERON:0000473`,
`UniProtKB:B3DHD6 Q6XCC7`), then prefixes the Biolink model has never heard of, then the ordinary
"no Babel clique" remainder. Within each reason they are broken down by CURIE shape, which is how
pathbank's 215,953 failures resolve into 175,039 `PathBank:Reaction_…`, 31,182 `PathBank:Compound_…`
and 8,886 `PathBank:ProteinComplex_…`. Every CURIE links out — via the Biolink prefix map, falling
back to [Bioregistry](https://bioregistry.io/) — so you can check what the identifier actually is.

It runs locally, which keeps individual CURIEs off the public web and leaves the deployment question
(GitHub Pages export, Kubernetes, or folding into another Translator dashboard) open.

## Development

```bash
uv sync
uv run python tests/test_loader.py
```
