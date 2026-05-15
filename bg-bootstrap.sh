#!/usr/bin/env bash
# Background VPS bootstrap helper.
# Reads all config from pipeline/vps-connection.json — no variable substitution needed.
# Called from the project root: bash pipeline/_bg-bootstrap.sh </dev/null >/dev/null 2>&1 &
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VPS_JSON="$PROJECT_DIR/pipeline/vps-connection.json"

PORT=$(jq -r '.ssh_port'  "$VPS_JSON")
KEY=$(jq  -r '.ssh_key'   "$VPS_JSON")
USR=$(jq  -r '.ssh_user'  "$VPS_JSON")
HOST=$(jq  -r '.ssh_host'  "$VPS_JSON")
PROJECT=$(jq -r '.project_name' "$VPS_JSON")

[[ "$PROJECT" =~ ^[a-z0-9][a-z0-9-]{0,62}$ ]] || { echo "STATUS:INVALID_VPS_CONFIG reason=bad_project_name"; exit 2; }
[[ "$HOST" =~ ^[A-Za-z0-9.-]+$ ]] || { echo "STATUS:INVALID_VPS_CONFIG reason=bad_ssh_host"; exit 2; }
[[ "$PORT" =~ ^[0-9]+$ && "$PORT" -ge 1 && "$PORT" -le 65535 ]] || { echo "STATUS:INVALID_VPS_CONFIG reason=bad_ssh_port"; exit 2; }
[[ "$USR" =~ ^[A-Za-z_][A-Za-z0-9_.-]{0,63}$ ]] || { echo "STATUS:INVALID_VPS_CONFIG reason=bad_ssh_user"; exit 2; }

# --- Gitea admin password: random per-project, persisted locally ---
# Reuse the value in vps-connection.json on re-runs (idempotent). Generate a
# fresh one only on the first launch. Persist BEFORE we launch the VPS wrapper
# so the orchestrator's Bootstrap Join can read it straight from the local
# file — no wrapper-grep, no hard-coded fallback.
# tr strips base64 chars that break shell/URL contexts (=, +, /, newline).
GITEA_PASS=$(jq -r '.gitea_pass // empty' "$VPS_JSON")
if [[ -z "$GITEA_PASS" ]]; then
  GITEA_PASS=$(openssl rand -base64 24 | tr -d '=+/\n' | cut -c1-24)
  jq --arg p "$GITEA_PASS" --arg u "$PROJECT" \
     '.gitea_pass = $p | .gitea_user = (.gitea_user // $u)' \
     "$VPS_JSON" > "$VPS_JSON.tmp" && mv "$VPS_JSON.tmp" "$VPS_JSON"
  chmod 600 "$VPS_JSON"   # password is now inside — keep it owner-only
fi

# Clear stale host key if the VPS was reinstalled (changed fingerprint).
# Without this, SSH refuses to connect with "REMOTE HOST IDENTIFICATION HAS CHANGED".
# ssh-keygen -R is idempotent and safe — it only removes the specific host entry.
ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$HOST" 2>/dev/null || true

_astro_static_ssh() {
  ssh -p "$PORT" -i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "$USR@$HOST" "$@"
}
SSH=_astro_static_ssh

# Initialize log with timestamp
echo "=== Bootstrap started $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" > "$PROJECT_DIR/pipeline/bootstrap.log"

# Ensure the remote setup script exists. The orchestrator normally uploads this
# before launching bg-bootstrap, but thin wrappers and manual resumes have
# historically missed that step, causing an immediate `/tmp/setup-vps.sh: No
# such file or directory` failure. Make bg-bootstrap self-contained and
# idempotent by uploading the canonical script when available.
SETUP_SRC="${ASTRO_STATIC_SETUP_VPS:-$HOME/.config/opencode/astro-static/setup-vps.sh}"
if [[ -f "$SETUP_SRC" ]]; then
  scp -P "$PORT" -i "$KEY" -o StrictHostKeyChecking=accept-new \
    "$SETUP_SRC" "$USR@$HOST:/tmp/setup-vps.sh" \
    >> "$PROJECT_DIR/pipeline/bootstrap.log" 2>&1 \
    || { echo "STATUS:BOOTSTRAP_SETUP_UPLOAD_FAILED src=$SETUP_SRC" >> "$PROJECT_DIR/pipeline/bootstrap.log"; exit 1; }
  $SSH "chmod +x /tmp/setup-vps.sh" >> "$PROJECT_DIR/pipeline/bootstrap.log" 2>&1 || true
else
  echo "WARNING: setup-vps.sh not found locally at $SETUP_SRC; assuming /tmp/setup-vps.sh already exists on VPS" \
    >> "$PROJECT_DIR/pipeline/bootstrap.log"
fi

# Write a setup wrapper script to /tmp on VPS that handles env vars safely.
# This avoids inline shell escaping issues with special chars in passwords.
# NOTE: the heredoc is quoted ('WRAPPER'), so local vars below are NOT expanded
# on the local side — they expand on the VPS from the \"${…}\" interpolations
# our outer $SSH fed through. GITEA_PASS carries the per-project random value
# written to vps-connection.json above.
GITEA_USER=$(jq -r '.gitea_user // "siteadmin"' "$VPS_JSON")
$SSH "cat > /tmp/pipeline-setup-wrapper.sh << 'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export PROJECT_NAME=\"${PROJECT}\"
export GITEA_ADMIN_USER=\"${GITEA_USER}\"
export GITEA_ADMIN_PASS=\"${GITEA_PASS}\"
export GITEA_ADMIN_EMAIL=\"admin@localhost\"
export DOMAIN=\"auto\"

