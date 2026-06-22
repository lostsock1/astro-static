#!/usr/bin/env bash
# ig-download.sh — Download Instagram CDN assets with proper headers and retry
# Part of astro-static pipeline: used by instagram-extractor to download images
# from Instagram CDN URLs before they expire (signed URLs last ~24h).
#
# Usage: ig-download.sh <cdn_url> <output_path> [--referer URL]
#
# Handles: Referer header requirement (Instagram blocks requests without it),
# User-Agent rotation (mobile-first for better CDN cache hits), retry with
# exponential backoff, output validation (must be a real image, not an error page).

set -euo pipefail

CDN_URL="${1:?Usage: ig-download.sh <cdn_url> <output_path> [--referer URL]}"
OUTPUT="${2:?Usage: ig-download.sh <cdn_url> <output_path> [--referer URL]}"
REFERER="https://www.instagram.com/"

# Parse optional --referer flag
if [ $# -ge 4 ] && [ "$3" = "--referer" ]; then
    REFERER="$4"
fi

# Ensure output directory exists
mkdir -p "$(dirname "$OUTPUT")"

# Mobile-first User-Agent rotation — Instagram CDN serves better quality to
# mobile UAs and caches them more aggressively.
USER_AGENTS=(
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/126.0.6478.153 Mobile/15E148 Safari/604.1"
)

# Rotate UA per invocation for diversity
UA="${USER_AGENTS[$((RANDOM % ${#USER_AGENTS[@]}))]}"

# Download with retry (max 3 attempts, 2s/4s/8s backoff)
MAX_RETRIES=3
for attempt in $(seq 1 $MAX_RETRIES); do
    if curl -sS -L \
        -H "Referer: $REFERER" \
        -H "User-Agent: $UA" \
        -H "Accept: image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8" \
        -H "Accept-Language: en-US,en;q=0.9" \
        -H "Sec-Fetch-Dest: image" \
        -H "Sec-Fetch-Mode: no-cors" \
        -H "Sec-Fetch-Site: cross-site" \
        -o "$OUTPUT" \
        --max-time 30 \
        --connect-timeout 10 \
        "$CDN_URL" 2>/dev/null; then

        # Verify we got an actual image, not an error/redirect page
        if [ -s "$OUTPUT" ] && file "$OUTPUT" | grep -qE 'JPEG|PNG|WebP|GIF|SVG'; then
            # Check minimum size (1KB — anything smaller is likely an error page)
            SIZE=$(stat -f%z "$OUTPUT" 2>/dev/null || stat -c%s "$OUTPUT" 2>/dev/null || echo 0)
            if [ "$SIZE" -ge 1024 ]; then
                exit 0
            fi
        fi
        # File exists but isn't a valid image — retry
        rm -f "$OUTPUT"
    fi

    if [ "$attempt" -lt "$MAX_RETRIES" ]; then
        BACKOFF=$((2 ** attempt))  # 2, 4, 8 seconds
        sleep "$BACKOFF"
    fi
done

# All retries exhausted
echo "STATUS:IG_DOWNLOAD_FAILED url=$CDN_URL output=$OUTPUT" >&2
exit 1
