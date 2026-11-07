#!/usr/bin/env bash
# Phase 5 push — commit local tree, ensure Gitea repo exists, rebase on
# remote, push with stall detection. Reads credentials from
# pipeline/vps-connection.json in the current working directory.
#
# Cwd MUST be the local project root (contains pipeline/vps-connection.json
# and is the git working tree being pushed). The script does not cd.
#
# Emits STATUS: tokens from the orchestrator's grammar:
#   NOTHING_TO_COMMIT, GITEA_HTTP_UNHEALTHY,
#   GITEA_REPO_MISSING, GITEA_AUTH_FAILED, GIT_REBASE_CONFLICT,
#   PUSH_TIMEOUT, PUSH_FAILED, PUSH_OK.
#
# Exit 0 on PUSH_OK or NOTHING_TO_COMMIT (both are fine), non-zero otherwise.

set -euo pipefail
umask 077
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The overall budget includes preparation, HTTP push, and the ONE fallback.
# Callers must allow budget + 10s for process-tree cancellation/status output.
PUSH_BUDGET_SECONDS="${ASTRO_STATIC_PUSH_BUDGET_SECONDS:-600}"
PUSH_HTTP_SECONDS="${ASTRO_STATIC_PUSH_HTTP_SECONDS:-300}"
PUSH_FALLBACK_SECONDS="${ASTRO_STATIC_PUSH_FALLBACK_SECONDS:-180}"
for seconds in "$PUSH_BUDGET_SECONDS" "$PUSH_HTTP_SECONDS" "$PUSH_FALLBACK_SECONDS"; do
  if ! [[ "$seconds" =~ ^[1-9][0-9]{0,4}$ ]] || [ "$seconds" -gt 86400 ]; then
    echo "STATUS:INVALID_VPS_CONFIG reason=bad_push_budget"; exit 1
  fi
done

# Portable timeout: Python is already required for credential encoding. The
# supervisor also handles descendants and propagates outer cancellation.
_timeout() {
  local rc=0
  python3 "$SCRIPT_DIR/operations-timeout.py" "$@" || rc=$?
  [ "$rc" -ne 124 ] || return 124
  return "$rc"
}
if [ "${1:-}" != "--budget-child" ]; then
  PUSH_DEADLINE_EPOCH=$(( $(date +%s) + PUSH_BUDGET_SECONDS ))
  rc=0
  _timeout "$PUSH_BUDGET_SECONDS" bash "$SCRIPT_DIR/push-gitea.sh" --budget-child "$PUSH_DEADLINE_EPOCH" || rc=$?
  if [ "$rc" -eq 124 ]; then
    echo "STATUS:PUSH_TIMEOUT after ${PUSH_BUDGET_SECONDS}s — overall push/fallback budget exhausted"
    echo "Inspect remote refs manually before retrying; cancellation cannot roll back accepted updates."
  fi
  exit "$rc"
fi
PUSH_DEADLINE_EPOCH="${2:-}"
NOW_EPOCH=$(date +%s)
if ! [[ "$PUSH_DEADLINE_EPOCH" =~ ^[1-9][0-9]{0,11}$ ]] \
    || [ "$PUSH_DEADLINE_EPOCH" -gt "$((NOW_EPOCH + PUSH_BUDGET_SECONDS))" ]; then
  echo "STATUS:INVALID_VPS_CONFIG reason=bad_push_deadline"; exit 1
fi
if [ "$PUSH_DEADLINE_EPOCH" -le "$NOW_EPOCH" ]; then
  echo "STATUS:PUSH_TIMEOUT — overall push/fallback deadline already expired"; exit 124
fi
export GIT_TERMINAL_PROMPT=0

VPS_JSON="pipeline/vps-connection.json"
[ -f "$VPS_JSON" ] || { echo "STATUS:INVALID_VPS_CONFIG reason=missing path=$VPS_JSON"; exit 1; }

