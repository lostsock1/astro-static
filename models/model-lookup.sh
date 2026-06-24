#!/usr/bin/env bash
# model-lookup.sh — Quick PPQ model lookup for film-making agents
# Usage: model-lookup.sh <command> [args...]
#
# Commands:
#   cheapest t2v [quality]    Cheapest text-to-video model (optionally filter by quality)
#   cheapest i2v              Cheapest image-to-video model
#   cheapest t2i              Cheapest text-to-image model
#   show video                Full video model summary
#   show image                Full image model summary
#   show i2v                  Full i2v model summary
#   show kling|veo|runway...  Models matching keyword
#   show chains               Recommended t2i→i2v chains
#   info <model-id>           Full details for one model
#   budget <dollars> <scenes> What chain fits your budget
#   tiers                     Budget/standard/premium breakdown
#   refresh                   Force-refresh the library

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CACHE_FILE="$HOME/.cache/opencode/ppq-video-models.json"
MD_FILE="$SCRIPT_DIR/ppq-models.md"

# Ensure cache exists
if [ ! -f "$CACHE_FILE" ]; then
  bash "$SCRIPT_DIR/refresh-models.sh" 2>/dev/null || true
fi

if [ ! -f "$CACHE_FILE" ]; then
  echo "❌ No cache. Set PPQ_API_KEY and run: refresh-models.sh" >&2
  exit 1
fi

JQ_ARGS=()

cmd="${1:-help}"
shift || true

