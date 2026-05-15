#!/usr/bin/env bash
# refresh-model-library.sh — Refresh PPQ model library (JSON cache + markdown reference)
# Usage: refresh-model-library.sh [--force] [--print]
#
# Called automatically by film-maker pre-flight. No-ops if <24h old.
#
# Output:
#   ~/.cache/opencode/ppq-video-models.json   (JSON cache from API)
#   ~/.config/opencode/skills/filmmaker/references/ppq-model-library.md  (curated reference)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CACHE_FILE="$HOME/.cache/opencode/ppq-video-models.json"
MD_FILE="$SCRIPT_DIR/../references/ppq-model-library.md"
FORCE=false
PRINT_ONLY=false

for arg in "$@"; do
  case "$arg" in
    --force|-f) FORCE=true ;;
    --print|-p) PRINT_ONLY=true ;;
  esac
done

if [ "$PRINT_ONLY" = true ]; then
  if [ -f "$MD_FILE" ]; then
    cat "$MD_FILE"
  else
    echo "❌ No library. Run: refresh-model-library.sh" >&2
    exit 1
  fi
  exit 0
fi

# Check freshness (24h = 86400s)
cache_fresh=false
md_fresh=false

if [ -f "$CACHE_FILE" ]; then
  cache_age=$(($(date +%s) - $(stat -f %m "$CACHE_FILE" 2>/dev/null || stat -c %Y "$CACHE_FILE" 2>/dev/null || echo 0)))
  [ "$cache_age" -lt 86400 ] && cache_fresh=true
fi

if [ -f "$MD_FILE" ]; then
  md_age=$(($(date +%s) - $(stat -f %m "$MD_FILE" 2>/dev/null || stat -c %Y "$MD_FILE" 2>/dev/null || echo 0)))
  [ "$md_age" -lt 86400 ] && md_fresh=true
fi

# Skip if both fresh and not forced
if [ "$FORCE" != true ] && [ "$cache_fresh" = true ] && [ "$md_fresh" = true ]; then
  echo "📦 Model library fresh ($(( $(date +%s) - $(stat -f %m "$MD_FILE" 2>/dev/null || stat -c %Y "$MD_FILE" 2>/dev/null || echo 0) ))s ago). Use --force to refresh."
  exit 0
fi

# Step 1: Refresh JSON cache (calls existing validate-ppq-models.sh)
echo "🔄 Refreshing PPQ model cache..."
bash "$SCRIPT_DIR/validate-ppq-models.sh" ${FORCE:+--force}

if [ ! -f "$CACHE_FILE" ]; then
  echo "❌ Cache not found after refresh: $CACHE_FILE" >&2
  exit 1
fi

# Step 2: Generate curated markdown from cache
echo "📝 Generating model library..."
mkdir -p "$(dirname "$MD_FILE")"
python3 "$SCRIPT_DIR/_curate_models.py" --cache "$CACHE_FILE" --output "$MD_FILE"

echo "✅ Model library: $MD_FILE"