# Preserve operator-owned conflict state, including linked-worktree git dirs.
# Never abort operations or delete .git metadata to make a push appear clean.
if git rev-parse --git-dir >/dev/null 2>&1; then
  for state in rebase-merge rebase-apply MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD sequencer; do
    state_path=$(git rev-parse --git-path "$state")
    if [ -e "$state_path" ]; then
      echo "STATUS:GIT_REBASE_CONFLICT reason=in_progress_operation state=$state"
      echo "Resolve the existing git operation manually before resuming."
      exit 1
    fi
  done
fi

GITEA_URL=$(jq -r '.gitea_url // empty'  "$VPS_JSON")
GITEA_USER=$(jq -r '.gitea_user // empty' "$VPS_JSON")
GITEA_PASS=$(jq -r '.gitea_pass // empty' "$VPS_JSON")
PROJECT=$(jq -r '.project_name // empty'  "$VPS_JSON")
for var in GITEA_URL GITEA_USER GITEA_PASS PROJECT; do
  eval "v=\${$var}"
  [ -n "${v:-}" ] || { echo "STATUS:INVALID_VPS_CONFIG reason=missing_field field=$var"; exit 1; }
done

# SSH details are optional for the primary HTTP push, but enable a robust
# fallback: ship a git bundle to the VPS and push into Gitea locally as the
# `git` user. This avoids flaky public :3000 links without bypassing the Gitea
# bare repo.
SSH_PORT=$(jq -r '.ssh_port // empty' "$VPS_JSON")
SSH_KEY=$(jq  -r '.ssh_key // empty'  "$VPS_JSON")
SSH_USER=$(jq -r '.ssh_user // empty' "$VPS_JSON")
SSH_HOST=$(jq -r '.ssh_host // empty' "$VPS_JSON")

# --- Step 1: Ensure Gitea repo exists ---
# Resolve HTTP→HTTPS redirect: Caddy auto-TLS on sslip.io redirects HTTP to
# HTTPS. curl -L follows it, but git push doesn't follow redirects. Detect the
# redirect and upgrade GITEA_URL to HTTPS before constructing the remote URL.
BASE_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
  -u "$GITEA_USER:$GITEA_PASS" \
  "$GITEA_URL/api/v1/repos/$GITEA_USER/$PROJECT")
if [ "$BASE_CODE" = "308" ] || [ "$BASE_CODE" = "301" ] || [ "$BASE_CODE" = "302" ]; then
  GITEA_URL="https://${GITEA_URL#http://}"
fi

# Idempotent: 200 = already exists, 404 = create. Anything else = fatal.
REPO_EXISTS=$(curl -s -L -o /dev/null -w "%{http_code}" --max-time 10 \
  -u "$GITEA_USER:$GITEA_PASS" \
  "$GITEA_URL/api/v1/repos/$GITEA_USER/$PROJECT")
if [ "$REPO_EXISTS" = "404" ]; then
  curl -s -o /dev/null --max-time 15 -X POST "$GITEA_URL/api/v1/user/repos" \
    -H "Content-Type: application/json" \
    -u "$GITEA_USER:$GITEA_PASS" \
    -d "{\"name\":\"$PROJECT\",\"default_branch\":\"main\",\"auto_init\":false}"
fi

# --- Step 2: Point origin at the clean remote URL and configure credentials ---
# Previously we embedded user:pass into the URL itself, which leaks the
# password into .git/config and `git remote -v` output. Now we keep the URL
# clean and use a per-repo credential helper that reads from a 600-permission
# file in pipeline/ (already gitignored).
REMOTE_URL="$GITEA_URL/$GITEA_USER/$PROJECT.git"

