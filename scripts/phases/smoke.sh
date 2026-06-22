#!/usr/bin/env bash
# Post-build smoke test. Runs from within the built static output directory and checks
# that index.html is actually functional — not just that a file exists.
#
# `astro build` returning zero + index.html being present does NOT prove
# the page works. These checks catch the classes of bug that previously shipped
# to production: missing CSS import, broken nav links, unrendered template
# fragments, empty theme tokens, placeholder <title>, and broken video
# background integration.
#
# Output:  STATUS:SMOKE_OK               (exit 0)
#      or  STATUS:SMOKE_FAIL check=<N>   (exit 1, where N describes what failed)
#
# Expected cwd: the static output directory (e.g. /var/www/sites/<project>/dist/client for @astrojs/node builds).
# The orchestrator invokes this over ssh like:
#   ssh $VPS "cd $SITE_DIR/dist/client && bash -s" < phases/smoke.sh

set -eu

# Auto-detect the build output directory if not already in it.
# The orchestrator should run from dist/client, but if invoked from $HOME
# or the site root, find the nearest dist/client automatically.
if [ ! -f index.html ]; then
  for candidate in \
    "$(pwd)/dist/client" \
    "$(pwd)/dist" \
    "$HOME/dist/client"; do
    if [ -f "$candidate/index.html" ]; then
      cd "$candidate"
      break
    fi
  done
  for candidate in /var/www/sites/*/dist/client; do
    if [ -f "$candidate/index.html" ]; then
      cd "$candidate"
      break
    fi
  done
fi

fail() {
  echo "STATUS:SMOKE_FAIL check=$1"
  exit 1
}

[ -f index.html ] || fail "no_index_html"

# 1. index.html links at least one stylesheet (BaseLayout must import theme).
grep -qE '<link[^>]*(rel="stylesheet"[^>]*href=|href="[^"]+"[^>]*rel="stylesheet")' index.html \
  || fail "no_stylesheet_link"

# 2. Every linked CSS file resolves on disk and is non-empty.
#    A link to a missing/empty CSS file means the build pipeline dropped it.
while IFS= read -r href; do
  [ -n "$href" ] || continue
  path="${href#/}"
  [ -s "$path" ] || fail "stylesheet_missing_or_empty"
done < <(grep -oE '<link[^>]*(rel="stylesheet"[^>]*href="[^"]+"|href="[^"]+"[^>]*rel="stylesheet")[^>]*>' index.html \
         | grep -oE 'href="[^"]+"' | cut -d'"' -f2)

# 3. Theme tokens actually emitted — at least one --color-* or --font-*
#    custom property somewhere in the compiled CSS. If this fails, the
#    @theme {} block never reached the output.
if ! find . -name '*.css' -print0 | xargs -0 grep -qE -- '--(color|font)-'; then
  # Specific diagnosis before the generic failure: a raw `@import "tailwindcss"`
  # still sitting in the emitted CSS means the entry file was shipped from
  # public/ (copied as-is by Astro) instead of src/ (imported by a component
  # and processed by @tailwindcss/vite). Tokens are missing and every utility
  # class in the HTML is undefined. The fix is to move the CSS under src/
  # and import it from BaseLayout.astro — flag it distinctly so the fix is
  # unambiguous.
  if find . -name '*.css' -print0 | xargs -0 grep -qE '@import[[:space:]]+"tailwindcss"'; then
    fail "tailwind_import_unprocessed"
  fi
  fail "theme_tokens_absent"
fi

# 4. Internal nav links resolve to generated pages. Any dangling href means
#    the builder wrote a link to a page it forgot to generate.
while IFS= read -r href; do
  [ -n "$href" ] || continue
  path="${href#/}"
  [ -z "$path" ] && path="index.html"
  [ -f "$path" ] || [ -f "$path/index.html" ] || [ -f "${path%/}.html" ] \
    || fail "nav_link_broken"
done < <(grep -oE '<a[^>]+href="/[^"#?]*"' index.html | grep -oE 'href="[^"]+"' | cut -d'"' -f2 | sort -u)

# 5. No unrendered template leakage. Mustache-style {{...}} in output usually
#    means a component was rendered as a string instead of evaluated.
! grep -qE '\{\{[^}]+\}\}' index.html || fail "unrendered_template"

# 6. <title> is not a placeholder or empty. "Astro" / "Document" are the
#    default fallbacks — if they survive to production, SEO is broken.
TITLE=$(grep -oE '<title>[^<]*</title>' index.html | sed 's/<[^>]*>//g')
case "$TITLE" in
  ''|'Astro'|'Astro Basics'|'Document') fail "placeholder_title" ;;
esac

# 7. Video backgrounds use real MP4 files, but poster attributes must point at
#    still images. A video file as its own poster produces broken/blank poster
#    behavior and caused a visible static artifact in a prior deploy.
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

# 8. Every referenced public video resolves and is large enough to be a real
#    clip, not a 0-byte/placeholder download.
while IFS= read -r src; do
  [ -n "$src" ] || continue
  case "$src" in
    http://*|https://*) continue ;;
  esac
  path="${src#/}"
  [ -s "$path" ] || fail "video_missing_or_empty"
  bytes=$(wc -c < "$path" | tr -d '[:space:]')
  [ "$bytes" -gt 102400 ] || fail "video_too_small"
done < <(find . -name '*.html' -print0 \
         | xargs -0 grep -hoE '(src|href)="/[^"]+\.(mp4|mov|m4v|webm)"' 2>/dev/null \
         | cut -d'"' -f2 | sort -u || true)

# 9. Video background component must not render a separate static poster image
#    layer behind the clip. Native <video poster> is fine; a sibling <img>
#    underneath the video makes opacity/reduced-motion states look like a double
#    exposure.
if find . -name '*.html' -print0 | xargs -0 grep -qE '<img[^>]+class="[^"]*video-bg__poster|<img[^>]+class=[^ >]*video-bg__poster' 2>/dev/null; then
  fail "video_static_poster_layer"
fi

# 10. Reduced-motion must not hide generated clips completely by default. The
#     pipeline preference is to keep opacity as-is/dim only; display:none or
#     opacity:0 caused users to think videos were not working.
if find . -name '*.css' -print0 | xargs -0 grep -qE 'video-bg__video[^}]*display:[[:space:]]*none|video-bg__video[^}]*opacity:[[:space:]]*0([;}])' 2>/dev/null; then
  fail "video_hidden_under_reduced_motion"
fi

# 11. TinaCMS admin SPA must exist at /admin/ (served from project root admin/
#     directory, not dist/client/admin/ which gets wiped by astro build).
#     Only check if tina/config.ts exists at the site root (TinaCMS project).
#     Non-TinaCMS projects skip this check.
SITE_ROOT=""
if [ -f "$(pwd)/tina/config.ts" ]; then
  SITE_ROOT="$(pwd)"
elif [ -f "$(pwd)/../tina/config.ts" ]; then
  SITE_ROOT="$(cd "$(pwd)/.." && pwd)"
elif [ -f "$(pwd)/../../tina/config.ts" ]; then
  SITE_ROOT="$(cd "$(pwd)/../.." && pwd)"
fi

if [ -n "$SITE_ROOT" ]; then
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
