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

## Development

```bash
uv sync
```