CRED_FILE="$(pwd)/pipeline/.git-credentials"
CRED_HELPER=$(python3 -c 'import shlex,sys; print("store --file=" + shlex.quote(sys.argv[1]))' "$CRED_FILE")
URL_PROTO=$(echo "$GITEA_URL" | sed -E 's|^(https?)://.*|\1|')
URL_HOST_PORT=$(echo "$GITEA_URL" | sed -E 's|^https?://([^/]+).*|\1|')
# URL-encode the password — '+' '/' '=' shouldn't appear (bg-bootstrap strips
# them) but be defensive against future generators or operator-set passwords.
URLENC_PASS=$(printf '%s' "$GITEA_PASS" | python3 -c 'import sys,urllib.parse; sys.stdout.write(urllib.parse.quote(sys.stdin.read(), safe=""))' 2>/dev/null || printf '%s' "$GITEA_PASS")
mkdir -p pipeline
printf '%s://%s:%s@%s\n' "$URL_PROTO" "$GITEA_USER" "$URLENC_PASS" "$URL_HOST_PORT" > "$CRED_FILE"
chmod 600 "$CRED_FILE"

# --- Step 3: Prepare local git state before committing ---
# Important: fresh VPS bootstrap creates an initial scaffold commit in Gitea.
# The generated local site starts without .git. If we commit first and only
# fetch/rebase later, git sees two unrelated/add-add histories and conflicts on
# nearly every scaffold file. Instead, fetch the remote first and, when this is
# a brand-new local repository, reset the INDEX to origin/main while preserving
# the generated working tree. The next commit becomes a normal child of the
# scaffold commit, so push is fast-forward and future runs remain resumable.
PREEXISTING_HEAD=NO
git rev-parse --verify HEAD >/dev/null 2>&1 && PREEXISTING_HEAD=YES || true

git init -b main 2>/dev/null || true
git branch -m master main 2>/dev/null || true

git remote set-url origin "$REMOTE_URL" 2>/dev/null \
  || git remote add origin "$REMOTE_URL"

# Reset the inherited helper chain for EVERY HTTP git operation. Merely adding
# a local store helper lets an earlier macOS keychain helper supply stale creds.
# These -c options are invocation-scoped: no global or persistent helper edits.
git_network() {
  local seconds="$1"; shift
  _timeout "$seconds" git -c credential.helper= \
    -c "credential.helper=$CRED_HELPER" "$@"
}

remote_bundle_push() (
  [ -n "${SSH_PORT:-}" ] && [ -n "${SSH_KEY:-}" ] && [ -n "${SSH_USER:-}" ] && [ -n "${SSH_HOST:-}" ] || return 1
  [ -f "$SSH_KEY" ] || return 1
  # Use one absolute deadline across bundle creation, transfer, SSH handshake,
  # and remote work. Never reset the allowance after a slow connection. VPS
  # and control-node clocks must be synchronized for the shared epoch bound.
  FALLBACK_DEADLINE_EPOCH=$(( $(date +%s) + PUSH_FALLBACK_SECONDS ))
  if [ "$FALLBACK_DEADLINE_EPOCH" -gt "$PUSH_DEADLINE_EPOCH" ]; then
    FALLBACK_DEADLINE_EPOCH=$PUSH_DEADLINE_EPOCH
  fi
  bundle_timeout() {
    local remaining=$((FALLBACK_DEADLINE_EPOCH - $(date +%s)))
    [ "$remaining" -gt 0 ] || return 124
    _timeout "$remaining" "$@"
  }
  bundle_timeout git rev-parse --verify main >/dev/null 2>&1 || return $?

  BUNDLE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/astro-static-push-${PROJECT}.XXXXXX") || return 1
  LOCAL_BUNDLE="$BUNDLE_DIR/site.bundle"
  REMOTE_BUNDLE="/tmp/astro-static-push-${PROJECT}-$(date +%s)-$$.bundle"
  REMOTE_REPO="/home/git/gitea-repositories/${GITEA_USER}/${PROJECT}.git"

  cleanup_local() { rm -f "$LOCAL_BUNDLE"; rmdir "$BUNDLE_DIR"; }
  trap cleanup_local EXIT
  bundle_timeout git bundle create "$LOCAL_BUNDLE" main >/dev/null || return $?
  bundle_timeout scp -P "$SSH_PORT" -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 \
    "$LOCAL_BUNDLE" "$SSH_USER@$SSH_HOST:$REMOTE_BUNDLE" >/dev/null 2>&1 || return $?

  bundle_timeout ssh -p "$SSH_PORT" -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 \
    "$SSH_USER@$SSH_HOST" \
    "set -e; \
     DEADLINE=$FALLBACK_DEADLINE_EPOCH; TMP=; \
     cleanup(){ if [ -n \"\$TMP\" ]; then sudo rm -rf \"\$TMP\"; fi; sudo rm -f '$REMOTE_BUNDLE'; }; \
     trap cleanup EXIT; \
     [ \"\$DEADLINE\" -gt \"\$(date +%s)\" ] || exit 124; \
     TMP=\$(mktemp -d /tmp/astro-static-git-push.XXXXXX); \
     test -d '$REMOTE_REPO'; \
     sudo chown git \"\$TMP\"; \
     sudo chown git '$REMOTE_BUNDLE'; \
     sudo chmod 600 '$REMOTE_BUNDLE'; \
     run_git(){ LEFT=\$((DEADLINE - \$(date +%s))); \
       [ \"\$LEFT\" -gt 0 ] || return 124; \
       sudo -u git timeout --kill-after=1 \"\$LEFT\" git -c credential.helper= \"\$@\"; }; \
     run_git clone '$REMOTE_BUNDLE' \"\$TMP/repo\" >/dev/null 2>&1; \
     run_git -C \"\$TMP/repo\" push '$REMOTE_REPO' main" >/dev/null 2>&1
)

