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

set -eu

# Portable timeout: macOS doesn't ship `timeout` (it's `gtimeout` from coreutils).
# Define a function that delegates to whatever is available, or falls back to
# a perl-based wrapper. This prevents silent command-not-found failures on macOS.
if command -v timeout >/dev/null 2>&1; then
  _timeout() { timeout "$@"; }
elif command -v gtimeout >/dev/null 2>&1; then
  _timeout() { gtimeout "$@"; }
else
  # perl-based fallback: perl is present on every macOS and Debian system.
  # Usage: _timeout <seconds> <command> [args...]
  _timeout() {
    local secs="$1"; shift
    perl -e 'alarm shift; exec @ARGV' "$secs" "$@"
  }
fi

VPS_JSON="pipeline/vps-connection.json"
[ -f "$VPS_JSON" ] || { echo "STATUS:INVALID_VPS_CONFIG reason=missing path=$VPS_JSON"; exit 1; }

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
git rebase --abort 2>/dev/null || true
rm -rf .git/rebase-merge .git/rebase-apply 2>/dev/null || true

git remote set-url origin "$REMOTE_URL" 2>/dev/null \
  || git remote add origin "$REMOTE_URL"

# Per-repo credential helper. --local writes to .git/config; the helper
# itself only contains the *path* to the cred file, not the password.
git config --local credential.helper "store --file=$CRED_FILE"

remote_bundle_push() {
  [ -n "${SSH_PORT:-}" ] && [ -n "${SSH_KEY:-}" ] && [ -n "${SSH_USER:-}" ] && [ -n "${SSH_HOST:-}" ] || return 1
  [ -f "$SSH_KEY" ] || return 1
  git rev-parse --verify main >/dev/null 2>&1 || return 1

  LOCAL_BUNDLE=$(mktemp "${TMPDIR:-/tmp}/astro-static-push-${PROJECT}.XXXXXX.bundle") || return 1
  REMOTE_BUNDLE="/tmp/astro-static-push-${PROJECT}-$(date +%s)-$$.bundle"
  REMOTE_REPO="/home/git/gitea-repositories/${GITEA_USER}/${PROJECT}.git"

  cleanup_local() { rm -f "$LOCAL_BUNDLE" 2>/dev/null || true; }
  trap cleanup_local RETURN

  git bundle create "$LOCAL_BUNDLE" main >/dev/null || return 1
  scp -P "$SSH_PORT" -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 \
    "$LOCAL_BUNDLE" "$SSH_USER@$SSH_HOST:$REMOTE_BUNDLE" >/dev/null 2>&1 || return 1

  ssh -p "$SSH_PORT" -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 \
    "$SSH_USER@$SSH_HOST" \
    "set -e; \
     TMP=\$(mktemp -d /tmp/astro-static-git-push.XXXXXX); \
     cleanup(){ sudo rm -rf \"\$TMP\" '$REMOTE_BUNDLE'; }; \
     trap cleanup EXIT; \
     test -d '$REMOTE_REPO'; \
     sudo -u git git clone '$REMOTE_BUNDLE' \"\$TMP/repo\" >/dev/null 2>&1; \
     sudo -u git git -C \"\$TMP/repo\" push '$REMOTE_REPO' main" >/dev/null 2>&1
}

# Never commit generated credentials/logs. The project repo is for the site
# source, not VPS secrets. Keep this idempotent and local to the repo.
touch .gitignore
for pattern in \
  'node_modules/' \
  'dist/' \
  '.astro/' \
  '.opencode/' \
  '.DS_Store' \
  '.env' \
  '.env.*' \
  '*.log' \
  'pipeline/vps-connection.json' \
  'pipeline/.git-credentials' \
  'pipeline/bootstrap*.json' \
  'pipeline/bootstrap*.log' \
  'pipeline/bootstrap*.pid' \
  'pipeline/bootstrap*.exit' \
  'pipeline/RESULT.md' \
  'pipeline/HUMAN_REVIEW.md'; do
  grep -qxF "$pattern" .gitignore 2>/dev/null || printf '%s\n' "$pattern" >> .gitignore
done

# If a previous broken run already staged/tracked local-only artifacts, untrack
# them now. Do not delete the working tree copies; just keep the Gitea source
# repository free of dependencies, build output, secrets, and transient logs.
git rm --cached --ignore-unmatch -r \
  node_modules dist .astro .opencode \
  pipeline/vps-connection.json pipeline/bootstrap-result.json pipeline/.git-credentials \
  pipeline/bootstrap.log pipeline/_bg-bootstrap.sh \
  >/dev/null 2>&1 || true

_timeout 30 git fetch origin main 2>/dev/null || true
if [ "$PREEXISTING_HEAD" = "NO" ] && git rev-parse --verify origin/main >/dev/null 2>&1; then
  git reset --mixed origin/main >/dev/null
fi

git add -A -- . \
  ':!node_modules/' \
  ':!dist/' \
  ':!.astro/' \
  ':!.opencode/' \
  ':!.env' \
  ':!.env.*' \
  ':!*.log' \
  ':!pipeline/vps-connection.json' \
  ':!pipeline/bootstrap-result.json' \
  ':!pipeline/.git-credentials' \
  ':!pipeline/bootstrap*.json' \
  ':!pipeline/bootstrap*.log' \
  ':!pipeline/bootstrap*.pid' \
  ':!pipeline/bootstrap*.exit' \
  ':!pipeline/RESULT.md' \
  ':!pipeline/HUMAN_REVIEW.md'
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
_timeout 30 git fetch origin main 2>/dev/null || true
if git rev-parse --verify origin/main >/dev/null 2>&1; then
  if ! _timeout 60 git pull --rebase origin main; then
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
# timeout 300 is the hard ceiling regardless of activity.
set +e
GIT_HTTP_LOW_SPEED_LIMIT=100 \
GIT_HTTP_LOW_SPEED_TIME=90 \
_timeout 300 git push -u origin main
PUSH_EXIT=$?
set -e

if [ "$PUSH_EXIT" -ne 0 ]; then
  echo "WARN:PUSH_HTTP_FAILED exit=$PUSH_EXIT — trying remote bundle fallback over SSH" >&2
  if remote_bundle_push; then
    echo "STATUS:PUSH_OK method=remote_bundle_fallback"
    exit 0
  fi
fi

case "$PUSH_EXIT" in
  0)   echo "STATUS:PUSH_OK"; exit 0 ;;
  124) echo "STATUS:PUSH_TIMEOUT after 300s — Gitea accepted connection but push stalled and remote bundle fallback failed"; exit 1 ;;
  *)   echo "STATUS:PUSH_FAILED exit=$PUSH_EXIT"; exit 1 ;;
esac
