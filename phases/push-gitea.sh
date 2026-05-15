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

# --- Step 1: Ensure Gitea repo exists ---
# Idempotent: 200 = already exists, 404 = create. Anything else = fatal.
REPO_EXISTS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
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

# Never commit generated credentials/logs. The project repo is for the site
# source, not VPS secrets. Keep this idempotent and local to the repo.
touch .gitignore
for pattern in \
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

timeout 30 git fetch origin main 2>/dev/null || true
if [ "$PREEXISTING_HEAD" = "NO" ] && git rev-parse --verify origin/main >/dev/null 2>&1; then
  git reset --mixed origin/main >/dev/null
fi

git add -A
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
timeout 5 bash -c ": > /dev/tcp/$GITEA_HOST/$GITEA_PORT" 2>/dev/null \
  || echo "WARN:GITEA_TCP_PROBE_FAILED host=$GITEA_HOST port=$GITEA_PORT — continuing to HTTP preflight" >&2

# Authenticated repo-scoped check — proves creds AND repo existence in one call.
# More useful than anonymous /api/v1/version, which doesn't exercise the
# credential path.
REPO_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
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
timeout 30 git fetch origin main 2>/dev/null || true
if git rev-parse --verify origin/main >/dev/null 2>&1; then
  if ! timeout 60 git pull --rebase origin main; then
    echo "STATUS:GIT_REBASE_CONFLICT"
    echo "The local site has diverged from Gitea (likely a content edit on the VPS)."
    echo "Resolve the conflict manually in $(pwd) and re-run the orchestrator."
    exit 1
  fi
fi

# --- Step 6: Push with hard wall-clock cap + stall detection ---
# LOW_SPEED_LIMIT=1000 bytes/s over LOW_SPEED_TIME=30s triggers abort —
# catches silent stalls where the server accepts bytes then stops acking.
# timeout 180 is the hard ceiling regardless of activity.
set +e
GIT_HTTP_LOW_SPEED_LIMIT=1000 \
GIT_HTTP_LOW_SPEED_TIME=30 \
timeout 180 git push -u origin main
PUSH_EXIT=$?
set -e

case "$PUSH_EXIT" in
  0)   echo "STATUS:PUSH_OK"; exit 0 ;;
  124) echo "STATUS:PUSH_TIMEOUT after 180s — Gitea accepted connection but push stalled"; exit 1 ;;
  *)   echo "STATUS:PUSH_FAILED exit=$PUSH_EXIT"; exit 1 ;;
esac