# Private recovery originals/authorization and local backups must never enter
# the source snapshot, even if an earlier run already staged or tracked them.
# Reuse this list for ignores, index cleanup, and candidate exclusions.
PRIVATE_PATHS=(
  'pipeline/archive/'
  'pipeline/tooling-backup/'
  'pipeline/.cms-roundtrip-*/'
  'pipeline/.cms-roundtrip.lock'
  'pipeline/.cms-report-*'
  'pipeline/cms-staging.json'
  'pipeline/cms-staging.json.*'
  'pipeline/cms-roundtrip*.json'
  'pipeline/cms-roundtrip*.json.*'
  'pipeline/cms-roundtrip/'
  'pipeline/03-cms-roundtrip.json'
  'pipeline/03-cms-roundtrip*.json'
  'pipeline/03-cms-roundtrip*.json.*'
)

# Never commit generated credentials/logs. The project repo is for the site
# source, not VPS secrets. Keep this idempotent and local to the repo.
touch .gitignore
LOCAL_ONLY_PATTERNS=( \
  'node_modules/' \
  'dist/' \
  '.astro/' \
  '.opencode/' \
  '.DS_Store' \
  '.env' \
  '.env.*' \
  '*.log' \
  'pipeline/vps-connection.json' \
  'pipeline/vps-connection.json.*' \
  'pipeline/.git-credentials' \
  'pipeline/bootstrap-result.json' \
  'pipeline/bootstrap-result.json.*' \
  'pipeline/bootstrap*.json' \
  'pipeline/bootstrap*.log' \
  'pipeline/bootstrap*.pid' \
  'pipeline/bootstrap*.exit' \
  'pipeline/installation-summary.md' \
  'pipeline/installation.log' \
  'pipeline/setup-wrapper.*' \
  'pipeline/RESULT.md' \
  'pipeline/HUMAN_REVIEW.md' )
for pattern in "${LOCAL_ONLY_PATTERNS[@]}" "${PRIVATE_PATHS[@]}"; do
  grep -qxF "$pattern" .gitignore 2>/dev/null || printf '%s\n' "$pattern" >> .gitignore
done

git_network 30 fetch origin main 2>/dev/null || true
if [ "$PREEXISTING_HEAD" = "NO" ] && git rev-parse --verify origin/main >/dev/null 2>&1; then
  git reset --mixed origin/main >/dev/null
fi

# Do this AFTER seeding the index from origin/main: reset can reintroduce
# previously tracked private artifacts. Preserve all working tree originals.
UNTRACK_PATHS=()
for pattern in "${LOCAL_ONLY_PATTERNS[@]}" "${PRIVATE_PATHS[@]}"; do
  # gitignore directory globs end in '/', but git's index pathspec matcher
  # needs the unsuffixed wildcard to match already-tracked children.
  UNTRACK_PATHS+=( "${pattern%/}" )
