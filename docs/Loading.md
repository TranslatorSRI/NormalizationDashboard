# Loading the data and running the dashboard

Everything needed to get from a fresh checkout to a working dashboard. The short version:

```bash
brew install rclone                        # or apt install rclone
uv sync
./scripts/sync-kgx-normalization.sh        # ~970 MB, a few minutes
uv run normalization-dashboard             # http://127.0.0.1:8050
```

## Prerequisites

| | |
|---|---|
| [uv](https://docs.astral.sh/uv/) | runs the project; `uv sync` installs Dash |
| [rclone](https://rclone.org/) | the entire downloader — `brew install rclone` / `apt install rclone` |
| disk | ~970 MB for a full mirror, or ~56 MB without the normalization maps |
| network | HTTPS to `kgx-storage.ci.transltr.io`; **no AWS credentials needed** |

No AWS credentials are needed, and none would help for listing: the `s3://kgx-translator-ingests`
bucket is not anonymously listable, so the site's HTML directory listings are the only public index.
rclone's `:http:` backend walks them.

## Step 1 — mirror the normalization data

```bash
./scripts/sync-kgx-normalization.sh
```

One `rclone sync` call. It walks every build directory in KGX Storage and downloads only four
kinds of file, preserving the remote folder layout and deleting local files that have disappeared
upstream:

- `normalization-metadata.json` — per-prefix counts, the input for the whole table
- `normalization_failures.txt` — one unnormalized CURIE per line
- `normalization_map.json` — source CURIE → normalized CURIE, for the future renormalization work
- `latest-build.json` — which build is current for each source

The multi-gigabyte `normalized_nodes.jsonl` and `normalized_edges.jsonl` files are **never fetched**.
The `--include` filters apply to the listing walk, so only directory HTML is requested for them.

### Variants

```bash
# See what would transfer, without downloading
./scripts/sync-kgx-normalization.sh /tmp/kgxtest --dry-run

# Skip the maps: ~56 MB instead of ~970 MB, enough for everything the dashboard shows today
./scripts/sync-kgx-normalization.sh data/kgx-storage.ci.transltr.io \
    --exclude "**/normalization_map.json"

# Mirror somewhere else
./scripts/sync-kgx-normalization.sh /some/other/path
```

Any argument after the destination is passed straight through to `rclone`.

### What you end up with

```
data/kgx-storage.ci.transltr.io/
├── {source}/
│   ├── latest-build.json
│   └── {source_version}/
│       └── transform_{hash}/
│           └── normalization_{babel}_{nn}_{code}_{conflated}_{strict}/
│               ├── normalization-metadata.json
│               ├── normalization_failures.txt
│               └── normalization_map.json
```

As of August 2026: 31 sources, 90 build directories, ~970 MB — 298 files, of which 297 arrive (see
the ubergraph 502 under Troubleshooting). The directory is named after the host it came from, and
`/data/` is gitignored, so nothing here is ever committed.

Re-running the script is incremental: unchanged files are skipped on size and modification time, so
a no-op sync transfers nothing. The listing walk still takes a few minutes, since every directory
must be fetched as HTML.

## Step 2 — check the mirror

```bash
uv run python tests/test_loader.py    # OK: 587 rows over 31 sources, 84 case-insensitive prefixes…
uv run python tests/test_curie.py     # OK: 266 Biolink prefixes loaded
```

No framework, no fixtures — these assert invariants against the real mirror (counts reconcile,
rates match the counts, exactly one latest build per source, summary values are all scalars). The
loader check skips cleanly if the mirror has not been synced yet.

## Step 3 — run the dashboard

```bash
uv run normalization-dashboard          # http://127.0.0.1:8050
PORT=8051 uv run normalization-dashboard   # second instance alongside the first
```

Startup reads the 90 metadata files and scans the 87 failures files once to collect example CURIEs —
3.2M lines, under a second. Nothing is cached to disk; restart to pick up a fresh sync.

The mirror is found relative to the repository even when the app is launched from another working
directory, so an IDE run configuration works without extra setup. If no mirror is found at all, the
app fails at startup naming the sync script rather than rendering an empty table.

## Keeping it current

- **New KGX builds**: re-run `./scripts/sync-kgx-normalization.sh`, then restart the app.
- **Biolink prefix map** (vendored so the app works offline, 266 prefixes, 14 KB):

  ```bash
  curl -sL https://raw.githubusercontent.com/biolink/biolink-model/master/src/biolink_model/prefixmaps/biolink-model-prefix-map.json \
       -o src/normalization_dashboard/biolink-model-prefix-map.json
  ```

  It decides which CURIEs link directly to their source; the rest fall back to `bioregistry.io`.

## Hosting

**There is no static export yet.** The dashboard is a local Dash server, which is deliberate for
now: individual unnormalized CURIEs stay off the public web while we work out what the dashboard
should show, and it keeps the door open to folding this into another Translator dashboard later.

When we do want it hosted, the shape of the work is already set up for it:

- `loader.py` has no Dash imports and returns plain `list[dict]`, so a static-JSON exporter can
  reuse `load_rows()`, `summarize()` and `load_failure_examples()` without touching the app.
- The prefix summary is genuinely small — 242 source/prefix rows, well under a megabyte as JSON —
  so a GitHub Pages page reading a committed JSON file is viable for goal 1.
- The 898,042 distinct unnormalized CURIEs are the part that would need a decision, both for size
  and for whether they should be public at all.

## Troubleshooting

**`502 Bad Gateway` on ubergraph's `normalization_map.json`, sync exits non-zero.** Expected, and
upstream. That one file is 247 MB and the origin appears to buffer JSON responses in memory; a 48 MB
map from the same source downloads fine. The sync completes 297 of 298 files. Add
`--exclude "**/ubergraph/**/normalization_map.json"` if the non-zero exit is a nuisance.

**`Port 8050 is in use by another program.`** Another instance is still running. `lsof -ti:8050`
finds it, or use `PORT=8051`.

**`No KGX Storage mirror at …`** The sync has not been run, or was pointed somewhere else. Run
`./scripts/sync-kgx-normalization.sh` from the repository root.

**The table is empty, or shows fewer rows than expected.** Check the mirror actually has metadata
files: `find data/kgx-storage.ci.transltr.io -name normalization-metadata.json | wc -l` should
report 90.
