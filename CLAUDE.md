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

Current shape: a local [Dash](https://plotly.com/dash/) app over a local mirror of KGX Storage.
Local is deliberate — individual unnormalized CURIEs stay off the public web while we work out what
the dashboard should show, and Dash is the form that can later fold into other Translator
dashboards. Nothing is hosted yet; see the Hosting section of [docs/Loading.md](docs/Loading.md).

Goal 1 is built. Goals 2 and 3 are partly served by the click-through CURIE listing, and the
normalization maps are mirrored ready for goal 3.

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
  Note its `success_rate` is **truncated, not rounded** (99.556 → 99.55; 128 of 587 rows differ),
  so `loader.py` recomputes the rate from the counts instead of reading that field.
- `normalization_failures.txt` — one unnormalized source CURIE per line. Input for goal 2. Not
  present in every build (e.g. ctkp, dakp have none).
- `normalization_map.json` — `{"normalization_map": {"<source CURIE>": ["<normalized CURIE>"] | null}}`.
  Failures are the `null` entries, so `normalization_failures.txt` is a subset of this file's keys.
  Kept anyway because it's 16× smaller and directly answers goal 2. The map is what goal 3 needs.

### Node files — labels and Biolink types, not mirrored (yet)

Two files we deliberately do **not** download, recorded here as sources of label/type information
for when a report needs it. Both are large; check the size before pulling any of them.

**`normalization_{...}/normalized_nodes.jsonl`** — post-normalization. One JSON object per line with
the preferred CURIE, the full Biolink category ancestor list, the label, the clique members, and an
information content score:

```json
{"id": "CHEBI:165710", "category": ["biolink:SmallMolecule", "...", "biolink:NamedThing"],
 "name": "Palmitoleyl linoleate",
 "equivalent_identifiers": ["CHEBI:165710", "PUBCHEM.COMPOUND:56935947", "INCHIKEY:NBQ..."],
 "information_content": 100.0, "description": "..."}
```

This is what would let a summary report say *what* a normalized node is, not just that it
normalized. Ubergraph's alone is 384 MB; **5.7 GB across all 90 builds**, so mirroring these means
restricting to the latest build per source (~31 files) rather than adding them to the sync filters.

**`transform_{hash}/{source}_nodes.jsonl`** — the transform output, generated *before*
normalization. This is the one that says what the upstream source knew about a CURIE we could
**not** normalize, which is exactly the missing half of the unnormalized-CURIE report. How much it
knows varies sharply by source, so check before relying on it:

| source | first line |
|---|---|
| pathbank (305 MB) | `{"id":"SMPDB:SMP0000055","category":["biolink:Pathway"],"name":"Alanine Metabolism","description":"Alanine (L-Alanine) is an α-amino acid…"}` |
| ncbi_gene (74 MB) | `{"id":"NCBIGene:1","category":["biolink:Gene"],"name":"A1BG","description":"alpha-1-B glycoprotein","full_name":…,"taxon":"NCBITaxon:9606","symbol":"A1BG"}` |
| goa (15 MB) | `{"name":"NUDT4B","id":"UniProtKB:A0A024RBG1","category":["biolink:Protein"],"description":"Diphosphoinositol polyphosphate phosphohydrolase NUDT4B","in_taxon":["NCBITaxon:9606"]}` |
| ubergraph (49 MB) | `{"id":"CHEBI:165710","category":["biolink:NamedThing"]}` — **no label, no real type** |

So for pathbank — currently the worst source, 215,953 unnormalized PathBank/SMPDB CURIEs — the
transform output has names and descriptions and would make a genuinely actionable Babel ingest
report. For ubergraph it would add nothing; those labels live in the ontologies themselves.

### Scale (full crawl of `data/`, Aug 2026)

90 normalization directories; a full listing crawl takes ~40s.

| file | count | total |
|---|---|---|
| `normalization-metadata.json` | 90 | 0.2 MB |
| `normalization_failures.txt` | 87 | 56 MB |
| `normalization_map.json` | 90 | 914 MB |

### CURIE prefix case

NodeNorm resolves CURIE prefixes case-insensitively — `ENSEMBL:ENSG00000139618`, `Ensembl:…` and
`ensembl:…` all return `NCBIGene:675`. So anything that summarizes must pool prefixes
case-insensitively (`loader.py` carries `prefix_key = prefix.upper()`), while individual records
keep the case as observed in the files. In the current mirror this merges 86 observed source
prefixes into 84: `Ensembl`/`ENSEMBL` and `SIGNOR`/`signor`. Both collisions happen to be across
different sources, so per-source rows never show two spellings today — the folding matters for
cross-source rollups.

## The app

See [docs/Loading.md](docs/Loading.md) for the runbook. Layout:

- `src/normalization_dashboard/loader.py` — no Dash imports, returns plain `list[dict]` so a
  notebook, the Dash app and a future static-JSON exporter can all reuse it. `load_rows()` gives one
  row per (build, prefix); `summarize()` pools by (source, case-insensitive prefix);
  `load_failure_examples()` collects a few real failing CURIEs per (source, prefix);
  `spread()` samples evenly across a list rather than taking its head.
- `src/normalization_dashboard/app.py` — the Dash app. `uv run normalization-dashboard`, or
  `PORT=8051` for a second instance.
- `src/normalization_dashboard/curie.py` — CURIE → URL, malformed detection, and the `problem()` /
  `stem()` grouping used by the click-through listing.
- `tests/test_loader.py`, `tests/test_curie.py` — invariant checks against the real mirror, no
  framework. `uv run python tests/test_loader.py`. The loader one skips cleanly if the mirror is
  not synced.

### Gotchas worth not rediscovering

- **DataTable cells may only hold a string, number or boolean.** A list or dict on a row makes the
  browser reject the *whole* table with `Invalid argument data[0].x passed into DataTable`. This is
  a client-side propType check, so no server-side test and no `curl` of the callback endpoint will
  ever see it — `test_loader.py` asserts every `summarize()` value is a scalar for exactly this
  reason. More generally: verifying Dash callbacks over HTTP proves the data, never the rendering.
- **`active_cell["row"]` indexes the sorted, filtered viewport**, not the `data` prop. Read
  `derived_viewport_data`, or a click after re-sorting silently picks the wrong row.
- **Row identity beats row index** for `style_data_conditional`: the selected-row highlight matches
  on `{prefix}` and `{source}` via `filter_query` so it follows the row through a re-sort.
- **The mirror path is resolved relative to the repo**, not the working directory, or an IDE run
  configuration loads zero rows in silence.
- **Table width was never a Dash limit.** A page container with `maxWidth` will silently crop the
  table; `DataTable` fills whatever its parent gives it.

### The click-through CURIE listing

Unnormalized CURIEs are grouped by `curie.problem()`, most actionable first: `malformed: <reason>`,
then `prefix unknown to the Biolink model`, then `no Babel clique for this identifier`. The prefix
check is a *signal*, not a proven cause — Babel decides coverage for itself and does not consult the
Biolink prefix map — so the label says what was actually checked.

Within each problem, CURIEs are grouped by `curie.stem()`, everything up to the first digit. That is
what turns pathbank's 215,953 failures into 175,039 `PathBank:Reaction_…`, 31,182
`PathBank:Compound_…` and 8,886 `PathBank:ProteinComplex_…`, and splits bgee's ENSEMBL failures by
species. Grouping declines above 12 groups and falls back to a flat list: InChIKeys contain no
digits, so 87 of them would otherwise make 87 groups of one.

Headline figures in the summary list describe the whole build selection, not the visible rows — an
overall score that moved when you hid the fully-normalizing prefixes would be worse than useless.
CURIEs are counted once per source, so the all-builds total of 3,225,939 failures counts occurrences
(898,042 distinct).

### Linking CURIEs

`biolink-model-prefix-map.json` is **vendored** into the package (266 prefixes, 14 KB) so the app
works offline. Refresh it with:

```bash
curl -sL https://raw.githubusercontent.com/biolink/biolink-model/master/src/biolink_model/prefixmaps/biolink-model-prefix-map.json \
     -o src/normalization_dashboard/biolink-model-prefix-map.json
```

The map covers 75.5% of the 898,042 distinct unnormalized CURIEs. The other 24 prefixes fall back to
`https://bioregistry.io/{curie}`, which resolves them — including PathBank, which is not in the
Biolink prefix map at all and is by itself 215,953 of those CURIEs. The `curies` package is not used:
the Biolink file is a flat prefix → URI-stem dict, so expansion is one dict lookup and a string
concat, and a case-insensitive index is a one-line comprehension.

Malformed CURIEs get no link and a reason instead, because the malformation is often the whole
explanation for the normalization failure. Real species found in the data: `rhea:RHEA:13065` (double
prefix), `CL:0000089 ∩ UBERON:0000473` (post-composed class expression), `UniProtKB:B3DHD6 Q6XCC7`
(two accessions in one CURIE), `UniProtKB:` (empty local id). Only 24 of 898,042 are malformed at
this syntactic level — rare, but they cluster: intact's 2 RHEA failures are both double-prefixed.

Current shape of the data through the loader: 587 raw rows, 31 sources, 84 case-insensitive
prefixes, 242 summary rows (241 for latest builds only — historical builds add almost nothing at the
(source, prefix) level).

## Local mirror

`./scripts/sync-kgx-normalization.sh` mirrors those three file types plus `latest-build.json` into
`data/kgx-storage.ci.transltr.io/` — a directory named after the host they came from, so it stays
obvious where a local copy originated. The nodes/edges files are excluded by the `--include`
filters, which apply to the listing walk, so they are never fetched. Full runbook, variants and
troubleshooting: [docs/Loading.md](docs/Loading.md).

`/data/` is gitignored, so use it as the scratch space for one-off jobs — intermediate results,
downloaded samples, ad-hoc query output — rather than `/tmp`. It survives reboots and stays next to
the code, so a one-off job can be picked up or re-run later instead of being redone from scratch.

## Conventions

- Add a dependency only when something actually needs it. `dash` is the only one; `curies` was
  considered and skipped because the Biolink prefix map is a flat dict.
- The downloader stays `rclone` — it already does listing, filtering, incremental sync, pruning,
  retries, and concurrency.
- Data files are never committed; only the small derived JSON summaries will be.
- Derived values are recomputed rather than trusted: `success_rate` comes from the counts, not from
  the field in the file.
- PR titles become release notes, so they describe the change and its effect — never "WIP" or
  "Initial implementation of X".