done
git rm --cached --ignore-unmatch -r -- \
  "${UNTRACK_PATHS[@]}" pipeline/_bg-bootstrap.sh \
  >/dev/null 2>&1 || { echo "STATUS:PUSH_FAILED reason=index_cleanup_failed"; exit 1; }

CANDIDATE_PATHS=( . \
  ':!node_modules/' \
  ':!dist/' \
  ':!.astro/' \
  ':!.opencode/' \
  ':!.env' \
  ':!.env.*' \
  ':!*.log' \
  ':!pipeline/vps-connection.json' \
  ':!pipeline/vps-connection.json.*' \
  ':!pipeline/bootstrap-result.json' \
  ':!pipeline/bootstrap-result.json.*' \
  ':!pipeline/.git-credentials' \
  ':!pipeline/bootstrap*.json' \
  ':!pipeline/bootstrap*.log' \
  ':!pipeline/bootstrap*.pid' \
  ':!pipeline/bootstrap*.exit' \
  ':!pipeline/installation-summary.md' \
  ':!pipeline/installation.log' \
  ':!pipeline/setup-wrapper.*' \
  ':!pipeline/RESULT.md' \
  ':!pipeline/HUMAN_REVIEW.md' )
for pattern in "${PRIVATE_PATHS[@]}"; do
  CANDIDATE_PATHS+=( ":!$pattern" )
done

# Explicit NUL-delimited candidates avoid git add's ignored-file advice without
# swallowing real failures (index locks, permissions, invalid paths, etc.).
# Literal pathspec input also handles newlines and pathspec-looking filenames.
STAGE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/astro-static-stage.XXXXXX")
cleanup_stage() { rm -f "$STAGE_DIR/candidates" "$STAGE_DIR/ignored" "$STAGE_DIR/selected"; rmdir "$STAGE_DIR"; }
trap cleanup_stage EXIT
git ls-files --cached --others --exclude-standard -z -- "${CANDIDATE_PATHS[@]}" > "$STAGE_DIR/candidates" \
  || { echo "STATUS:PUSH_FAILED reason=staging_candidates_failed"; exit 1; }
git ls-files --cached --ignored --exclude-standard -z > "$STAGE_DIR/ignored" \
  || { echo "STATUS:PUSH_FAILED reason=staging_candidates_failed"; exit 1; }
python3 - "$STAGE_DIR" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
ignored = set((root / 'ignored').read_bytes().split(b'\0'))
selected = dict.fromkeys((root / 'candidates').read_bytes().split(b'\0'))
(root / 'selected').write_bytes(b''.join(p + b'\0' for p in selected if p and p not in ignored))
PY
if [ -s "$STAGE_DIR/selected" ]; then
  git --literal-pathspecs add -A --pathspec-from-file="$STAGE_DIR/selected" --pathspec-file-nul \
    || { echo "STATUS:PUSH_FAILED reason=staging_failed"; exit 1; }
fi
cleanup_stage
trap - EXIT
if git diff --cached --quiet; then
  echo "STATUS:NOTHING_TO_COMMIT"
else
  git -c user.email=pipeline@localhost -c user.name="Site Pipeline" \
    commit -m "Generated site — $(date +%Y-%m-%d)" --quiet
fi

# --- Step 4: Preflight — authenticated Gitea HTTP ---
# Never run `git push` without proving Gitea is answering with the right
# credentials. A raw `/dev/tcp` probe used to be a hard blocker here, but it
# produced false negatives on control-node shells while `curl` and Gitea auth
# were healthy. HTTP is the protocol git will actually use for this remote, so
# repo-scoped authenticated HTTP is the authoritative preflight.
GITEA_HOST=$(echo "$GITEA_URL" | sed -E 's|^https?://([^/:]+).*|\1|')
GITEA_PORT=$(echo "$GITEA_URL" | sed -nE 's|^https?://[^/:]+:([0-9]+).*|\1|p')
if [ -z "$GITEA_PORT" ]; then
  case "$GITEA_URL" in https://*) GITEA_PORT=443;; *) GITEA_PORT=80;; esac