case "$cmd" in
  cheapest)
    what="${1:-t2v}"
    quality_filter="${2:-}"
    case "$what" in
      t2v)
        if [ -n "$quality_filter" ]; then
          echo "Cheapest t2v ($quality_filter):"
          cat "$CACHE_FILE" | jq -r '
            .video_models | to_entries[] | select(.value.recommended == true)
            | .key as $id | .value.pricing[]? as $p
            | $p.sizes | to_entries[]
            | select(.key | contains("'"$quality_filter"'"))
            | {model: $id, size: .key, price: .value}
          ' | jq -s 'sort_by(.price) | .[0] | "\(.model) (\(.size)) = $\(.price)"'
        else
          key="cheapest_t2v"
          cat "$CACHE_FILE" | jq -r ".recommendations.$key as \$m | .recommendations.${key}_price as \$p | \"\(\$m) — $\(\$p)\""
        fi
        ;;
      i2v)
        cat "$CACHE_FILE" | jq -r '.recommendations | "cheapest_i2v: \(.cheapest_i2v) — $\(.cheapest_i2v_price)"'
        ;;
      t2i)
        cat "$CACHE_FILE" | jq -r '.recommendations | "cheapest_t2i: \(.cheapest_t2i) — $\(.cheapest_t2i_price)"'
        ;;
      *)
        echo "Usage: model-lookup.sh cheapest t2v|t2i|i2v [quality]" >&2
        exit 1
        ;;
    esac
    ;;

  show)
    what="${1:-video}"
    case "$what" in
      video)
        cat "$CACHE_FILE" | jq -r '
          .video_models | to_entries[] | sort_by(.key)
          | "\(.key) | \(.value.name) | recommended=\(.value.recommended) | issues=\(.value.known_issues | length)"
        ' | column -t -s'|'
        ;;
      image)
        cat "$CACHE_FILE" | jq -r '
          .image_models | to_entries[]
          | select(.value.category | test("image-to-video|i2v") | not)
          | "\(.key) | \(.value.name) | \(.value.category)"
        ' | column -t -s'|'
        ;;
      i2v)
        cat "$CACHE_FILE" | jq -r '
          .image_models | to_entries[]
          | select(.key | test("i2v|image-to-video"; "i"))
          | "\(.key) | \(.value.name)"
        ' | column -t -s'|'
        ;;
      chains)
        if [ -f "$MD_FILE" ]; then
          grep -A 20 "## Recommended t2i" "$MD_FILE" | head -25
        else
          echo "No markdown library. Run refresh first." >&2
        fi
        ;;
      *)
        # Filter by keyword
        keyword="$what"
        echo "=== Video models matching '$keyword' ==="
        cat "$CACHE_FILE" | jq -r --arg kw "$keyword" '
          .video_models | to_entries[] | select(.key | contains($kw))
          | "\(.key): \(.value.name)"
        '
        echo ""
        echo "=== Image models matching '$keyword' ==="
        cat "$CACHE_FILE" | jq -r --arg kw "$keyword" '
          .image_models | to_entries[] | select(.key | contains($kw))
          | "\(.key): \(.value.name)"
        '
        ;;
    esac
    ;;

  info)
    model_id="${1:-}"
    if [ -z "$model_id" ]; then
      echo "Usage: model-lookup.sh info <model-id>" >&2
      exit 1
    fi
    # Try video first, then image
    cat "$CACHE_FILE" | jq --arg id "$model_id" '
      (.video_models[$id] // .image_models[$id] // null) as $m
      | if $m then {
          id: $id,
          name: $m.name,
          category: $m.category,
          recommended: $m.recommended,
          accepts_image: $m.accepts_image,
          quality_options: $m.quality_options,
          pricing: $m.pricing,
          known_issues: $m.known_issues
        } else {error: "Model not found", id: $id} end
    '
    ;;

  budget)
    dollars="${1:-20}"
    scenes="${2:-10}"
    echo "Budget: \$$dollars for $scenes scenes"
    echo ""
    per_scene=$(echo "$dollars / $scenes" | bc -l)
    echo "Max per scene: \$$(printf '%.4f' "$per_scene")"
    echo ""
    echo "=== Affordable t2v models ==="
    cat "$CACHE_FILE" | jq --argjson max "$per_scene" '
      .video_models | to_entries[] | select(.value.recommended == true)
      | .key as $id | .value.pricing[]? as $p
      | $p.sizes | to_entries[]
      | select(.value <= $max)
      | "\($id) (\(.key)) = $\(.value)"
    ' | sort -t'$' -k2 -n | head -10
    ;;

  tiers)
    echo "=== BUDGET (cheapest usable) ==="
    cat "$CACHE_FILE" | jq -r '.video_models | to_entries[] | select(.value.recommended == true) | .key as $id | .value.pricing[]?.sizes | to_entries[] | select(.value < 0.20) | "\($id) (\(.key)) = $\(.value)"' | sort -t'$' -k2 -n
    echo ""
    echo "=== STANDARD (0.20 - 1.00) ==="
    cat "$CACHE_FILE" | jq -r '.video_models | to_entries[] | select(.value.recommended == true) | .key as $id | .value.pricing[]?.sizes | to_entries[] | select(.value >= 0.20 and .value < 1.00) | "\($id) (\(.key)) = $\(.value)"' | sort -t'$' -k2 -n | head -15
    echo ""
    echo "=== PREMIUM (1.00+) ==="
    cat "$CACHE_FILE" | jq -r '.video_models | to_entries[] | select(.value.recommended == true) | .key as $id | .value.pricing[]?.sizes | to_entries[] | select(.value >= 1.00) | "\($id) (\(.key)) = $\(.value)"' | sort -t'$' -k2 -n | head -15
    ;;

  refresh)
    bash "$SCRIPT_DIR/refresh-models.sh" --force
    ;;

  help|--help|-h)
    echo "PPQ Model Lookup — Quick reference for film-making agents"
    echo ""
    echo "Commands:"
    echo "  cheapest t2v [quality]    Cheapest text-to-video model"
    echo "  cheapest i2v              Cheapest image-to-video model"
    echo "  cheapest t2i              Cheapest text-to-image model"
    echo "  show video|image|i2v      Model summary tables"
    echo "  show kling|veo|runway...  Models matching keyword"
    echo "  show chains               Recommended t2i→i2v chains"
    echo "  info <model-id>           Full JSON details for one model"
    echo "  budget <\$> <scenes>       What fits your budget"
    echo "  tiers                     Budget/standard/premium breakdown"
    echo "  refresh                   Force-refresh the library"
    ;;

  *)
    echo "Unknown command: $cmd. Use 'help' for usage." >&2
    exit 1
    ;;
esac
