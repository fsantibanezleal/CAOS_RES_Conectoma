#!/usr/bin/env bash
# Fetch the MaleCNS v1.0 connectome tables into the local cache. Resumable, size-verified, never committed.
#
#   ./scripts/fetch-data.sh [--with-synapse-points]
#
# The cache root comes from CONECTOMA_DATA_ROOT; see docs/guides/02_fetch-the-connectome.md.
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

BASE="https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome"
FILES=(
  "body-annotations-male-cns-v1.0-minconf-0.5.feather"
  "body-neurotransmitters-male-cns-v1.0.feather"
  "connectome-weights-male-cns-v1.0-minconf-0.5.feather"
)

if [ "${1:-}" = "--with-synapse-points" ]; then
  FILES+=("syn-points-male-cns-v1.0-minconf-0.5.feather")
fi

if [ -z "${CONECTOMA_DATA_ROOT:-}" ]; then
  echo "CONECTOMA_DATA_ROOT is not set. Point it at a directory with room for the tables." >&2
  exit 1
fi

DEST="$CONECTOMA_DATA_ROOT/malecns"
mkdir -p "$DEST"

for name in "${FILES[@]}"; do
  url="$BASE/$name"
  target="$DEST/$name"
  expected="$(curl -sI "$url" | awk 'tolower($1) == "content-length:" { print $2 }' | tr -d '\r')"
  if [ -f "$target" ] && [ "$(stat -c %s "$target")" = "$expected" ]; then
    echo "[fetch] $name already complete ($expected bytes)"
    continue
  fi
  echo "[fetch] $name ($expected bytes)"
  curl -fSL -C - -o "$target" "$url"
  actual="$(stat -c %s "$target")"
  if [ "$actual" != "$expected" ]; then
    echo "[fetch] FAILED: $name is $actual bytes, expected $expected. Re-run to resume." >&2
    exit 1
  fi
done

echo "[fetch] cache ready at $DEST"
echo "[fetch] next: python data-pipeline/run.py build-connectome"