# Clean previous state files (owned by us now, not root)
rm -f /tmp/setup-vps.exit /tmp/setup-vps.log /tmp/pipeline-result.json

# Write the exit code via EXIT trap so it fires on *every* exit path:
# normal exit, set -e abort, SIGTERM from nohup cleanup, SSH session death.
# Previously this was a post-bash 'echo \$? > ...' line that was skipped
# whenever setup-vps.sh exited via signal — leaving bg-bootstrap's waiter
# spinning for its full 1200s budget and the background process alive.
trap 'echo \$? > /tmp/setup-vps.exit' EXIT

# Run setup, capturing output (exit code is captured by the trap above)
bash /tmp/setup-vps.sh > /tmp/setup-vps.log 2>&1
WRAPPER
chmod +x /tmp/pipeline-setup-wrapper.sh" >> "$PROJECT_DIR/pipeline/bootstrap.log" 2>&1 || true

# Launch setup on VPS under nohup so it survives SSH disconnect.
# Uses the wrapper script instead of inline command — avoids shell escaping bugs.
# Redirection order: file first, then dup stderr to that file. The reverse
# (2>&1 >> file) leaks stderr to the controlling terminal.
$SSH "nohup sudo bash /tmp/pipeline-setup-wrapper.sh > /dev/null 2>&1 &
echo LAUNCHED" >> "$PROJECT_DIR/pipeline/bootstrap.log" 2>&1 || true

# Wait for the VPS to write its exit file. Instead of firing one SSH handshake
# every 15s (which racks up 80+ connections across a 20 min install and makes
# the VPS auth log unreadable), we open ONE long-lived SSH session and poll
# locally on the remote side. Falls back to local polling only if the SSH
# drops mid-bootstrap (we retry up to 3 times).
WAIT_ATTEMPT=0
WAIT_MAX=3
WAITED_TOTAL=0
WAIT_BUDGET=1200   # seconds; matches the old cap

while [[ "$WAIT_ATTEMPT" -lt "$WAIT_MAX" ]] && [[ "$WAITED_TOTAL" -lt "$WAIT_BUDGET" ]]; do
  WAIT_ATTEMPT=$((WAIT_ATTEMPT + 1))
  REMAINING=$((WAIT_BUDGET - WAITED_TOTAL))
  echo "  Remote-wait attempt ${WAIT_ATTEMPT}/${WAIT_MAX} (budget ${REMAINING}s)" \
    >> "$PROJECT_DIR/pipeline/bootstrap.log"
  # ServerAliveInterval keeps the connection alive during apt-get's silent stretches.
  # Remote loop exits as soon as the exit file exists OR the budget elapses.
  ssh -p "$PORT" -i "$KEY" \
      -o StrictHostKeyChecking=accept-new \
      -o ConnectTimeout=10 \
      -o ServerAliveInterval=30 \
      -o ServerAliveCountMax=6 \
      "$USR@$HOST" \
      "BUDGET=$REMAINING; WAITED=0; \
       while [ ! -f /tmp/setup-vps.exit ] && [ \"\$WAITED\" -lt \"\$BUDGET\" ]; do \
         sleep 15; WAITED=\$((WAITED + 15)); \
         echo \"  Bootstrap running... (\${WAITED}s on VPS)\"; \
       done; \
       test -f /tmp/setup-vps.exit" \
    >> "$PROJECT_DIR/pipeline/bootstrap.log" 2>&1

  WAIT_RC=$?
  if [[ "$WAIT_RC" -eq 0 ]]; then
    break   # exit file present — proceed to retrieve it
  fi

  # Either the remote waiter returned non-zero (file not present at budget) or
  # the SSH connection itself dropped. Re-probe briefly before a full reconnect.
  sleep 5
  WAITED_TOTAL=$((WAITED_TOTAL + 20))
done

# Final existence check via a single short-lived SSH — source of truth.
if ! $SSH "test -f /tmp/setup-vps.exit" 2>/dev/null; then
  echo "TIMEOUT" > "$PROJECT_DIR/pipeline/bootstrap.exit"
  echo "TIMEOUT after ${WAITED_TOTAL}s (remote waiter dropped)" >> "$PROJECT_DIR/pipeline/bootstrap.log"
  exit 1
fi

# Retrieve log and exit code from VPS
$SSH "sudo cat /tmp/setup-vps.log" >> "$PROJECT_DIR/pipeline/bootstrap.log" 2>&1 || true

# Read exit code robustly — strip whitespace, validate it's numeric
RAW_EXIT=$($SSH "sudo cat /tmp/setup-vps.exit" 2>/dev/null || echo "UNKNOWN")
CLEAN_EXIT=$(echo "$RAW_EXIT" | head -1 | tr -d '[:space:]')
if echo "$CLEAN_EXIT" | grep -qE '^[0-9]+$'; then
  echo "$CLEAN_EXIT" > "$PROJECT_DIR/pipeline/bootstrap.exit"
else
  # Non-numeric exit file — VPS script was interrupted or corrupted
  echo "1" > "$PROJECT_DIR/pipeline/bootstrap.exit"
  echo "WARNING: VPS exit file non-numeric ('$RAW_EXIT'), defaulting to 1" >> "$PROJECT_DIR/pipeline/bootstrap.log"
fi

echo "=== Bootstrap complete (exit=$(cat "$PROJECT_DIR/pipeline/bootstrap.exit")) $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" >> "$PROJECT_DIR/pipeline/bootstrap.log"
