#!/usr/bin/env bash
#
# sync.sh — install the astro-static pipeline into OpenCode, or check for drift.
#
# Usage:
#   ./sync.sh install   Copy this repo  ->  your live OpenCode config (3 dirs).
#   ./sync.sh status    Show what differs between this repo and the live install.
#   ./sync.sh pull      Copy the live install  ->  this repo (rescue in-place edits).
#
# This repo is the source of truth. Normal loop:
#   edit here  ->  ./sync.sh install  ->  test in OpenCode  ->  git commit  ->  git push
# Use `pull` only to recover edits you made directly under ~/.config/opencode.
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OC="${OPENCODE_CONFIG_DIR:-$HOME/.config/opencode}"

# install/pull copy contents + perms + times; status compares by content
# checksum (-c) and ignores mtime, so cosmetic time differences are not "drift".
RFLAGS_WRITE="-rlpt"
RFLAGS_CHECK="-rlpc"
EXCLUDES=(--exclude=__pycache__/ --exclude=.pytest_cache/ --exclude='*.pyc' --exclude=.DS_Store)

# What this repo owns and where each part installs in OpenCode.
#   1. agent prompts + schemas + references  (everything under agents/astro-static EXCEPT scripts/)
#   2. runtime scripts                        (agents/astro-static/scripts/* -> sibling runtime dir;
#                                              excludes models/ so the toolkit below survives --delete)
#   3. model toolkit                          (models/* -> the runtime dir's models/ subdir)
#   4. slash commands
# Fields: label | SRC (repo) | DST (opencode) | extra rsync excludes
MAPPINGS=(
  "agent prompts/schemas/refs|$REPO/agents/astro-static/|$OC/agents/astro-static/|--exclude=scripts/"
  "runtime scripts|$REPO/agents/astro-static/scripts/|$OC/astro-static/|--exclude=models/"
  "model toolkit|$REPO/models/|$OC/astro-static/models/|"
  "slash commands|$REPO/commands/astro-static/|$OC/commands/astro-static/|"
)

command -v rsync >/dev/null 2>&1 || { echo "ERROR: rsync is required but not found."; exit 1; }

mode="${1:-}"
case "$mode" in
  install|status|pull) ;;
  *) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac

drift=0
for entry in "${MAPPINGS[@]}"; do
  IFS='|' read -r label src dst extra <<<"$entry"
  extra_arr=(); [ -n "$extra" ] && extra_arr=("$extra")
  case "$mode" in
    install)
      mkdir -p "$dst"
      rsync $RFLAGS_WRITE --delete "${EXCLUDES[@]}" ${extra_arr[@]+"${extra_arr[@]}"} "$src" "$dst"
      echo "  installed  ->  $dst   ($label)"
      ;;
    pull)
      mkdir -p "$src"
      rsync $RFLAGS_WRITE --delete "${EXCLUDES[@]}" ${extra_arr[@]+"${extra_arr[@]}"} "$dst" "$src"
      echo "  pulled     <-  $dst   ($label)"
      ;;
    status)
      # Keep only real content drift: new/changed/deleted items. Lines whose
      # itemize code starts with '.' mean identical content (only mtime/perms
      # attrs differ) and are ignored.
      out="$(rsync $RFLAGS_CHECK -in --delete "${EXCLUDES[@]}" ${extra_arr[@]+"${extra_arr[@]}"} "$src" "$dst" 2>/dev/null \
             | grep -vE '^(\.|cd)' | awk 'NF' || true)"
      if [ -z "$out" ]; then
        echo "  in sync    ($label)"
      else
        drift=1
        echo "  DIFFERS    ($label)  ->  $dst"
        printf '%s\n' "$out" | sed 's/^/        /'
      fi
      ;;
  esac
done

case "$mode" in
  install) echo ""; echo "Install complete. Test in OpenCode, then:  git add -A && git commit -m '...' && git push" ;;
  status)
    echo ""
    if [ "$drift" = 0 ]; then
      echo "All in sync."
    else
      echo "Drift detected. Run './sync.sh install' to push repo -> live, or './sync.sh pull' to bring live edits into the repo."
      exit 1
    fi
    ;;
esac
