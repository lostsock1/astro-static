#!/usr/bin/env bash
# Source-only helpers for per-phase retry-dedupe. Appends each attempt to
# pipeline/retry.log and answers whether the same phase+error signature has
# already been seen — so a stuck subagent can't spin the whole retry budget
# on one failure.
#
# Usage:
#   source ~/.config/opencode/astro-static/phases/retry.sh
#   append_retry "phase4-build" "STATUS:BUILD_FAILED reason=no_index_html"
#   HASH=$(printf '%s' "$LINE" | sha256sum | cut -c1-16)
#   if ! should_retry "phase4-build" "$HASH"; then
#     echo "HALT: same error twice — see HUMAN_REVIEW.md"
#     exit 1
#   fi
#
# Retry log format (TSV, one line per attempt):
#   <iso8601>\t<phase>\t<token>\t<hash>\t<full status line>

append_retry() {
  local phase="$1" line="$2"
  local hash token
  hash=$(printf '%s' "$line" | sha256sum | cut -c1-16)
  token=$(printf '%s' "$line" | awk '{print $1}')
  mkdir -p pipeline
  printf '%s\t%s\t%s\t%s\t%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$phase" "$token" "$hash" "$line" \
    >> pipeline/retry.log
}

# Returns 0 (retry OK) if the same phase+hash has occurred <=1 times,
# 1 (give up) otherwise. Allows a single retry of an identical failure,
# then halts — same-error-twice means the retry isn't fixing anything.
should_retry() {
  local phase="$1" hash="$2"
  local hits
  hits=$(awk -v p="$phase" -v h="$hash" -F'\t' '$2==p && $4==h' \
         pipeline/retry.log 2>/dev/null | wc -l)
  [ "$hits" -le 1 ]
}
