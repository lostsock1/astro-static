#!/usr/bin/env bash
# validate-ppq-models.sh — Query PPQ API for video/image models + cache validated results
# Usage: ./validate-ppq-models.sh [--force] [--print]
# Cache: ~/.cache/opencode/ppq-video-models.json (24h TTL)

set -euo pipefail

CACHE_FILE="$HOME/.cache/opencode/ppq-video-models.json"
CACHE_DIR="$(dirname "$CACHE_FILE")"
API_KEY="${PPQ_API_KEY:-}"
FORCE=false
PRINT_ONLY=false
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=true ;;
    --print|-p) PRINT_ONLY=true ;;
  esac
done

if [ "$PRINT_ONLY" = true ]; then
  [ -f "$CACHE_FILE" ] && cat "$CACHE_FILE" || { echo '{"error":"No cache. Run first."}' >&2; exit 1; }
  exit 0
fi

# 24h cache skip
if [ "$FORCE" != true ] && [ -f "$CACHE_FILE" ]; then
  cache_age=$(($(date +%s) - $(stat -f %m "$CACHE_FILE" 2>/dev/null || stat -c %Y "$CACHE_FILE" 2>/dev/null || echo 0)))
  if [ "$cache_age" -lt 86400 ]; then
    echo "📦 Using cached model data ($((cache_age / 3600))h old). --force to refresh."
    exit 0
  fi
fi

[ -z "$API_KEY" ] && { echo "❌ PPQ_API_KEY not set."; exit 1; }
mkdir -p "$CACHE_DIR"

echo "🔍 Querying PPQ API for video/image models..."
MODELS_JSON=$(curl -s "https://api.ppq.ai/v1/models?type=image,video" -H "Authorization: Bearer $API_KEY")

echo "$MODELS_JSON" | python3 "$SCRIPT_DIR/_parse_ppq_models.py" "$CACHE_FILE"

echo ""
echo "✅ Cache: $CACHE_FILE"
