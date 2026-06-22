#!/usr/bin/env bash
# Bootstrap Join — blocking wait for background VPS bootstrap, then validate.
# Runs from the project root (cwd contains pipeline/vps-connection.json).
# Emits STATUS tokens from the orchestrator grammar:
#   BOOTSTRAP_FAILED, BOOTSTRAP_RESULT_INVALID,
#   BOOTSTRAP_JOIN_PROBE_FAILED, BOOTSTRAP_JOIN_GITEA_AUTH_FAILED,
#   BOOTSTRAP_OK
#
# Exit 0 on BOOTSTRAP_OK, non-zero otherwise.
#
# Preconditions enforced upstream (do NOT re-defend here):
# - bg-bootstrap.sh writes gitea_pass into vps-connection.json BEFORE the
#   VPS wrapper launches, so the password is authoritative locally.
# - bg-bootstrap.sh normalizes pipeline/bootstrap.exit to a numeric or
#   "TIMEOUT" string, so we only need to check for "0" vs anything else.
# - setup-vps.sh has an EXIT trap that always writes /var/lib/site-pipeline/pipeline-result.json,
#   so its absence on the VPS is a real error — not a case to reconstruct.
#
# If vps-connection.json is missing gitea_pass or pipeline-result.json is
# missing on the VPS, we fail loud — no recovery.

set -eu
umask 077

VPS_JSON="pipeline/vps-connection.json"
[ -f "$VPS_JSON" ] || { echo "STATUS:BOOTSTRAP_FAILED reason=missing_vps_json"; exit 1; }

PORT=$(jq -r '.ssh_port' "$VPS_JSON")
KEY=$(jq  -r '.ssh_key'  "$VPS_JSON")
USR=$(jq  -r '.ssh_user' "$VPS_JSON")
HOST=$(jq -r '.ssh_host' "$VPS_JSON")
PROJECT=$(jq -r '.project_name' "$VPS_JSON")

case "$HOST" in
  ""|null|*[!A-Za-z0-9._-]*) echo "STATUS:INVALID_VPS_CONFIG reason=bad_ssh_host"; exit 1 ;;
esac
case "$PORT" in
  ''|null|*[!0-9]*) echo "STATUS:INVALID_VPS_CONFIG reason=bad_ssh_port"; exit 1 ;;
esac
if [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
  echo "STATUS:INVALID_VPS_CONFIG reason=bad_ssh_port"
  exit 1
fi
case "$USR" in
  ""|null|*[!A-Za-z0-9._-]*) echo "STATUS:INVALID_VPS_CONFIG reason=bad_ssh_user"; exit 1 ;;
esac
case "$KEY" in
  ""|null|*$'\n'*|*$'\r'*) echo "STATUS:INVALID_VPS_CONFIG reason=bad_ssh_key"; exit 1 ;;
esac
case "$PROJECT" in
  ""|null|*[!A-Za-z0-9._-]*) echo "STATUS:INVALID_VPS_CONFIG reason=bad_project_name"; exit 1 ;;
esac

_astro_static_ssh() {
  ssh -p "$PORT" -i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "$USR@$HOST" "$@"
}
SSH=_astro_static_ssh

# --- Step 1: Wait for background bootstrap to finish ---
# bg-bootstrap.sh owns the remote wait (single long-lived SSH coalesces what
# used to be 80+ short connections). It writes pipeline/bootstrap.exit when
# done. Our job here is just to wait for that local PID to exit.
#
# Cap at 1500s so a runaway bg-bootstrap can't block forever. The post-wait
# VPS probe in Step 2 is the source of truth — if bg-bootstrap exits without
# an exit file, we still consult the VPS once and accept BOOTSTRAPPED=YES.
if [ -f pipeline/bootstrap.pid ] && [ ! -f pipeline/bootstrap.exit ]; then
  PID=$(cat pipeline/bootstrap.pid)
  echo "Waiting for VPS bootstrap (pid $PID)..."
  WAITED=0
  WAIT_MAX=1500
  while kill -0 "$PID" 2>/dev/null && [ "$WAITED" -lt "$WAIT_MAX" ]; do
    sleep 5
    WAITED=$((WAITED + 5))
  done
  if kill -0 "$PID" 2>/dev/null; then
    echo "bg-bootstrap pid $PID still alive after ${WAIT_MAX}s — Step 2 will consult VPS state directly"
  fi
fi

# --- Step 2: Evaluate exit code ---
# bg-bootstrap.sh normalizes the file, so EXIT is either "0", a non-zero
# numeric, or "TIMEOUT". Any value except "0" triggers a VPS-state probe
# as secondary evidence — the exit file is a local proxy; the VPS is the
# source of truth.
EXIT=$(cat pipeline/bootstrap.exit 2>/dev/null | head -1 | tr -d '[:space:]' || echo MISSING)

