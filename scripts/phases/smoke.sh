#!/usr/bin/env bash
# Post-build smoke test. Runs from within the built dist/ directory and checks
# that index.html is actually functional — not just that a file exists.
#
# `astro build` returning zero + dist/index.html being present does NOT prove
# the page works. These six checks catch the classes of bug that previously
# shipped to production: missing CSS import, broken nav links, unrendered
# template fragments, empty theme tokens, placeholder <title>.
#
# Output:  STATUS:SMOKE_OK               (exit 0)
#      or  STATUS:SMOKE_FAIL check=<N>   (exit 1, where N describes what failed)
#
# Expected cwd: the dist/ directory (e.g. /var/www/sites/<project>/dist).
# The orchestrator invokes this over ssh like:
#   ssh $VPS "cd $SITE_DIR/dist && bash -s" < phases/smoke.sh

set -eu

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

echo "STATUS:SMOKE_OK"
