#!/usr/bin/env bash
# Deterministic fallback asset updater for astro-static.
#
# Usage from local project root (contains pipeline/02-asset-manifest.json):
#   bash ~/.config/opencode/astro-static/phases/asset-fallbacks.sh images
#   bash ~/.config/opencode/astro-static/phases/asset-fallbacks.sh videos
#
# This script is intentionally website-agnostic. It never invents brand facts;
# it only prevents missing/0-byte assets from breaking future deployments.

set -euo pipefail

MODE="${1:-}"
MANIFEST="pipeline/02-asset-manifest.json"
IMAGE_SHOTS="pipeline/02-image-shot-list.json"
VIDEO_SHOTS="pipeline/02-video-shot-list.json"

[ -f "$MANIFEST" ] || { echo "STATUS:ASSET_FALLBACK_FAILED reason=missing_manifest"; exit 1; }

write_svg_placeholder() {
  local path="$1" label="$2" width="$3" height="$4"
  mkdir -p "$(dirname "$path")"
  python3 - "$path" "$label" "$width" "$height" <<'PY'
from pathlib import Path
import html
import sys

path = Path(sys.argv[1])
label = html.escape(sys.argv[2])
width = int(sys.argv[3])
height = int(sys.argv[4])
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{label}">
  <defs>
    <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0" stop-color="#b55a3a"/>
      <stop offset="1" stop-color="#4a3625"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#g)"/>
  <circle cx="{width * 0.82:.0f}" cy="{height * 0.20:.0f}" r="{min(width, height) * 0.12:.0f}" fill="#d4922a" opacity="0.45"/>
  <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#f0dfb8" font-family="system-ui, sans-serif" font-size="{max(18, min(width, height)//18)}" font-weight="700">{label}</text>
</svg>
'''
path.write_text(svg, encoding="utf-8")
PY
}

dimensions_to_wh() {
  local dims="$1" default_w="$2" default_h="$3"
  if [[ "$dims" =~ ^([0-9]+)x([0-9]+)$ ]]; then
    printf '%s %s\n' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
  else
    printf '%s %s\n' "$default_w" "$default_h"
  fi
}

case "$MODE" in
  images)
    [ -f "$IMAGE_SHOTS" ] || { echo "STATUS:ASSET_FALLBACK_FAILED reason=missing_image_shot_list"; exit 1; }

    count=$(jq '.images | length' "$IMAGE_SHOTS")
    for ((i=0; i<count; i++)); do
      path=$(jq -r ".images[$i].output_path" "$IMAGE_SHOTS")
      id=$(jq -r ".images[$i].id // \"image-$i\"" "$IMAGE_SHOTS")
      dims=$(jq -r ".images[$i].dimensions // empty" "$IMAGE_SHOTS")
      read -r w h < <(dimensions_to_wh "$dims" 1200 800)
      if [ ! -s "$path" ] || [ "$(wc -c < "$path")" -lt 1024 ]; then
        write_svg_placeholder "$path" "$id placeholder" "$w" "$h"
        jq ".images[$i].status = \"placeholder\" | .images[$i].fallback_reason = \"generation_missing_or_too_small\"" \
          "$IMAGE_SHOTS" > "$IMAGE_SHOTS.tmp" && mv "$IMAGE_SHOTS.tmp" "$IMAGE_SHOTS"
      elif [ "$(jq -r ".images[$i].status // empty" "$IMAGE_SHOTS")" = "" ]; then
        jq ".images[$i].status = \"generated\"" "$IMAGE_SHOTS" > "$IMAGE_SHOTS.tmp" && mv "$IMAGE_SHOTS.tmp" "$IMAGE_SHOTS"
      fi
    done

    jq --argjson images "$(jq '.images' "$IMAGE_SHOTS")" '.content_images = $images' \
      "$MANIFEST" > "$MANIFEST.tmp" && mv "$MANIFEST.tmp" "$MANIFEST"
    echo "STATUS:ASSET_FALLBACK_IMAGES_OK"
    ;;

  videos)
    if [ ! -f "$VIDEO_SHOTS" ]; then
      jq '.video_backgrounds = (.video_backgrounds // [])' "$MANIFEST" > "$MANIFEST.tmp" && mv "$MANIFEST.tmp" "$MANIFEST"
      echo "STATUS:ASSET_FALLBACK_VIDEOS_SKIPPED reason=no_video_shot_list"
      exit 0
    fi

    count=$(jq '.videos | length' "$VIDEO_SHOTS")
    for ((i=0; i<count; i++)); do
      path=$(jq -r ".videos[$i].output_path" "$VIDEO_SHOTS")
      if [ -s "$path" ] && [ "$(du -k "$path" | cut -f1)" -gt 100 ]; then
        jq ".videos[$i].status = \"generated\"" "$VIDEO_SHOTS" > "$VIDEO_SHOTS.tmp" && mv "$VIDEO_SHOTS.tmp" "$VIDEO_SHOTS"
      else
        jq ".videos[$i].status = \"failed\" | .videos[$i].fallback = \"poster_or_gradient\" | .videos[$i].fallback_reason = \"video_missing_or_too_small\"" \
          "$VIDEO_SHOTS" > "$VIDEO_SHOTS.tmp" && mv "$VIDEO_SHOTS.tmp" "$VIDEO_SHOTS"
      fi
    done

    jq --argjson videos "$(jq '.videos' "$VIDEO_SHOTS")" '.video_backgrounds = $videos' \
      "$MANIFEST" > "$MANIFEST.tmp" && mv "$MANIFEST.tmp" "$MANIFEST"
    echo "STATUS:ASSET_FALLBACK_VIDEOS_OK"
    ;;

  *)
    echo "Usage: $0 images|videos" >&2
    echo "STATUS:ASSET_FALLBACK_FAILED reason=invalid_mode mode=${MODE:-empty}"
    exit 2
    ;;
esac