if [ "$EXIT" != "0" ]; then
  VPS_OK=$($SSH "test -f /var/lib/site-pipeline/bootstrapped && echo YES || echo NO" 2>/dev/null || echo NO)
  if [ "$VPS_OK" != "YES" ]; then
    echo "STATUS:BOOTSTRAP_FAILED exit=$EXIT — see pipeline/bootstrap.log"
    exit 1
  fi
  echo "VPS probe confirms BOOTSTRAPPED=YES — treating join as successful (exit=$EXIT)"
fi

# --- Step 3: Fetch structured bootstrap result (required) ---
# setup-vps.sh's EXIT trap always writes /var/lib/site-pipeline/pipeline-result.json. If it's
# missing here, something deleted it after the trap ran — fail loud.
if ! $SSH "test -f /var/lib/site-pipeline/pipeline-result.json" 2>/dev/null; then
  echo "STATUS:BOOTSTRAP_RESULT_INVALID reason=pipeline_result_missing_on_vps"
  exit 1
fi
TMP_RESULT=$(mktemp pipeline/bootstrap-result.json.XXXXXX)
$SSH "sudo cat /var/lib/site-pipeline/pipeline-result.json" > "$TMP_RESULT" \
  || { echo "STATUS:BOOTSTRAP_RESULT_INVALID reason=result_fetch_failed"; exit 1; }
chmod 600 "$TMP_RESULT"
mv "$TMP_RESULT" pipeline/bootstrap-result.json
chmod 600 pipeline/bootstrap-result.json

jq -e '
  .schema_version and .project_name and .site_dir and .site_url and
  .server_ip and .gitea_url and .gitea_user and .tina_admin_password
' pipeline/bootstrap-result.json >/dev/null \
  || { echo "STATUS:BOOTSTRAP_RESULT_INVALID reason=missing_required_fields"; exit 1; }

python3 ~/.config/opencode/astro-static/validate-pipeline.py --phase startup . --pipeline-dir pipeline/ >/dev/null \
  || { echo "STATUS:BOOTSTRAP_RESULT_INVALID reason=schema_validation_failed"; exit 1; }

# --- Step 4: Merge bootstrap result into vps-connection.json ---
# bootstrap-result fields override any pre-existing placeholders in vps-connection.
TMP_VPS=$(mktemp pipeline/vps-connection.json.XXXXXX)
jq -s '.[0] * .[1]' \
  pipeline/vps-connection.json \
  pipeline/bootstrap-result.json > "$TMP_VPS" \
  && mv "$TMP_VPS" pipeline/vps-connection.json
chmod 600 pipeline/vps-connection.json

SITE_DIR=$(jq -r '.site_dir'   pipeline/vps-connection.json)
GITEA_URL=$(jq -r '.gitea_url'  pipeline/vps-connection.json)
GITEA_USER=$(jq -r '.gitea_user' pipeline/vps-connection.json)
GITEA_PASS=$(jq -r '.gitea_pass' pipeline/vps-connection.json)
[ -n "$GITEA_PASS" ] && [ "$GITEA_PASS" != "null" ] \
  || { echo "STATUS:BOOTSTRAP_JOIN_GITEA_AUTH_FAILED reason=missing_local_password"; exit 1; }

# --- Step 5: Final VPS probe (services + paths + caddy parse) ---
  $SSH "
  set -e
  node --version >/dev/null
  caddy version >/dev/null
  systemctl is-active gitea >/dev/null
  test -d $SITE_DIR
  sudo caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1 \
    || { echo 'CADDY_CONFIG_INVALID' >&2; exit 1; }
  " || { echo "STATUS:BOOTSTRAP_JOIN_PROBE_FAILED"; exit 1; }

# --- Step 6: Gitea auth check from control node ---
# Proves the credentials we just merged actually work — anonymous /api/v1/version
# doesn't exercise the credential path, so we hit an authenticated endpoint.
AUTH_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
  -u "$GITEA_USER:$GITEA_PASS" "$GITEA_URL/api/v1/user")
[ "$AUTH_CODE" = "200" ] \
  || { echo "STATUS:BOOTSTRAP_JOIN_GITEA_AUTH_FAILED code=$AUTH_CODE"; exit 1; }

# --- Step 7: Mark pipeline state completed ---
# Shell-generated timestamp via --arg: jq's `now | todate` is not in all jq builds.
NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
if [ -f pipeline/00-pipeline-state.json ]; then
  jq --arg now "$NOW" '.phases["0_bootstrap_launch"].status = "completed" |
      .phases["0_bootstrap_launch"].completed_at = $now |
      .updated_at = $now' \
    pipeline/00-pipeline-state.json > pipeline/00-pipeline-state.json.tmp \
    && mv pipeline/00-pipeline-state.json.tmp pipeline/00-pipeline-state.json
fi

echo "STATUS:BOOTSTRAP_OK"
exit 0
