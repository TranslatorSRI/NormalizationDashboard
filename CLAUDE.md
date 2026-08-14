# CLAUDE.md

## What this is

A dashboard for tracking how well NCATS Translator KGX ingests normalize against
[Babel](https://github.com/NCATSTranslator/Babel)/[NodeNorm](https://github.com/biothings/NodeNormalizationAPI).
The DINGO team transforms biomedical sources into KGX `_nodes.jsonl`/`_edges.jsonl`, normalizes node
CURIEs through NodeNorm, and publishes the results to KGX Storage. This repo consumes the
normalization side of those outputs.

Three goals, in order:

1. Summary of all prefixes normalized across every data source in KGX Storage.
2. Report of CURIEs that could not be normalized — this drives Babel ingest prioritization.
3. Renormalize a build's normalization output against a new Babel release to estimate how much the
   new release would change the results.

Planned shape: a Python CLI produces small static JSON summaries, committed to the repo and rendered
by a plain HTML/JS page on GitHub Pages. Possibly ported to [Dash](https://plotly.com/dash/) later so
it can be combined with other Translator dashboards.

## KGX Storage

`https://kgx-storage.ci.transltr.io/` fronts `s3://kgx-translator-ingests`. See `/docs` on that site.

- **HTTPS is the only public access path.** The bucket is *not* anonymously listable — both
  `aws s3 ls --no-sign-request` and the S3 REST API return `AccessDenied`. The site's HTML directory
  listings are the sole public index. `rclone`'s `:http:` backend parses them correctly, which is why
  the sync script is one `rclone sync` call.
- **File URLs 302-redirect to presigned S3 URLs**, so any client must follow redirects — use
  `curl -fL`. Directory URLs need a trailing slash. Appending `?view` to a JSON URL opens an HTML
  viewer instead of returning the raw file.
- **Large JSON files 502.** The origin appears to buffer JSON responses in memory: a 48 MB
  `normalization_map.json` downloads fine, but ubergraph's 247 MB one
  (`data/ubergraph/2026-05-31/transform_e7f773ea/normalization_.../normalization_map.json`) returns
  502 Bad Gateway to every client. This is an upstream bug worth reporting to DINGO; until it's
  fixed, a full sync exits non-zero because of that one file.

### Path layout

```
data/{source}/{source_version}/transform_{hash}/normalization_{babel}_{nn}_{code}_{conflated}_{strict}/
    normalization-metadata.json
    normalization_failures.txt
    normalization_map.json
    normalized_nodes.jsonl        # huge, never download
    normalized_edges.jsonl        # huge, never download
    merge_{version}/
data/{source}/latest-build.json           # index: which transform/normalization is current
releases/latest-release-summary.json      # index: every source's current release
releases/{source}/{release_version}/
```

The normalization directory name encodes Babel version, NodeNorm version, normalization code
version, and the conflation/strict flags. Every directory in the bucket currently uses
`normalization_2025sep1_2.4.1_1.4.0_conflated_strict` — one Babel version so far, but the layout
allows several to coexist and the sync handles that without changes.

### File semantics

- `normalization-metadata.json` — pre/post node counts, failure count, edge counts, and
  `normalization_by_prefix`: per source prefix `{succeeded, failed, total, success_rate,
  normalized_to: {target_prefix: count}}`. This is the input for goal 1. Tiny (~2–7 KB each).
- `normalization_failures.txt` — one unnormalized source CURIE per line. Input for goal 2. Not
  present in every build (e.g. ctkp, dakp have none).
- `normalization_map.json` — `{"normalization_map": {"<source CURIE>": ["<normalized CURIE>"] | null}}`.
  Failures are the `null` entries, so `normalization_failures.txt` is a subset of this file's keys.
  Kept anyway because it's 16× smaller and directly answers goal 2. The map is what goal 3 needs.

### Scale (full crawl of `data/`, Aug 2026)

90 normalization directories; a full listing crawl takes ~40s.

| file | count | total |
|---|---|---|
| `normalization-metadata.json` | 90 | 0.2 MB |
| `normalization_failures.txt` | 87 | 56 MB |
| `normalization_map.json` | 90 | 914 MB |

## Local mirror

`./scripts/sync-kgx-normalization.sh` mirrors those three file types into
`data/kgx-storage.ci.transltr.io/`, named for the host it came from. `/data/` is gitignored as
scratch space. The nodes/edges files are excluded by the `--include` filters, which apply to the
listing walk, so they are never fetched.

## Conventions

- Add a dependency only when something actually needs it. The project has none so far.
- The downloader stays `rclone` — it already does listing, filtering, incremental sync, pruning,
  retries, and concurrency.
- Data files are never committed; only the small derived JSON summaries will be.