fi

# Optional diagnostic only. Do not fail if /dev/tcp is unavailable or lies.
_timeout 5 bash -c ": > /dev/tcp/$GITEA_HOST/$GITEA_PORT" 2>/dev/null \
  || echo "STATUS:GITEA_TCP_PROBE_WARNING host=$GITEA_HOST port=$GITEA_PORT — continuing to HTTP preflight" >&2

# Authenticated repo-scoped check — proves creds AND repo existence in one call.
# More useful than anonymous /api/v1/version, which doesn't exercise the
# credential path.
REPO_CODE=$(curl -s -L -o /dev/null -w '%{http_code}' --max-time 10 \
  -u "$GITEA_USER:$GITEA_PASS" "$GITEA_URL/api/v1/repos/$GITEA_USER/$PROJECT")
case "$REPO_CODE" in
  200) : ;;
  404) echo "STATUS:GITEA_REPO_MISSING user=$GITEA_USER repo=$PROJECT"; exit 1 ;;
  401|403) echo "STATUS:GITEA_AUTH_FAILED code=$REPO_CODE"; exit 1 ;;
  *)   echo "STATUS:GITEA_HTTP_UNHEALTHY code=$REPO_CODE host=$GITEA_HOST port=$GITEA_PORT"; exit 1 ;;
esac

# --- Step 5: Rebase on remote before push ---
# git-sync-watch on the VPS auto-commits file-backed content edits to Gitea, so by
# the time we reach Phase 5 on a warm project the remote may already be ahead
# of local HEAD. Without this rebase, push is rejected as non-fast-forward and
# any remote content edits made between runs are lost.
git_network 30 fetch origin main 2>/dev/null || true
if git rev-parse --verify origin/main >/dev/null 2>&1; then
  if ! git_network 60 pull --rebase origin main; then
    echo "STATUS:GIT_REBASE_CONFLICT"
    echo "The local site has diverged from Gitea (likely a content edit on the VPS)."
    echo "Resolve the conflict manually in $(pwd) and re-run the orchestrator."
    exit 1
  fi
fi

# --- Step 6: Push with hard wall-clock cap + stall detection ---
# LOW_SPEED_LIMIT is deliberately low: small VPS/Gitea links can dip below
# 1KB/s for short stretches while still making progress. A prior 1000/30 gate
# caused false PUSH_FAILED results on healthy but slow pushes.
# The HTTP cap and the overall supervisor both apply regardless of activity.
set +e
GIT_HTTP_LOW_SPEED_LIMIT=100 \
GIT_HTTP_LOW_SPEED_TIME=90 \
git_network "$PUSH_HTTP_SECONDS" push -u origin main
PUSH_EXIT=$?
set -e

BUNDLE_EXIT=0
if [ "$PUSH_EXIT" -ne 0 ]; then
  echo "WARN:PUSH_HTTP_FAILED exit=$PUSH_EXIT — trying remote bundle fallback over SSH" >&2
  if remote_bundle_push; then
    echo "STATUS:PUSH_OK method=remote_bundle_fallback"
    exit 0
  else
    BUNDLE_EXIT=$?
  fi
fi

if [ "$PUSH_EXIT" -eq 124 ] || [ "$BUNDLE_EXIT" -eq 124 ]; then
  echo "STATUS:PUSH_TIMEOUT — HTTP push or bounded bundle fallback exhausted its budget"
  echo "Inspect remote refs manually before retrying; cancellation cannot roll back accepted updates."
  exit 1
fi

case "$PUSH_EXIT" in
  0)   echo "STATUS:PUSH_OK"; exit 0 ;;
  *)   echo "STATUS:PUSH_FAILED exit=$PUSH_EXIT"; exit 1 ;;
esac
