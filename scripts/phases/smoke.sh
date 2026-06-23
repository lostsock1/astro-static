#!/usr/bin/env bash
# Post-build smoke test. Supports both static Astro output (dist/client/index.html)
# and SSR Astro output (dist/server/entry.mjs) when SITE_URL is provided.
#
# Output:  STATUS:SMOKE_OK               (exit 0)
#      or  STATUS:SMOKE_FAIL check=<N>   (exit 1, where N describes what failed)
#
# Expected cwd: either the site root or the static output directory. For SSR,
# run with SITE_URL=<live-url> SITE_DIR=<site-root> so this script can validate
# the live page body while still checking local dist/client assets.

set -euo pipefail

fail() {
  echo "STATUS:SMOKE_FAIL check=$1"
  exit 1
}

abs_dir() { (cd "$1" 2>/dev/null && pwd) || return 1; }

SITE_ROOT="${SITE_DIR:-}"
if [ -n "$SITE_ROOT" ] && [ -d "$SITE_ROOT" ]; then
  SITE_ROOT="$(abs_dir "$SITE_ROOT")"
else
  SITE_ROOT=""
fi

if [ -z "$SITE_ROOT" ]; then
  for candidate in "$(pwd)" "$(pwd)/.." "$(pwd)/../.."; do
    if [ -f "$candidate/package.json" ] || [ -d "$candidate/tina" ] || [ -d "$candidate/dist" ]; then
      SITE_ROOT="$(abs_dir "$candidate")"
      break
    fi
  done
fi

DIST_DIR=""
for candidate in \
  "$(pwd)" \
  "$(pwd)/dist/client" \
  "$(pwd)/dist" \
  "${SITE_ROOT:-}/dist/client" \
  "${SITE_ROOT:-}/dist" \
  "$HOME/dist/client"; do
  [ -n "$candidate" ] || continue
  if [ -d "$candidate" ] && { [ -f "$candidate/index.html" ] || [ -d "$candidate/assets" ] || [ -d "$candidate/_astro" ]; }; then
    DIST_DIR="$(abs_dir "$candidate")"
    break
  fi
