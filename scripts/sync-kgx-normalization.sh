#!/usr/bin/env bash
# Mirror only the normalization artifacts from KGX Storage, preserving its folder layout.
# Downloads new/changed files and deletes local files that no longer exist upstream.
#
# Usage: ./scripts/sync-kgx-normalization.sh [DEST] [extra rclone args...]
#   e.g. ./scripts/sync-kgx-normalization.sh /tmp/kgxtest --dry-run
#        ./scripts/sync-kgx-normalization.sh data/kgx-storage.ci.transltr.io --exclude "**/normalization_map.json"
#
# Requires rclone (brew install rclone). The S3 bucket behind KGX Storage is not
# anonymously listable, so we walk the site's HTML listings via rclone's http backend.
set -euo pipefail

DEST="${1:-data/kgx-storage.ci.transltr.io}"

rclone sync --http-url https://kgx-storage.ci.transltr.io :http:data/ "$DEST" \
  --include "**/normalization-metadata.json" \
  --include "**/normalization_failures.txt" \
  --include "**/normalization_map.json" \
  --checkers 16 --transfers 8 --progress --stats-one-line "${@:2}"