done
if [ -z "$DIST_DIR" ]; then
  for candidate in /var/www/sites/*/dist/client; do
    if [ -d "$candidate" ] && { [ -f "$candidate/index.html" ] || [ -d "$candidate/assets" ] || [ -d "$candidate/_astro" ]; }; then
      DIST_DIR="$(abs_dir "$candidate")"
      break
    fi
  done
fi

if [ -n "$DIST_DIR" ]; then
  cd "$DIST_DIR"
fi

SSR_MODE=NO
if [ -n "$SITE_ROOT" ] && [ -f "$SITE_ROOT/dist/server/entry.mjs" ]; then
  SSR_MODE=YES
fi

LIVE_TMP=""
cleanup() { [ -n "$LIVE_TMP" ] && rm -f "$LIVE_TMP" 2>/dev/null || true; }
trap cleanup EXIT

INDEX_FILE=""
if [ -n "${SITE_URL:-}" ]; then
  command -v curl >/dev/null 2>&1 || fail "no_curl_for_live_http"
  LIVE_TMP="$(mktemp "${TMPDIR:-/tmp}/astro-static-smoke.XXXXXX")"
  HTTP_CODE="000"
  LIVE_OK=NO
  for attempt in 1 2 3 4 5; do
    if HTTP_CODE=$(curl -k -L -sS --connect-timeout 10 --max-time 30 -o "$LIVE_TMP" -w "%{http_code}" "$SITE_URL" 2>/dev/null); then
      LIVE_OK=YES
      break
    fi
    sleep 1
  done
  [ "$LIVE_OK" = "YES" ] || fail "live_http_unhealthy"
  case "$HTTP_CODE" in
    2*|3*) INDEX_FILE="$LIVE_TMP" ;;
    *) fail "live_http_status_${HTTP_CODE}" ;;
  esac
fi

if [ -z "$INDEX_FILE" ]; then
  if [ -f index.html ]; then
    INDEX_FILE="index.html"
  elif [ "$SSR_MODE" = "YES" ]; then
    fail "no_live_site_url_for_ssr"
  else
    fail "no_index_html"
  fi
fi

# 1. The rendered page links at least one stylesheet (BaseLayout must import theme).
grep -qE '<link[^>]*(rel="stylesheet"[^>]*href=|href="[^"]+"[^>]*rel="stylesheet")' "$INDEX_FILE" \
  || fail "no_stylesheet_link"

# 2. Every linked local CSS file resolves on disk and is non-empty.
while IFS= read -r href; do
  [ -n "$href" ] || continue
  case "$href" in http://*|https://*|data:*) continue ;; esac
  path="${href%%\#*}"
  path="${path%%\?*}"
  path="${path#/}"
  [ -s "$path" ] || fail "stylesheet_missing_or_empty"
done < <(grep -oE '<link[^>]*(rel="stylesheet"[^>]*href="[^"]+"|href="[^"]+"[^>]*rel="stylesheet")[^>]*>' "$INDEX_FILE" \
         | grep -oE 'href="[^"]+"' | cut -d'"' -f2)

# 3. Theme tokens actually emitted — at least one --color-* or --font-* custom property.
if ! find . -name '*.css' -print0 | xargs -0 grep -qE -- '--(color|font)-'; then
  if find . -name '*.css' -print0 | xargs -0 grep -qE '@import[[:space:]]+"tailwindcss"'; then
    fail "tailwind_import_unprocessed"
  fi
  fail "theme_tokens_absent"
fi

# 4. Internal nav links resolve to generated pages. In SSR mode with live URL,
# disk lookup is not authoritative, so only static output is checked this way.
if [ "$SSR_MODE" != "YES" ]; then
  while IFS= read -r href; do
    [ -n "$href" ] || continue
    path="${href#/}"
    [ -z "$path" ] && path="index.html"
    [ -f "$path" ] || [ -f "$path/index.html" ] || [ -f "${path%/}.html" ] \
      || fail "nav_link_broken"
  done < <(grep -oE '<a[^>]+href="/[^"#?]*"' "$INDEX_FILE" | grep -oE 'href="[^"]+"' | cut -d'"' -f2 | sort -u)
fi

# 5. No unrendered template leakage.
! grep -qE '\{\{[^}]+\}\}' "$INDEX_FILE" || fail "unrendered_template"

# 6. <title> is not a placeholder or empty.
TITLE=$(grep -oE '<title>[^<]*</title>' "$INDEX_FILE" | sed 's/<[^>]*>//g' | head -1)
case "$TITLE" in
  ''|'Astro'|'Astro Basics'|'Document') fail "placeholder_title" ;;
esac

HAS_HTML=NO
while IFS= read -r _html_file; do HAS_HTML=YES; break; done < <(find . -name '*.html' -print)
if [ "$HAS_HTML" = "YES" ]; then
  # 7. Video posters must be still images and exist for local public assets.
  while IFS= read -r poster; do
    [ -n "$poster" ] || continue
    case "$poster" in
      http://*|https://*|data:*) continue ;;
      *.mp4|*.mov|*.m4v|*.webm) fail "video_poster_is_video" ;;
    esac
    poster_path="${poster%%\?*}"
    poster_path="${poster_path#/}"
    [ -f "$poster_path" ] || fail "video_poster_missing"
  done < <(find . -name '*.html' -print0 \
           | xargs -0 grep -hoE '<video[^>]*poster="[^"]+"' 2>/dev/null \
           | grep -oE 'poster="[^"]+"' | cut -d'"' -f2 || true)

  # 8. Every referenced public video resolves and is large enough to be real.
  while IFS= read -r src; do
    [ -n "$src" ] || continue
    case "$src" in http://*|https://*) continue ;; esac
    path="${src#/}"
    [ -s "$path" ] || fail "video_missing_or_empty"
    bytes=$(wc -c < "$path" | tr -d '[:space:]')
    [ "$bytes" -gt 102400 ] || fail "video_too_small"
  done < <(find . -name '*.html' -print0 \
           | xargs -0 grep -hoE '(src|href)="/[^"]+\.(mp4|mov|m4v|webm)"' 2>/dev/null \
           | cut -d'"' -f2 | sort -u || true)

  # 9. Video background component must not render a separate static poster layer.
  if find . -name '*.html' -print0 | xargs -0 grep -qE '<img[^>]+class="[^"]*video-bg__poster|<img[^>]+class=[^ >]*video-bg__poster' 2>/dev/null; then
    fail "video_static_poster_layer"
  fi
fi

# 10. Reduced-motion must not hide generated clips completely by default.
if find . -name '*.css' -print0 | xargs -0 grep -qE 'video-bg__video[^}]*display:[[:space:]]*none|video-bg__video[^}]*opacity:[[:space:]]*0([;}])' 2>/dev/null; then
  fail "video_hidden_under_reduced_motion"
fi

# 11. TinaCMS admin SPA must exist at /admin/ for Tina projects.
if [ -z "$SITE_ROOT" ]; then
  if [ -f "$(pwd)/tina/config.ts" ]; then
    SITE_ROOT="$(pwd)"
  elif [ -f "$(pwd)/../tina/config.ts" ]; then
    SITE_ROOT="$(cd "$(pwd)/.." && pwd)"
  elif [ -f "$(pwd)/../../tina/config.ts" ]; then
    SITE_ROOT="$(cd "$(pwd)/../.." && pwd)"
  fi
fi

if [ -n "$SITE_ROOT" ] && [ -f "$SITE_ROOT/tina/config.ts" ]; then
  if [ -f "$SITE_ROOT/admin/index.html" ]; then
    ADMIN_SIZE=$(du -sk "$SITE_ROOT/admin" | cut -f1)
    [ "$ADMIN_SIZE" -gt 50 ] || fail "admin_spa_too_small"
  else
    fail "admin_spa_missing"
  fi
  [ -f "$SITE_ROOT/admin/login.html" ] || fail "admin_login_missing"
  [ -f "$SITE_ROOT/admin/bridge.js" ] || fail "admin_bridge_missing"
  [ -f "$SITE_ROOT/tina/__generated__/_schema.json" ] || fail "tina_schema_missing"
fi

echo "STATUS:SMOKE_OK"
