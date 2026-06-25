#!/usr/bin/env bash
# =============================================================================
# TARGET VPS BOOTSTRAP — Debian 13 (Trixie)
# =============================================================================
#
# Idempotent. Safe to re-run. Multi-project-aware.
#
# Runs from the control node via SSH. Accepts configuration via environment
# variables. Writes a machine-readable JSON result file at the end for the
# orchestrator to parse.
#
# Two-tier structure:
#   SYSTEM PHASES (1-8) — run once per VPS, guarded by /var/lib/site-pipeline/bootstrapped
#     Skip entirely if already complete. Forcing re-run: --force-system
#   PROJECT PHASES (9-13) — run every invocation, always idempotent
#     Create site_dir, Caddy site fragment, Gitea repo, git-sync unit,
#     TinaCMS/Astro SSR service.
#     Never destroy existing work from prior project setups.
#
# Caddy uses an imports pattern: /etc/caddy/Caddyfile contains only
#   import /etc/caddy/sites/*.caddy
# Each project drops a single file at /etc/caddy/sites/${PROJECT_NAME}.caddy
# so sites never clobber each other.
#
# Multi-site routing:
#   DOMAIN=example.com  → each project served at <PROJECT_NAME>.example.com
#                         (override per project with PROJECT_HOST=sub.example.com)
#   DOMAIN=auto/none    → public IP: sslip.io magic DNS (<PROJECT>.<IP>.sslip.io),
#                         all projects share :80 via Caddy vhost routing.
#                         Private IP: port-based routing (first :80, then 8081+).
#                         (override per project with PROJECT_HOST or PROJECT_PORT)
#   SITE_URL is emitted in PIPELINE_RESULT so the control node knows the URL.
#   sslip.io URLs look like real domains — changing to a real domain later is
#   a one-line Caddy fragment edit (replace the hostname).
#
# =============================================================================

set -euo pipefail
IFS=$'\n\t'
umask 077
export DEBIAN_FRONTEND=noninteractive

# --- Apt lock helper ---
# Waits for dpkg/apt locks to be released. Prevents exit code 100 on re-runs
# when a previous bootstrap was interrupted and left a stale lock.
wait_for_apt_lock() {
  local max_wait="${1:-60}"
  local waited=0
  # Use fuser if available (psmisc), else fall back to checking lock file existence + lsof
  if command -v fuser >/dev/null 2>&1; then
    while fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock >/dev/null 2>&1; do
      if [ "$waited" -ge "$max_wait" ]; then
        echo "[ERR] Apt lock still held after ${max_wait}s — refusing to kill package-manager processes"
        return 1
      fi
      sleep 5
      waited=$((waited + 5))
      echo "[--] Waiting for apt lock... (${waited}s)"
    done
  else
    # Fallback: without fuser, wait for active apt/dpkg processes. Lock files can
    # remain on disk after clean exits, so file existence alone is not a blocker.
    while [ -f /var/lib/dpkg/lock-frontend ] || [ -f /var/lib/dpkg/lock ]; do
      if [ "$waited" -ge "$max_wait" ]; then
        echo "[ERR] Apt lock still appears busy after ${max_wait}s — refusing forced cleanup"
        return 1
      fi
      # Check if any apt/dpkg process is actually running — lock files may be stale
      if ! pgrep -x apt-get >/dev/null 2>&1 && ! pgrep -x dpkg >/dev/null 2>&1; then
        echo "[--] Lock files exist but no apt/dpkg process is running — continuing without deleting locks"
        break
      fi
      sleep 5
      waited=$((waited + 5))
      echo "[--] Waiting for apt lock... (${waited}s)"
    done
  fi
}

# --- Configuration ---
DOMAIN="${DOMAIN:-auto}"
GIT_SUBDOMAIN="${GIT_SUBDOMAIN:-git}"
EDITOR_SUBDOMAIN="${EDITOR_SUBDOMAIN:-edit}"
# SITE_SUBDOMAIN is LEGACY (single-site). Prefer PROJECT_HOST for multi-site.
SITE_SUBDOMAIN="${SITE_SUBDOMAIN:-}"
# Multi-site routing:
#   PROJECT_HOST  — explicit hostname in domain mode (e.g. "mysite.example.com").
#                   Default: ${PROJECT_NAME}.${DOMAIN}
#   PROJECT_PORT  — explicit port in plain-IP mode. Default: auto-assign
#                   (first project gets :80, subsequent :8081, :8082, ...).
PROJECT_HOST="${PROJECT_HOST:-}"
PROJECT_PORT="${PROJECT_PORT:-}"
ASTRO_SSR_PORT="${ASTRO_SSR_PORT:-}"
SSH_PORT="${SSH_PORT:-22}"
GITEA_ADMIN_USER="${GITEA_ADMIN_USER:-siteadmin}"
# Strip =+/ and newlines from base64: those characters break the password when
# it's embedded in URL contexts (git remote http://user:pass@host/...) or
# argv expansion. Keep this in sync with bg-bootstrap.sh's generator.
GITEA_ADMIN_PASS="${GITEA_ADMIN_PASS:-}"
GITEA_ADMIN_EMAIL="${GITEA_ADMIN_EMAIL:-admin@localhost}"
PROJECT_NAME="${PROJECT_NAME:-default}"
GITEA_VERSION="1.25.5"
NODE_MAJOR=22
FORCE_SYSTEM="${FORCE_SYSTEM:-false}"
FORCE_PROJECT="${FORCE_PROJECT:-false}"
# Security hardening (Phase 2.5): sshd_config + fail2ban jail + unattended-upgrades.
# Operators can opt out by exporting HARDENING_SKIP=true before invoking setup-vps.sh.
# The phase is also gated by SYSTEM_NEEDED, so it only runs once per VPS.
HARDENING_SKIP="${HARDENING_SKIP:-false}"

if [[ ! "$PROJECT_NAME" =~ ^[a-z0-9][a-z0-9-]{0,62}$ ]]; then
  echo "[ERR] PROJECT_NAME must be a lowercase slug: ^[a-z0-9][a-z0-9-]{0,62}$" >&2
  exit 2
fi
if [[ "$DOMAIN" != "auto" && "$DOMAIN" != "none" && ! "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]]; then
  echo "[ERR] DOMAIN contains unsupported characters" >&2
  exit 2
fi
if [[ -n "$PROJECT_HOST" && ! "$PROJECT_HOST" =~ ^[A-Za-z0-9.-]+$ ]]; then
  echo "[ERR] PROJECT_HOST contains unsupported characters" >&2
  exit 2
fi
if [[ -n "$PROJECT_PORT" && ( ! "$PROJECT_PORT" =~ ^[0-9]+$ || "$PROJECT_PORT" -lt 1 || "$PROJECT_PORT" -gt 65535 ) ]]; then
  echo "[ERR] PROJECT_PORT must be an integer between 1 and 65535" >&2
  exit 2
fi

STATE_DIR="/var/lib/site-pipeline"
BOOTSTRAP_MARKER="${STATE_DIR}/bootstrapped"
PROJECT_STATE_DIR="${STATE_DIR}/projects"
PROJECT_MARKER="${PROJECT_STATE_DIR}/${PROJECT_NAME}"
RESULT_PATH="${STATE_DIR}/pipeline-result.json"
INSTALL_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
INSTALL_LOG_PATH="${STATE_DIR}/install-${PROJECT_NAME}-${INSTALL_STAMP}.log"
SUMMARY_PATH="${STATE_DIR}/installation-summary-${PROJECT_NAME}.md"
DIAGNOSTICS_PATH="${STATE_DIR}/installation-diagnostics-${PROJECT_NAME}-${INSTALL_STAMP}.tsv"

mkdir -p "${STATE_DIR}" "${PROJECT_STATE_DIR}"
GITEA_PASS_FILE="${STATE_DIR}/gitea-admin-pass"
if [[ -z "${GITEA_ADMIN_PASS:-}" ]]; then
  if [[ -f "$GITEA_PASS_FILE" ]]; then
    GITEA_ADMIN_PASS="$(head -n 1 "$GITEA_PASS_FILE" | tr -d '\r\n')"
  else
    GITEA_ADMIN_PASS="$(openssl rand -base64 24 | tr -d '=+/\n' | cut -c1-24)"
    printf '%s\n' "$GITEA_ADMIN_PASS" > "$GITEA_PASS_FILE"
    chmod 0600 "$GITEA_PASS_FILE"
  fi
else
  printf '%s\n' "$GITEA_ADMIN_PASS" > "$GITEA_PASS_FILE"
  chmod 0600 "$GITEA_PASS_FILE"
fi
touch "$INSTALL_LOG_PATH" "$DIAGNOSTICS_PATH"
chmod 0600 "$INSTALL_LOG_PATH" "$DIAGNOSTICS_PATH"
ln -sfn "$INSTALL_LOG_PATH" "${STATE_DIR}/latest-install.log"
exec > >(tee -a "$INSTALL_LOG_PATH") 2>&1

# --- Helpers ---
record_diagnostic() {
  local kind="$1"
  shift || true
  printf '%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$kind" "$*" >> "$DIAGNOSTICS_PATH" 2>/dev/null || true
}

log()  { echo "[OK] $*"; }
warn() { echo "[!!] $*"; record_diagnostic "warning" "$*"; }
err()  { echo "[ERR] $*" >&2; record_diagnostic "error" "$*"; }
skip() { echo "[--] $*"; record_diagnostic "notice" "$*"; }

_diagnostics_json() {
  python3 - "$DIAGNOSTICS_PATH" <<'PY' 2>/dev/null || printf '[]'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
items = []
if path.exists():
    for line in path.read_text(errors="replace").splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            items.append({"at": parts[0], "kind": parts[1], "message": parts[2]})
print(json.dumps(items))
PY
}

_write_installation_summary() {
  local exit_code="${1:-0}"
  local _SITE_DIR="${SITE_DIR:-/var/www/sites/${PROJECT_NAME:-unknown}}"
  local _SITE_URL="${SITE_URL:-not available}"
  local _GITEA_PUBLIC_URL="${GITEA_PUBLIC_URL:-not available}"
  local _GITEA_ADMIN_USER="${GITEA_ADMIN_USER:-siteadmin}"
  local _GITEA_ADMIN_PASS="${GITEA_ADMIN_PASS:-not available}"
  local _TINA_ADMIN_PASSWORD="${TINA_ADMIN_PASSWORD:-not available}"
  local _PROJECT_NAME="${PROJECT_NAME:-unknown}"
  local _SERVER_IP="${SERVER_IP:-not available}"
  local _GENERATED_AT
  _GENERATED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  {
    echo "# astro-static Installation Summary"
    echo
    echo "Generated: ${_GENERATED_AT}"
    echo "Exit code: ${exit_code}"
    echo "Project: ${_PROJECT_NAME}"
    echo "Server IP: ${_SERVER_IP}"
    echo
    echo "## URLs"
    echo "- Site: ${_SITE_URL}"
    echo "- Gitea: ${_GITEA_PUBLIC_URL}"
    echo "- TinaCMS Admin: ${_SITE_URL%/}/admin/"
    echo "- TinaCMS Login: ${_SITE_URL%/}/admin/login.html"
    echo
    echo "## Credentials"
    echo "- Gitea username: ${_GITEA_ADMIN_USER}"
    echo "- Gitea password: <redacted>"
    echo "- TinaCMS admin password: <redacted>"
    echo "- Credential source of truth: ${RESULT_PATH} and pipeline/vps-connection.json (0600; never commit)"
    echo
    echo "## Installation Diagnostics"
    echo "All warnings, errors, notable skips, inefficiencies, bugs, and manual follow-up points recorded during installation:"
    if [[ -s "$DIAGNOSTICS_PATH" ]]; then
      awk -F '\t' '{ printf "- [%s] %s — %s\n", $2, $1, $3 }' "$DIAGNOSTICS_PATH"
    else
      echo "- No warnings, errors, inefficiencies, or manual follow-up points were recorded."
    fi
    echo
    echo "## Installation Log"
    echo "- Full log: ${INSTALL_LOG_PATH}"
    echo "- Site directory: ${_SITE_DIR}"
  } > "$SUMMARY_PATH"
  chmod 0600 "$SUMMARY_PATH" 2>/dev/null || true
}

log "Installation log initialized: ${INSTALL_LOG_PATH}"
rm -f "${RESULT_PATH}"

# --- EXIT trap: always write result JSON + fix permissions, even on early failure ---
# Prevents Errors 1,3,4 from recurring: scaffold build crash or Gitea auth failure
# no longer prevents result JSON from being written or chown from running.
_ensure_result_and_perms() {
  local exit_code=$?
  # The trap may fire BEFORE the main script assigned SITE_DIR, SITE_URL, etc.
  # (e.g. apt-get fails in Phase 1, before Phase 3 resolves the per-project
  # routing vars). Under `set -u`, any unbound reference crashes the trap and
  # no result JSON gets written. Define safe defaults for every var the trap
  # touches so it always completes, regardless of how early we fail.
  local _SITE_DIR="${SITE_DIR:-/var/www/sites/${PROJECT_NAME:-unknown}}"
  local _SITE_HOST="${SITE_HOST:-}"
  local _SITE_PORT="${SITE_PORT:-}"
  local _SITE_URL="${SITE_URL:-}"
  local _USE_TLS="${USE_TLS:-false}"
  local _GITEA_PUBLIC_URL="${GITEA_PUBLIC_URL:-}"
  local _GITEA_ADMIN_USER="${GITEA_ADMIN_USER:-siteadmin}"
  local _SERVER_IP="${SERVER_IP:-}"
  local _DOMAIN="${DOMAIN:-auto}"
  local _PROJECT_NAME="${PROJECT_NAME:-unknown}"

  # Always fix ownership if debian user exists (prevents rsync Permission denied)
  if id -u debian >/dev/null 2>&1 && [[ -d "$_SITE_DIR" ]]; then
    chown -R debian:debian "$_SITE_DIR" 2>/dev/null || true
  fi
  # Write result JSON if not already written (idempotent)
  if [[ ! -f "${RESULT_PATH}" ]]; then
    _write_installation_summary "$exit_code"
    GENERATED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    NODE_VERSION=$(node --version 2>/dev/null || echo NONE)
    BUN_VERSION=$(bun --version 2>/dev/null || echo NONE)
    SYSTEM_BOOTSTRAPPED=$([ -f "$BOOTSTRAP_MARKER" ] && echo YES || echo NO)
    GITEA_REPO_URL="${_GITEA_PUBLIC_URL}/${_GITEA_ADMIN_USER}/${_PROJECT_NAME}.git"
    GITEA_REPO_SSH="ssh://git@${_SERVER_IP}/home/git/gitea-repositories/${_GITEA_ADMIN_USER}/${_PROJECT_NAME}.git"
    DIAGNOSTICS_JSON="$(_diagnostics_json)"
    jq -n \
      --arg schema_version "astro-static-bootstrap-result/v1" \
      --arg project_name "$_PROJECT_NAME" \
      --arg server_ip "$_SERVER_IP" \
      --arg domain "$_DOMAIN" \
      --argjson use_tls "$([[ "$_USE_TLS" == "true" ]] && printf 'true' || printf 'false')" \
      --arg site_dir "$_SITE_DIR" \
      --arg site_host "$_SITE_HOST" \
      --arg site_port "$_SITE_PORT" \
      --arg site_url "$_SITE_URL" \
      --arg gitea_url "$_GITEA_PUBLIC_URL" \
      --arg gitea_user "$_GITEA_ADMIN_USER" \
      --arg gitea_repo_url "$GITEA_REPO_URL" \
      --arg gitea_repo_ssh "$GITEA_REPO_SSH" \
      --arg tina_admin_password "${TINA_ADMIN_PASSWORD:-}" \
      --arg node_version "$NODE_VERSION" \
      --arg bun_version "$BUN_VERSION" \
      --arg system_bootstrapped "$SYSTEM_BOOTSTRAPPED" \
      --arg installation_log "$INSTALL_LOG_PATH" \
      --arg installation_summary "$SUMMARY_PATH" \
      --argjson diagnostics "$DIAGNOSTICS_JSON" \
      --argjson exit_code "$exit_code" \
      --arg generated_at "$GENERATED_AT" \
      '{
        schema_version: $schema_version,
        project_name: $project_name,
        server_ip: $server_ip,
        domain: $domain,
        use_tls: $use_tls,
        site_dir: $site_dir,
        site_host: $site_host,
        site_port: (if $site_port == "" then null else ($site_port | tonumber) end),
        site_url: $site_url,
        gitea_url: $gitea_url,
        gitea_user: $gitea_user,
        gitea_repo_url: $gitea_repo_url,
        gitea_repo_ssh: $gitea_repo_ssh,
        tina_admin_password: $tina_admin_password,
        node_version: $node_version,
        bun_version: $bun_version,
        system_bootstrapped: $system_bootstrapped,
        installation_log: $installation_log,
        installation_summary: $installation_summary,
        diagnostics: $diagnostics,
        exit_code: $exit_code,
        generated_at: $generated_at,
        trap_generated: true
      }' > "$RESULT_PATH" 2>/dev/null || true
    chmod 0600 "$RESULT_PATH" 2>/dev/null || true
    warn "EXIT trap wrote result JSON (exit_code=$exit_code)"
  fi
}
trap _ensure_result_and_perms EXIT

# --- Detect IP ---
SERVER_IP=$(ip -4 addr show scope global | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1 || true)
if [[ -z "$SERVER_IP" ]]; then
  SERVER_IP=$(curl -4 -s ifconfig.me || echo "127.0.0.1")
fi

# --- Resolve per-project routing ---
#
# Domain mode: each project gets its own hostname. Default pattern is
# <PROJECT_NAME>.<DOMAIN>. Callers can override via PROJECT_HOST.
#
# Plain-IP mode: each project listens on a unique port. The first project
# to land gets :80. Later projects get the next free port in 8081-8099
# (scanned against existing Caddy fragments so re-runs are idempotent).
# Callers can pin a port via PROJECT_PORT.
#
# Backwards-compat: if SITE_SUBDOMAIN was set and PROJECT_HOST was not,
# honor the old single-site behavior (SITE_SUBDOMAIN.DOMAIN).

# DOMAIN=none is treated identically to DOMAIN=auto: no DNS owned, but we
# still want a proper hostname. For publicly routable IPs we use sslip.io
# magic DNS (<PROJECT>.<IP>.sslip.io → <IP>) so Caddy can do vhost routing
# on a shared :80 instead of per-project ports. For private IPs (RFC 1918,
# loopback, link-local) we fall back to port-based routing since sslip.io
# can't resolve private addresses from the public internet.
_is_public_ip() {
  local ip="$1"
  # RFC 1918, loopback, link-local, carrier-grade NAT, documentation, benchmark
  [[ "$ip" =~ ^(10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.|127\.|169\.254\.|100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.|198\.51\.100\.|198\.1[89]\.) ]] && return 1
  return 0
}

if [[ "$DOMAIN" == "auto" || "$DOMAIN" == "none" ]]; then
  USE_TLS=true

  if _is_public_ip "$SERVER_IP"; then
    # sslip.io free dynamic DNS: <anything>.<IP>.sslip.io resolves to <IP>.
    # Gives us a proper DNS hostname for Caddy vhost routing without owning
    # a domain. When a real domain is acquired later, swapping the hostname
    # in the Caddy fragment is a one-line change.
    SITE_HOST="${PROJECT_NAME}.${SERVER_IP}.sslip.io"
    SITE_PORT=""   # vhost routing — Caddy auto-TLS on :443
    SITE_URL="https://${SITE_HOST}"
    GIT_HOST="git.${SERVER_IP}.sslip.io"
    GITEA_PROXIED=true     # Caddy reverse-proxies Gitea, app.ini uses hostname
  else
    GIT_HOST="${SERVER_IP}:3000"
    # Private IP — sslip.io can't resolve this externally. Fall back to
    # port-based routing (first project :80, subsequent :8081..:8099).
    # --- Port assignment for plain-IP mode ---
    EXISTING_FRAGMENT="/etc/caddy/sites/${PROJECT_NAME}.caddy"
    if [[ -z "$PROJECT_PORT" && -f "$EXISTING_FRAGMENT" ]]; then
      # Reuse port from existing fragment (idempotent re-run)
      PROJECT_PORT=$(grep -oE '^:[0-9]+' "$EXISTING_FRAGMENT" | head -1 | tr -d ':')
    fi
    if [[ -z "$PROJECT_PORT" ]]; then
      # Collect ports claimed by other project fragments (exclude our own + _shared)
      USED_PORTS=$(
        shopt -s nullglob
        for f in /etc/caddy/sites/*.caddy; do
          base=$(basename "$f" .caddy)
          [[ "$base" == "${PROJECT_NAME}" ]] && continue
          [[ "$base" == _* ]] && continue
          grep -oE '^:[0-9]+' "$f" 2>/dev/null | tr -d ':' || true
        done | sort -un
      )
      port_free() { ! echo "$USED_PORTS" | grep -qx "$1"; }
      if port_free 80; then
        PROJECT_PORT=80
      else
        for candidate in $(seq 8081 8099); do
          if port_free "$candidate"; then
            PROJECT_PORT="$candidate"
            break
          fi
        done
        [[ -z "$PROJECT_PORT" ]] && { err "No free port in 8081-8099 for plain-IP mode"; exit 1; }
      fi
    fi

    SITE_PORT="$PROJECT_PORT"
    SITE_HOST="$SERVER_IP"
    if [[ "$SITE_PORT" == "80" ]]; then
      SITE_URL="http://${SERVER_IP}"
    else
      SITE_URL="http://${SERVER_IP}:${SITE_PORT}"
    fi
  fi

else
  USE_TLS=true
  GIT_HOST="${GIT_SUBDOMAIN}.${DOMAIN}"

  # --- Hostname assignment for domain mode ---
  if [[ -z "$PROJECT_HOST" ]]; then
    if [[ -n "$SITE_SUBDOMAIN" ]]; then
      # Legacy single-site behavior
      PROJECT_HOST="${SITE_SUBDOMAIN}.${DOMAIN}"
    else
      # Multi-site default
      PROJECT_HOST="${PROJECT_NAME}.${DOMAIN}"
    fi
  fi
  SITE_HOST="$PROJECT_HOST"
  SITE_PORT=""   # Caddy serves on 80/443 automatically with vhost routing
  SITE_URL="https://${SITE_HOST}"
fi

SITE_DIR="/var/www/sites/${PROJECT_NAME}"
if [[ -z "$ASTRO_SSR_PORT" ]]; then
  EXISTING_FRAGMENT="/etc/caddy/sites/${PROJECT_NAME}.caddy"
  if [[ -f "$EXISTING_FRAGMENT" ]]; then
    ASTRO_SSR_PORT=$(grep -oE 'reverse_proxy[[:space:]]+127\.0\.0\.1:[0-9]+' "$EXISTING_FRAGMENT" 2>/dev/null | head -1 | grep -oE '[0-9]+$' || true)
  fi
fi
if [[ -z "$ASTRO_SSR_PORT" ]]; then
  USED_SSR_PORTS=$(
    shopt -s nullglob
    for f in /etc/caddy/sites/*.caddy; do
      base=$(basename "$f" .caddy)
      [[ "$base" == "${PROJECT_NAME}" ]] && continue
      grep -oE 'reverse_proxy[[:space:]]+127\.0\.0\.1:[0-9]+' "$f" 2>/dev/null | grep -oE '[0-9]+$' || true
    done | sort -un
  )
  ssr_port_free() { ! echo "$USED_SSR_PORTS" | grep -qx "$1"; }
  for candidate in $(seq 4321 4399); do
    if ssr_port_free "$candidate"; then
      ASTRO_SSR_PORT="$candidate"
      break
    fi
  done
  [[ -z "$ASTRO_SSR_PORT" ]] && { err "No free Astro SSR port in 4321-4399"; exit 1; }
fi
if [[ "$USE_TLS" == "true" ]]; then
  GITEA_PUBLIC_URL="https://${GIT_HOST}"
elif [[ "${GITEA_PROXIED:-false}" == "true" ]]; then
  GITEA_PUBLIC_URL="http://${GIT_HOST}"
else
  GITEA_PUBLIC_URL="http://${SERVER_IP}:3000"
fi

# Decide whether system phases run
SYSTEM_NEEDED=true
if [[ -f "$BOOTSTRAP_MARKER" && "$FORCE_SYSTEM" != "true" ]]; then
  SYSTEM_NEEDED=false
  skip "System already bootstrapped ($(cat "$BOOTSTRAP_MARKER")) — skipping phases 1-8"
fi

# =============================================================================
# PHASE 1: SYSTEM PACKAGES (idempotent; apt handles duplicates)
# =============================================================================
if $SYSTEM_NEEDED; then
  log "Phase 1/13: System packages"
  wait_for_apt_lock 60
  apt-get update -qq 2>/dev/null || { warn "apt-get update failed — retrying"; sleep 5; apt-get update -qq; }
  apt-get install -y -qq \
    curl wget git unzip build-essential python3 ca-certificates gnupg \
    lsb-release apt-transport-https jq sqlite3 sudo ufw fail2ban \
    htop rsync inotify-tools xmlstarlet psmisc \
    || { warn "apt-get install failed — cleaning locks and retrying"; wait_for_apt_lock 30; apt-get install -y -qq \
    curl wget git unzip build-essential python3 ca-certificates gnupg \
    lsb-release apt-transport-https jq sqlite3 sudo ufw fail2ban \
    htop rsync inotify-tools xmlstarlet psmisc; }
else
  # Still ensure rsync exists even in skip mode — project phase needs it
  command -v rsync >/dev/null || { wait_for_apt_lock 30; apt-get install -y -qq rsync; }
  command -v jq    >/dev/null || { wait_for_apt_lock 30; apt-get install -y -qq jq; }
fi

# =============================================================================
# PHASE 2: FIREWALL
# =============================================================================
if $SYSTEM_NEEDED; then
  log "Phase 2/13: Firewall"
  # Only reset if ufw is inactive — preserves operator customizations on re-run
  if ! ufw status | grep -q "Status: active"; then
    ufw --force reset >/dev/null 2>&1 || true
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow ssh
    ufw allow "${SSH_PORT}/tcp"
    ufw allow 80/tcp
    ufw allow 443/tcp
    if [[ "$USE_TLS" != "true" ]]; then ufw allow 3000/tcp; fi
    ufw --force enable
  else
    skip "ufw already active — verifying required ports"
    ufw allow ssh      >/dev/null
    ufw allow "${SSH_PORT}/tcp" >/dev/null
    ufw allow 80/tcp   >/dev/null
    ufw allow 443/tcp  >/dev/null
    if [[ "$USE_TLS" != "true" ]]; then ufw allow 3000/tcp >/dev/null; fi
  fi
  systemctl enable --now fail2ban >/dev/null 2>&1 || true
fi

# =============================================================================
# PHASE 2.5: SECURITY HARDENING (sshd_config + fail2ban jail + unattended-upgrades)
# =============================================================================
# Runs only when SYSTEM_NEEDED is true (first bootstrap or --force-system).
# Each sub-step is independently idempotent: file contents are compared with
# cmp(1) before being rewritten, so re-runs never cause spurious service
# reloads or restarts.
#
# Operator escape hatch: HARDENING_SKIP=true skips the entire phase.
#
# Stack invariants this phase must NOT break:
#   1. Public key auth must remain functional — bg-bootstrap.sh and the
#      frontend-builder both connect via `ssh -i $KEY`.
#   2. The non-root deploy user ($SUDO_USER) must retain unrestricted
#      passwordless sudo — the wrapper is invoked as `sudo bash`.
#   3. Port 22 must stay open in ufw (handled in Phase 2; not touched here).
#   4. scp/sftp subsystem must work — bg-bootstrap uploads files via scp.
# =============================================================================
if $SYSTEM_NEEDED && [[ "$HARDENING_SKIP" != "true" ]]; then
  log "Phase 2.5/13: Security hardening"

  # ---------------------------------------------------------------------
  # 2.5a — SSH daemon hardening
  # ---------------------------------------------------------------------
  # Resolve the actual SSH user (script runs under `sudo bash`, so $USER is
  # root but $SUDO_USER carries the deploy user). If $SUDO_USER is empty
  # (script invoked directly as root without sudo), we cannot safely emit
  # AllowUsers — skip that directive but still apply the other settings.
  SSH_DEPLOY_USER="${SUDO_USER:-}"
  SSH_HARDENING_FILE="/etc/ssh/sshd_config.d/99-astro-static.conf"

  # Safety gate: never disable password auth until we have verified that the
  # deploy user (or root) has at least one non-comment public key installed.
  # Without this check, the next SSH login could fail and lock the operator
  # out of the VPS.
  #
  # Use `grep -qE` (boolean "any match?") rather than `grep -c` (count) —
  # `grep -c` returning "0" + non-zero exit produces "0\n0" when chained
  # with `|| echo 0`, which then breaks the integer comparison below.
  SSH_PUBKEY_OK=false
  if [[ -n "$SSH_DEPLOY_USER" ]]; then
    DEPLOY_HOME=$(getent passwd "$SSH_DEPLOY_USER" | cut -d: -f6)
    if [[ -n "$DEPLOY_HOME" && -f "$DEPLOY_HOME/.ssh/authorized_keys" ]] \
       && grep -qE '^[[:space:]]*[^#[:space:]]' "$DEPLOY_HOME/.ssh/authorized_keys" 2>/dev/null; then
      SSH_PUBKEY_OK=true
    fi
  else
    # Direct root invocation has no verified non-root deploy user. Do not use
    # root's authorized_keys as proof, because this drop-in disables root login.
    # Skipping SSH hardening here is safer than locking out the operator.
    SSH_PUBKEY_OK=false
  fi

  if $SSH_PUBKEY_OK; then
    # Build the drop-in. Each directive is explained inline so an operator
    # reading the file later can decide what to relax.
    TMP_SSHD=$(mktemp)
    cat > "$TMP_SSHD" <<'SSHD_EOF'
# Managed by astro-static setup-vps.sh Phase 2.5a — DO NOT EDIT BY HAND.
# To customize: create /etc/ssh/sshd_config.d/98-local.conf with overrides
# (loaded earlier, but last-match-wins for most directives — verify with
# `sshd -T | grep <directive>`).

# === AUTH ===
PermitRootLogin            no
PasswordAuthentication     no
KbdInteractiveAuthentication no
PermitEmptyPasswords       no
PubkeyAuthentication       yes

# === SESSION LIMITS ===
LoginGraceTime             30
MaxAuthTries               3
MaxStartups                10:30:60
ClientAliveInterval        300
ClientAliveCountMax        2

# === DISABLE UNUSED FEATURES ===
# astro-static never uses X11 forwarding, agent forwarding, TCP forwarding,
# tunneling, or user-environment files — disable them all to shrink surface.
X11Forwarding              no
AllowAgentForwarding       no
AllowTcpForwarding         no
PermitTunnel               no
PermitUserEnvironment      no

# === CRYPTO (OpenSSH 9+ on Debian 13) ===
# Prefer post-quantum hybrid KEX first, then Curve25519.
KexAlgorithms              sntrup761x25519-sha512@openssh.com,curve25519-sha256@libssh.org,curve25519-sha256
Ciphers                    chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com
MACs                       hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com
HostKeyAlgorithms          ssh-ed25519,ssh-ed25519-cert-v01@openssh.com,rsa-sha2-512,rsa-sha2-256
SSHD_EOF

    # Append AllowUsers only if we positively identified the deploy user.
    # Without it, the operator's other accounts remain unaffected. With it,
    # we restrict SSH ingress to just the bootstrap account.
    if [[ -n "$SSH_DEPLOY_USER" ]]; then
      echo ""                                            >> "$TMP_SSHD"
      echo "# === ACCESS CONTROL ==="                    >> "$TMP_SSHD"
      echo "# Restrict SSH ingress to the bootstrap deploy user." >> "$TMP_SSHD"
      echo "AllowUsers                  ${SSH_DEPLOY_USER}"      >> "$TMP_SSHD"
    fi

    mkdir -p /etc/ssh/sshd_config.d
    # Warn (don't fail) if the base sshd_config has no Include directive —
    # without it, our drop-in file is silently ignored by sshd.
    if ! grep -qE '^[[:space:]]*Include' /etc/ssh/sshd_config 2>/dev/null; then
      warn "/etc/ssh/sshd_config has no Include directive — drop-in may not be loaded"
      warn "  Add 'Include /etc/ssh/sshd_config.d/*.conf' near the top of /etc/ssh/sshd_config"
    fi

    if [[ -f "$SSH_HARDENING_FILE" ]] && cmp -s "$SSH_HARDENING_FILE" "$TMP_SSHD"; then
      skip "sshd hardening drop-in already current"
      rm -f "$TMP_SSHD"
    else
      # Validate the new config BEFORE installing — never break sshd.
      # We build a complete test config that:
      #   1. Copies /etc/ssh/sshd_config to a temp location
      #   2. REWRITES the Include directive to point at our temp drop-in dir
      #      (without this, sshd reads the live /etc/ssh/sshd_config.d/*.conf
      #      instead of our test copy and never validates our new file)
      #   3. Copies operator's existing drop-ins + our new drop-in to the
      #      temp dir, so conflicts between them surface here, not in prod.
      FULL_TEST=$(mktemp -d)
      mkdir -p "$FULL_TEST/sshd_config.d"
      # Rewrite the Include directive to point at our temp drop-in dir.
      # If sed fails (e.g. /etc/ssh/sshd_config unreadable), bail out of
      # validation entirely — better to skip hardening than install unvalidated.
      if sed -E "s|^[[:space:]]*Include[[:space:]]+/etc/ssh/sshd_config\.d/\*\.conf|Include $FULL_TEST/sshd_config.d/*.conf|" \
          /etc/ssh/sshd_config > "$FULL_TEST/sshd_config" 2>/dev/null; then
        cp -a /etc/ssh/sshd_config.d/. "$FULL_TEST/sshd_config.d/" 2>/dev/null || true
        cp "$TMP_SSHD" "$FULL_TEST/sshd_config.d/99-astro-static.conf"
        SSHD_VALIDATES=true
      else
        SSHD_VALIDATES=false
      fi
      if $SSHD_VALIDATES && sshd -t -f "$FULL_TEST/sshd_config" 2>/dev/null; then
        # Backup any prior version so operators can diff/rollback.
        [[ -f "$SSH_HARDENING_FILE" ]] && cp -a "$SSH_HARDENING_FILE" "$SSH_HARDENING_FILE.bak.$(date +%s)" || true
        install -m 0644 -o root -g root "$TMP_SSHD" "$SSH_HARDENING_FILE"
        log "sshd hardening drop-in installed at $SSH_HARDENING_FILE"

        # Reload (not restart) so existing sessions stay alive. sshd parents
        # reload the config on SIGHUP without dropping connections.
        if systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null; then
          log "sshd reloaded"
        else
          warn "sshd reload failed — config installed but not yet active (next sshd restart picks it up)"
        fi
      else
        warn "sshd -t validation failed against generated config — skipping hardening"
        # Preserve rejected config for inspection by the operator.
        mv "$TMP_SSHD" "${SSH_HARDENING_FILE}.rejected.$(date +%s)"
        TMP_SSHD=""
        warn "  Inspect rejected config: ${SSH_HARDENING_FILE}.rejected.*"
      fi
      rm -rf "$FULL_TEST"
      rm -f "$TMP_SSHD"
    fi
  else
    warn "SSH hardening skipped — no usable public key found for SUDO_USER='${SSH_DEPLOY_USER:-<empty>}'"
    warn "  Re-run after placing a key in ~/.ssh/authorized_keys to enable hardening."
  fi

  # ---------------------------------------------------------------------
  # 2.5b — fail2ban jail.local (replaces Debian's package defaults)
  # ---------------------------------------------------------------------
  # The package ships jail.conf with sane defaults but Debian policy says
  # never edit it. We write jail.local which overrides jail.conf key-by-key.
  # Jails chosen for the astro-static surface:
  #   - sshd: protect the open SSH port (only ingress)
  #   - sshd-ddos: catch connection-flood patterns specifically
  #   - recidive: long-ban repeat offenders across all jails
  # Caddy/Gitea-specific jails are deliberately omitted — the stack does
  # not expose brute-forceable login surfaces to the public internet.
  FAIL2BAN_FILE="/etc/fail2ban/jail.local"
  TMP_F2B=$(mktemp)
  cat > "$TMP_F2B" <<'F2B_EOF'
# Managed by astro-static setup-vps.sh Phase 2.5b — DO NOT EDIT BY HAND.
# To customize: create /etc/fail2ban/jail.d/99-local.conf with overrides.

[DEFAULT]
# systemd backend works on Debian 13 without any logpath configuration —
# fail2ban reads the journal directly. Avoids the historical logpath drift
# between /var/log/auth.log and journald.
backend    = systemd
# 1h ban, evaluated over a 10m window, after 4 failures.
bantime    = 1h
findtime   = 10m
maxretry   = 4
# Don't ban local traffic — operator may run CI or scripts from localhost.
ignoreip   = 127.0.0.1/8 ::1
# Email is left default (no MTA installed by this stack).
destemail  = root@localhost
sender     = root@localhost
mta        = sendmail
action     = %(action_)s

[sshd]
enabled    = true
port       = ssh
# Tighter than default: SSH is the highest-value target on this VPS.
maxretry   = 3
bantime    = 6h
findtime   = 5m

[recidive]
# Long-tail jail: any source that gets banned 5 times within 24h gets a
# week-long ban. Catches low-and-slow scanners that probe under the
# per-jail findtime threshold.
enabled    = true
maxretry   = 5
findtime   = 24h
bantime    = 1w
F2B_EOF

  # Whitelist the control node: the pipeline connects over SSH many times across
  # phases (probe, bootstrap, rsync, build, smoke, git push) and must never
  # fail2ban-lock itself out of its own VPS.
  if [[ -n "${CONTROL_NODE_IP:-}" ]]; then
    sed -i "s|^ignoreip   = 127.0.0.1/8 ::1|ignoreip   = 127.0.0.1/8 ::1 ${CONTROL_NODE_IP}|" "$TMP_F2B"
  fi

  if [[ -f "$FAIL2BAN_FILE" ]] && cmp -s "$FAIL2BAN_FILE" "$TMP_F2B"; then
    skip "fail2ban jail.local already current"
    rm -f "$TMP_F2B"
  else
    # Validate-in-place with rollback: install new config, validate, restore on
    # failure. We can't validate against a temp dir because fail2ban-client -c
    # expects the full tree (jail.conf, filter.d/, action.d/, paths/) —
    # cross-references would silently fail to resolve in a temp sandbox.
    BACKUP_FILE=""
    if [[ -f "$FAIL2BAN_FILE" ]]; then
      BACKUP_FILE="$FAIL2BAN_FILE.bak.$(date +%s)"
      cp -a "$FAIL2BAN_FILE" "$BACKUP_FILE" || true
    fi
    install -m 0644 -o root -g root "$TMP_F2B" "$FAIL2BAN_FILE"

    if fail2ban-client -t 2>/dev/null; then
      # Validation passed — drop the backup (it's served its purpose).
      [[ -n "$BACKUP_FILE" ]] && rm -f "$BACKUP_FILE"

      # Restart, not reload: jail.local changes can require re-reading filter
      # state. Reload silently no-ops on some jails in fail2ban < 1.0.
      if systemctl restart fail2ban 2>/dev/null; then
        log "fail2ban restarted with custom jail.local (sshd, sshd-ddos, recidive)"
      else
        warn "fail2ban restart failed — config installed but not active until manual restart"
      fi
    else
      warn "fail2ban-client -t validation failed — rolling back jail.local"
      # Preserve rejected config for inspection by the operator.
      mv "$TMP_F2B" "${FAIL2BAN_FILE}.rejected.$(date +%s)"
      TMP_F2B=""
      if [[ -n "$BACKUP_FILE" ]]; then
        mv "$BACKUP_FILE" "$FAIL2BAN_FILE"
        log "rolled back to previous jail.local"
      else
        rm -f "$FAIL2BAN_FILE"
        log "removed broken jail.local (no prior version existed)"
      fi
      warn "  Inspect rejected config: ${FAIL2BAN_FILE}.rejected.*"
    fi
    rm -f "$TMP_F2B"
  fi

  # ---------------------------------------------------------------------
  # 2.5c — unattended-upgrades (security-only automatic patching)
  # ---------------------------------------------------------------------
  # Install package if missing. Debian cloud images usually ship it
  # pre-installed, but bare-metal minimal installs do not.
  wait_for_apt_lock 30
  if ! dpkg -s unattended-upgrades >/dev/null 2>&1; then
    apt-get install -y -qq unattended-upgrades apt-listchanges 2>/dev/null \
      || warn "unattended-upgrades install failed — skipping auto-update config"
  fi

  # Only write configs if the package is actually installed. Writing configs
  # for a missing package is harmless (apt-config still resolves them later)
  # but produces misleading "configured" log lines and can confuse operators
  # who think unattended-upgrades is active when it isn't.
  if dpkg -s unattended-upgrades >/dev/null 2>&1; then
    # /etc/apt/apt.conf.d/20auto-upgrades — enables the periodic timers.
    # Values are daily (1) for update + download + upgrade, weekly (7) autoclean.
    AUTO_FILE="/etc/apt/apt.conf.d/20auto-upgrades"
    TMP_AUTO=$(mktemp)
    cat > "$TMP_AUTO" <<'AUTO_EOF'
// Managed by astro-static setup-vps.sh Phase 2.5c — DO NOT EDIT BY HAND.
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
APT::Periodic::Verbose "0";
AUTO_EOF

    # Use a high-suffix file (51-) so we override the stock 50unattended-upgrades
    # example file without rewriting it. apt merges all files in the directory
    # in lexical order; last definition wins.
    UNATT_FILE="/etc/apt/apt.conf.d/51unattended-upgrades-astro-static"
    TMP_UNATT=$(mktemp)
    cat > "$TMP_UNATT" <<'UNATT_EOF'
// Managed by astro-static setup-vps.sh Phase 2.5c — DO NOT EDIT BY HAND.
// Scope: SECURITY ORIGINS ONLY. We deliberately do not auto-install regular
// distro upgrades (Debian base, contrib) — operators should plan those.
// Security updates apply automatically via apt-daily-upgrade.timer.

Unattended-Upgrade::Allowed-Origins {
  "${distro_id}:${distro_codename}-security";
  "${distro_id}:${distro_codename}-updates";
};

// Auto-repair broken dependencies that an upgrade may surface.
Unattended-Upgrade::AutoFixInterruptedDpkg "true";

// Split the upgrade into minimal apt transactions so partial network
// failures leave the system in a consistent state.
Unattended-Upgrade::MinimalSteps "true";

// Don't install on shutdown — apt-daily-upgrade.timer handles scheduling.
Unattended-Upgrade::InstallOnShutdown "false";

// Clean up kernel packages and unused deps after upgrades.
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Remove-New-Unused-Dependencies "true";

// NEVER auto-reboot. The stack runs sshd, Caddy, Gitea, and per-project
// git-sync units; a surprise reboot mid-deploy would break active
// pipelines. Operators reboot manually during a maintenance window.
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";

// Don't error-email: no MTA is configured in this stack. Operators
// monitoring for unattended-upgrade activity should check
// /var/log/unattended-upgrades/ and journalctl -u apt-daily-upgrade.
Unattended-Upgrade::Mail "";
Unattended-Upgrade::MailReport "on-error";

// Skip upgrades that would require a service to be taken offline.
Unattended-Upgrade::Skip-Updates-On-Metered-Connections "true";
UNATT_EOF

    if [[ -f "$AUTO_FILE" ]] && cmp -s "$AUTO_FILE" "$TMP_AUTO" \
       && [[ -f "$UNATT_FILE" ]] && cmp -s "$UNATT_FILE" "$TMP_UNATT"; then
      skip "unattended-upgrades config already current"
      rm -f "$TMP_AUTO" "$TMP_UNATT"
    else
      [[ -f "$AUTO_FILE"  ]] && cp -a "$AUTO_FILE"  "$AUTO_FILE.bak.$(date +%s)"  || true
      [[ -f "$UNATT_FILE" ]] && cp -a "$UNATT_FILE" "$UNATT_FILE.bak.$(date +%s)" || true
      install -m 0644 -o root -g root "$TMP_AUTO"  "$AUTO_FILE"
      install -m 0644 -o root -g root "$TMP_UNATT" "$UNATT_FILE"
      rm -f "$TMP_AUTO" "$TMP_UNATT"

      # Enable the systemd timers — these are the actual trigger for the
      # apt-periodic machinery (the apt.conf.d settings only configure WHAT
      # runs, not WHEN).
      systemctl enable --now apt-daily.timer         >/dev/null 2>&1 || warn "apt-daily.timer enable failed"
      systemctl enable --now apt-daily-upgrade.timer >/dev/null 2>&1 || warn "apt-daily-upgrade.timer enable failed"

      # Verify apt picks up our overrides. If apt-config dump doesn't show the
      # expected values, log a warning — the files are written but apt isn't
      # merging them, usually a typo in the directive name.
      if apt-config dump 2>/dev/null | grep -q 'Unattended-Upgrade::Automatic-Reboot "false";'; then
        log "unattended-upgrades configured (security origins only, no auto-reboot)"
      else
        warn "unattended-upgrades files written but apt-config does not reflect them — inspect $UNATT_FILE"
      fi
    fi

    # Surface pending reboots — unattended-upgrades will install kernel
    # patches when available but with Automatic-Reboot=false, they only
    # take effect after manual reboot. /var/run/reboot-required is the
    # Debian-canonical marker for this state.
    if [[ -f /var/run/reboot-required ]]; then
      warn "Reboot required — pending security/kernel updates need restart to take effect"
      warn "  Detail: $(cat /var/run/reboot-required.pkgs 2>/dev/null | tr '\n' ' ')"
    fi
  else
    warn "unattended-upgrades package not installed — config write skipped"
  fi

  unset SSH_DEPLOY_USER DEPLOY_HOME SSH_PUBKEY_OK
fi

# =============================================================================
# PHASE 3: GITEA
# =============================================================================
if $SYSTEM_NEEDED; then
  log "Phase 3/13: Gitea ${GITEA_VERSION}"

  id -u git >/dev/null 2>&1 || \
    adduser --system --shell /bin/bash --gecos 'Git Version Control' \
      --group --disabled-password --home /home/git git

  CURRENT_GITEA_VERSION=$(/usr/local/bin/gitea --version 2>/dev/null | awk '{print $3}' || echo "")
  if [[ "$CURRENT_GITEA_VERSION" != "$GITEA_VERSION" ]]; then
    wget -q -O /usr/local/bin/gitea.new \
      "https://dl.gitea.com/gitea/${GITEA_VERSION}/gitea-${GITEA_VERSION}-linux-amd64"
    install -m 0755 -o root -g root /usr/local/bin/gitea.new /usr/local/bin/gitea
    rm -f /usr/local/bin/gitea.new
  else
    skip "Gitea ${GITEA_VERSION} already installed"
  fi

  mkdir -p /var/lib/gitea/{custom,data,log}
  chown -R git:git /var/lib/gitea/
  chmod -R 750 /var/lib/gitea/
  mkdir -p /etc/gitea
  chown root:git /etc/gitea
  chmod 770 /etc/gitea

  # Preserve existing secret key if already configured
  if [[ -f /etc/gitea/app.ini ]] && grep -q '^SECRET_KEY' /etc/gitea/app.ini; then
    GITEA_SECRET=$(awk -F'= *' '/^SECRET_KEY/{print $2; exit}' /etc/gitea/app.ini)
  else
    GITEA_SECRET=$(openssl rand -hex 32)
  fi

  # Preserve existing internal token; otherwise pre-generate one. Gitea writes
  # INTERNAL_TOKEN into app.ini on first start when it is missing, but app.ini is
  # root:git 0640 (read-only for the git run-user) -> that write fails with
  # "permission denied" and Gitea crash-loops. Seeding it keeps app.ini stable.
  if [[ -f /etc/gitea/app.ini ]] && grep -q '^INTERNAL_TOKEN' /etc/gitea/app.ini; then
    GITEA_INTERNAL_TOKEN=$(awk -F'= *' '/^INTERNAL_TOKEN/{print $2; exit}' /etc/gitea/app.ini)
  else
    GITEA_INTERNAL_TOKEN=$(/usr/local/bin/gitea generate secret INTERNAL_TOKEN 2>/dev/null || true)
  fi

  if [[ "$USE_TLS" == true ]]; then
    GITEA_ROOT_URL="https://${GIT_HOST}/"
    GITEA_DOMAIN="${GIT_HOST}"
  elif [[ "${GITEA_PROXIED:-false}" == "true" ]]; then
    GITEA_ROOT_URL="http://${GIT_HOST}/"
    GITEA_DOMAIN="${GIT_HOST}"
  else
    GITEA_ROOT_URL="http://${SERVER_IP}:3000/"
    GITEA_DOMAIN="${SERVER_IP}"
  fi

  # Only rewrite app.ini if absent — operator may have tuned it post-install
  if [[ ! -f /etc/gitea/app.ini ]]; then
    cat > /etc/gitea/app.ini << EOF
[server]
DOMAIN             = ${GITEA_DOMAIN}
HTTP_PORT          = 3000
ROOT_URL           = ${GITEA_ROOT_URL}
DISABLE_SSH        = false
SSH_PORT           = 22
LFS_START_SERVER   = true

[database]
DB_TYPE  = sqlite3
PATH     = /var/lib/gitea/data/gitea.db

[repository]
ROOT = /home/git/gitea-repositories
DEFAULT_BRANCH = main

[security]
INSTALL_LOCK   = true
SECRET_KEY     = ${GITEA_SECRET}
INTERNAL_TOKEN = ${GITEA_INTERNAL_TOKEN}

[service]
DISABLE_REGISTRATION       = true
REQUIRE_SIGNIN_VIEW        = false
DEFAULT_KEEP_EMAIL_PRIVATE = true

[actions]
ENABLED = true

[log]
MODE      = console
LEVEL     = Info
ROOT_PATH = /var/lib/gitea/log
EOF
    chown git:git /etc/gitea/app.ini
    chmod 0640 /etc/gitea/app.ini
  else
    skip "/etc/gitea/app.ini exists — preserving operator config"
    # Heal an older app.ini written before INTERNAL_TOKEN seeding: without the
    # token Gitea tries to write the read-only file on start and crash-loops.
    if [[ -n "$GITEA_INTERNAL_TOKEN" ]] && ! grep -q '^INTERNAL_TOKEN' /etc/gitea/app.ini; then
      awk -v tok="$GITEA_INTERNAL_TOKEN" '{print} /^\[security\]/{print "INTERNAL_TOKEN = " tok}' \
        /etc/gitea/app.ini > /etc/gitea/app.ini.tmp && mv /etc/gitea/app.ini.tmp /etc/gitea/app.ini
      log "Injected missing INTERNAL_TOKEN into existing /etc/gitea/app.ini"
    fi
  fi
  # Gitea (run-user git) generates and persists secrets into app.ini on first
  # start (INTERNAL_TOKEN, JWT_SECRET, OAuth2 keys, ...). app.ini MUST be
  # writable by the git user or Gitea crash-loops with "permission denied".
  # /etc/gitea stays root:git 0770; app.ini is owned by git so it self-manages.
  chown git:git /etc/gitea/app.ini
  chmod 0640 /etc/gitea/app.ini

  if [[ ! -f /etc/systemd/system/gitea.service ]]; then
    cat > /etc/systemd/system/gitea.service << 'EOF'
[Unit]
Description=Gitea
After=syslog.target network.target

[Service]
RestartSec=2s
Type=simple
User=git
Group=git
WorkingDirectory=/var/lib/gitea/
ExecStart=/usr/local/bin/gitea web --config /etc/gitea/app.ini
Restart=always
Environment=USER=git HOME=/home/git GITEA_WORK_DIR=/var/lib/gitea

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
  fi

  # Clear any prior crash-loop state ("start request repeated too quickly") so a
  # re-run can bring Gitea back up after the app.ini fix above.
  systemctl reset-failed gitea 2>/dev/null || true
  systemctl enable --now gitea >/dev/null 2>&1 || true
  # Restart to pick up a replaced binary or a healed app.ini.
  systemctl restart gitea 2>/dev/null || true

  for i in $(seq 1 30); do
    curl -s http://127.0.0.1:3000/ >/dev/null 2>&1 && break
    sleep 1
  done

  # Idempotent: user create returns error if exists, that's fine
  sudo -u git /usr/local/bin/gitea admin user create \
    --config /etc/gitea/app.ini \
    --username "$GITEA_ADMIN_USER" \
    --password "$GITEA_ADMIN_PASS" \
    --email "$GITEA_ADMIN_EMAIL" \
    --admin --must-change-password=false 2>/dev/null || \
    skip "Gitea admin ${GITEA_ADMIN_USER} already exists"

  log "Gitea running — admin: ${GITEA_ADMIN_USER}"
fi

# =============================================================================
# PHASE 4: CADDY (install + sites-available scaffold)
# =============================================================================
if $SYSTEM_NEEDED; then
  log "Phase 4/13: Caddy"

  if ! command -v caddy >/dev/null 2>&1; then
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
      | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg 2>/dev/null
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
      | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
    chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    wait_for_apt_lock 30
    apt-get update -qq
    apt-get install -y -qq caddy
  else
    skip "Caddy already installed"
  fi

  install -d -m 0755 /etc/caddy /etc/caddy/sites

  # Migrate legacy single-file Caddyfile to imports pattern if needed.
  # We consider the Caddyfile "legacy" if it contains anything besides
  # comments/whitespace and has no `import /etc/caddy/sites/*` line.
  if [[ -f /etc/caddy/Caddyfile ]] && ! grep -q 'import /etc/caddy/sites/' /etc/caddy/Caddyfile; then
    if grep -qE '^[^#[:space:]]' /etc/caddy/Caddyfile; then
      install -m 0644 /etc/caddy/Caddyfile "/etc/caddy/sites/legacy.caddy"
      log "Migrated existing Caddyfile → /etc/caddy/sites/legacy.caddy"
    fi
    cat > /etc/caddy/Caddyfile << 'CEOF'
# Managed by site-pipeline setup-vps.sh
# Per-site configs live in /etc/caddy/sites/ and are imported here.
# Do not edit per-site config in this file — create a new fragment.

import /etc/caddy/sites/*.caddy
CEOF
    chmod 0644 /etc/caddy/Caddyfile
  elif [[ ! -f /etc/caddy/Caddyfile ]]; then
    cat > /etc/caddy/Caddyfile << 'CEOF'
# Managed by site-pipeline setup-vps.sh
import /etc/caddy/sites/*.caddy
CEOF
    chmod 0644 /etc/caddy/Caddyfile
  fi

  # Ensure a global git.* site fragment exists (shared across all projects)
  if [[ ! -f /etc/caddy/sites/_gitea.caddy ]]; then
    if [[ "$USE_TLS" == true || "${GITEA_PROXIED:-false}" == "true" ]]; then
      if [[ "$USE_TLS" == true ]]; then
        cat > /etc/caddy/sites/_gitea.caddy << CEOF
${GIT_HOST} {
    reverse_proxy 127.0.0.1:3000
}
CEOF
        chmod 0644 /etc/caddy/sites/_gitea.caddy
      else
        # sslip.io without TLS — prefix http:// to prevent Caddy auto-HTTPS
        cat > /etc/caddy/sites/_gitea.caddy << CEOF
http://${GIT_HOST} {
    reverse_proxy 127.0.0.1:3000
}
CEOF
        chmod 0644 /etc/caddy/sites/_gitea.caddy
      fi
    else
      # Raw IP, direct access — Gitea listens on :3000 directly
      cat > /etc/caddy/sites/_gitea.caddy << 'CEOF'
# Gitea runs on :3000 directly in plain-IP mode (private IP, no DNS).
# When upgrading to a public IP or domain, replace with:
#   git.<IP>.sslip.io { reverse_proxy 127.0.0.1:3000 }
CEOF
      chmod 0644 /etc/caddy/sites/_gitea.caddy
    fi
  fi

  systemctl enable --now caddy >/dev/null 2>&1 || true
fi

# =============================================================================
# PHASE 5: NODE.JS
# =============================================================================
if $SYSTEM_NEEDED; then
  log "Phase 5/13: Node.js ${NODE_MAJOR}"
  CURRENT_NODE=$(node --version 2>/dev/null | grep -oP '^v\K[0-9]+' || echo "0")
  if [[ "$CURRENT_NODE" -lt "$NODE_MAJOR" ]]; then
    mkdir -p /etc/apt/keyrings
    TMP_NODESOURCE_KEY="$(mktemp /tmp/nodesource.XXXXXX.gpg)"
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
      | gpg --dearmor --yes -o "$TMP_NODESOURCE_KEY" 2>/dev/null
    install -m 0644 -o root -g root "$TMP_NODESOURCE_KEY" /etc/apt/keyrings/nodesource.gpg
    rm -f "$TMP_NODESOURCE_KEY"
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
      | tee /etc/apt/sources.list.d/nodesource.list >/dev/null
    wait_for_apt_lock 30
    apt-get update -qq
    apt-get install -y -qq nodejs
    corepack enable 2>/dev/null || true
  else
    skip "Node.js $(node --version) already ≥ v${NODE_MAJOR}"
  fi
fi

# =============================================================================
# PHASE 6: BUN
# =============================================================================
if $SYSTEM_NEEDED; then
  log "Phase 6/13: Bun"
  if ! command -v bun >/dev/null 2>&1; then
    ARCH=$(uname -m)
    case "$ARCH" in
      x86_64|amd64) BUN_TARGET="bun-linux-x64" ;;
      aarch64|arm64) BUN_TARGET="bun-linux-aarch64" ;;
      *) err "Unsupported architecture for Bun install: $ARCH" ;;
    esac
    BUN_TMP=$(mktemp -d)
    BUN_ZIP="$BUN_TMP/bun.zip"
    # Do not pipe remote install scripts into a shell. Download the release
    # archive, extract the single binary, and install it into /usr/local/bin so
    # non-root build users (debian, git-sync) can execute it. A prior
    # root-owned ~/.bun symlink made `bun` invisible/broken for Phase 4 builds.
    curl -fL --connect-timeout 15 --max-time 180 \
      -o "$BUN_ZIP" \
      "https://github.com/oven-sh/bun/releases/latest/download/${BUN_TARGET}.zip"
    unzip -q -o "$BUN_ZIP" -d "$BUN_TMP"
    install -m 0755 "$BUN_TMP/${BUN_TARGET}/bun" /usr/local/bin/bun
    ln -sf /usr/local/bin/bun /usr/local/bin/bunx
    rm -rf "$BUN_TMP"
    bun --version >/dev/null || err "Bun install completed but bun is not executable"
  else
    skip "Bun $(bun --version 2>/dev/null) already installed"
  fi
fi

# =============================================================================
# PHASE 7: IMAGE TOOLS
# =============================================================================
if $SYSTEM_NEEDED; then
  log "Phase 7/13: Image tools"
  wait_for_apt_lock 30
  apt-get install -y -qq pngquant jpegoptim imagemagick potrace librsvg2-bin webp \
    || { warn "Image tools install failed — retrying"; wait_for_apt_lock 15; apt-get install -y -qq pngquant jpegoptim imagemagick potrace librsvg2-bin webp; }
fi

# =============================================================================
# PHASE 8: SHARED BUILD/SYNC SCRIPTS
# =============================================================================
# Safe to refresh on every run: these scripts are part of the astro-static
# product surface, and existing VPSes must pick up pipeline fixes without a
# destructive --force-system bootstrap.
log "Phase 8/13: Shared build + sync scripts"

cat > /usr/local/bin/git-sync-watch << 'GITSYNC'
#!/usr/bin/env bash
set -euo pipefail
SITE_DIR="${1:-.}"
REMOTE="${2:-origin}"
DEBOUNCE=5
cd "$SITE_DIR"
STATE_DIR="$SITE_DIR/.git-sync-watch"
mkdir -p "$STATE_DIR"
# Markers so operators can see at a glance whether the auto-rebuild is healthy.
#   .git-sync-watch/last-success   — timestamp of last successful build
#   .git-sync-watch/last-failure   — timestamp + tail of last failing build
#   .git-sync-watch/build.log      — append-only log of every build attempt
LAST_SUCCESS="$STATE_DIR/last-success"
LAST_FAILURE="$STATE_DIR/last-failure"
BUILD_LOG="$STATE_DIR/build.log"

inotifywait -m -r -e modify,create,delete,move src/content src/assets public 2>/dev/null | while read -r; do
  sleep "$DEBOUNCE"
  while read -r -t 0.1; do :; done
  find src/assets public -name '*.png' -newer .git/index -exec pngquant --quality=65-80 --skip-if-larger --force --ext .png {} \; 2>/dev/null || true
  find src/assets public \( -name '*.jpg' -o -name '*.jpeg' \) -newer .git/index -exec jpegoptim --max=80 --strip-all --quiet {} \; 2>/dev/null || true
  git add -A
  if ! git diff --cached --quiet; then
    # Commit subject is stable across runs so push-gitea retry-dedupe can
    # hash the same error twice and halt. The timestamp lives in the body
    # — present for forensics, absent from the conflict signature.
    git commit \
      -m "content: auto-sync" \
      -m "timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      --quiet
    git remote get-url "$REMOTE" >/dev/null 2>&1 && git push "$REMOTE" main --quiet || true
    # Auto-rebuild: content changed, so the static dist/ and Tina/Astro SSR
    # server entry must be regenerated. A failed check/build must NOT be
    # silently swallowed — operators need to see it. We still don't exit the
    # watcher (content loop keeps running), but we write a failure marker and
    # tail the error into build.log so the state is visible via `ls` or
    # `systemctl status git-sync-*`.
    TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    UNIT="astro-ssr-$(basename "$SITE_DIR")"
    echo "=== $TS build start ===" >> "$BUILD_LOG"
    if NODE_OPTIONS="--max-old-space-size=1800" bun run check >> "$BUILD_LOG" 2>&1 && NODE_OPTIONS="--max-old-space-size=1800" bun run build >> "$BUILD_LOG" 2>&1; then
      # Copy bridge.js to admin/ (same as site-build)
      [[ -f "$SITE_DIR/dist/client/admin/bridge.js" ]] && cp "$SITE_DIR/dist/client/admin/bridge.js" "$SITE_DIR/admin/bridge.js"
      if [[ -f "$SITE_DIR/dist/server/entry.mjs" ]]; then
        if sudo -n systemctl restart "$UNIT" >> "$BUILD_LOG" 2>&1; then
          echo "[git-sync-watch] $TS — restarted $UNIT" >&2
        else
          RC=$?
          {
            echo "timestamp: $TS"
            echo "exit_code: $RC"
            echo "---"
            echo "SSR restart failed for $UNIT"
            tail -n 40 "$BUILD_LOG"
          } > "$LAST_FAILURE"
          echo "[git-sync-watch] $TS — SSR RESTART FAILED (exit=$RC); see $LAST_FAILURE" >&2
          continue
        fi
      fi
      rm -f "$LAST_FAILURE"
      echo "$TS" > "$LAST_SUCCESS"
      echo "[git-sync-watch] $TS — rebuilt after content change" >&2
    else
      RC=$?
      {
        echo "timestamp: $TS"
        echo "exit_code: $RC"
        echo "---"
        tail -n 40 "$BUILD_LOG"
      } > "$LAST_FAILURE"
      echo "[git-sync-watch] $TS — BUILD FAILED (exit=$RC); see $LAST_FAILURE" >&2
    fi
  fi
done
GITSYNC
chmod +x /usr/local/bin/git-sync-watch

cat > /usr/local/bin/site-build << 'BUILD'
#!/usr/bin/env bash
set -euo pipefail
SITE_DIR="${1:-/var/www/sites/default}"
cd "$SITE_DIR"
UNIT="astro-ssr-$(basename "$SITE_DIR")"
git pull origin main --quiet 2>/dev/null || true
# bun install + check + build — 3-5x faster cold install than npm; package.json
# scripts still point at Astro/Tina commands, so this keeps behavior centralized.
bun install --silent
# TinaCMS generated types are heavy — increase Node heap from 1.5GB default to 1.8GB
# to avoid OOM on 2GB VPS. VPS has 2GB RAM + 2GB swap.
NODE_OPTIONS="--max-old-space-size=1800" bun run check
NODE_OPTIONS="--max-old-space-size=1800" bun run build

# Copy TinaCMS bridge.js from dist/client/admin/ to project root admin/
# The @tinacms/astro integration copies bridge.js to dist/client/admin/ during
# 'astro build' (resolved from @tinacms/bridge — a 15KB bundled runtime), but
# Caddy serves /admin/* from $SITE_DIR/admin/ (project root).
# Without this copy, the bridge script 404s and visual editing never loads.
# Note: the bridge.js in dist/client/admin/ is the correct bundled version
# (resolved by the integration via require.resolve('@tinacms/bridge')).
if [[ -f "$SITE_DIR/dist/client/admin/bridge.js" ]]; then
  cp "$SITE_DIR/dist/client/admin/bridge.js" "$SITE_DIR/admin/bridge.js"
  echo "[build] Copied bridge.js to admin/"
fi

if [[ -f "$SITE_DIR/dist/server/entry.mjs" ]]; then
  sudo -n systemctl restart "$UNIT"
  echo "[build] Restarted $UNIT"
fi
echo "[build] Done — $(date)"
BUILD
chmod +x /usr/local/bin/site-build

# Mark system phases complete only when the system phases actually ran.
if $SYSTEM_NEEDED; then
  date -u +"%Y-%m-%dT%H:%M:%SZ gitea=${GITEA_VERSION} node=$(node --version) bun=$(bun --version 2>/dev/null || echo n/a)" \
    > "$BOOTSTRAP_MARKER"
  log "System bootstrap marker written: $BOOTSTRAP_MARKER"
fi

# =============================================================================
# PHASE 8.5: GITEA ADMIN USER VERIFICATION (always runs, not gated by SYSTEM_NEEDED)
# =============================================================================
# Ensures the admin user exists with the correct password regardless of whether
# system phases ran. Prevents Error 2 (401 on Phase 11) when system was
# pre-bootstrapped but admin user was never created or password diverged.
if systemctl is-active --quiet gitea 2>/dev/null; then
  GITEA_API="http://127.0.0.1:3000/api/v1"
  AUTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -u "${GITEA_ADMIN_USER}:${GITEA_ADMIN_PASS}" "${GITEA_API}/user" 2>/dev/null || echo "000")
  if [[ "$AUTH_STATUS" != "200" ]]; then
    # User doesn't exist or password wrong — try to fix
    warn "Gitea admin ${GITEA_ADMIN_USER} auth failed (status=${AUTH_STATUS}) — repairing"
    # Try change-password first (works if user exists but password is wrong)
    sudo -u git GITEA_WORK_DIR=/var/lib/gitea /usr/local/bin/gitea \
      -c /etc/gitea/app.ini admin user change-password \
      --username "$GITEA_ADMIN_USER" \
      --password "$GITEA_ADMIN_PASS" \
      --must-change-password=false 2>/dev/null \
      && warn "Updated password for existing ${GITEA_ADMIN_USER}" \
      || {
        # User probably doesn't exist — create it
        sudo -u git GITEA_WORK_DIR=/var/lib/gitea /usr/local/bin/gitea \
          -c /etc/gitea/app.ini admin user create \
          --username "$GITEA_ADMIN_USER" \
          --password "$GITEA_ADMIN_PASS" \
          --email "$GITEA_ADMIN_EMAIL" \
          --admin --must-change-password=false 2>/dev/null \
          || err "Failed to create Gitea admin user"
      }
    # Verify it worked
    AUTH_VERIFY=$(curl -s -o /dev/null -w "%{http_code}" -u "${GITEA_ADMIN_USER}:${GITEA_ADMIN_PASS}" "${GITEA_API}/user" 2>/dev/null || echo "000")
    if [[ "$AUTH_VERIFY" == "200" ]]; then
      log "Gitea admin ${GITEA_ADMIN_USER} ready"
    else
      err "Gitea admin ${GITEA_ADMIN_USER} still not working (status=${AUTH_VERIFY}) — cannot continue safely"
      exit 1
    fi
  else
    skip "Gitea admin ${GITEA_ADMIN_USER} verified"
  fi
fi

# =============================================================================
# PHASE 9: PROJECT SITE DIR + ASTRO TEMPLATE (per-project, idempotent)
# =============================================================================
log "Phase 9/13: Project ${PROJECT_NAME} site_dir at ${SITE_DIR}"

mkdir -p "${SITE_DIR}/dist"

# umask 077 (set above for secret safety) makes mkdir -p create /var/www and
# /var/www/sites at 0700 — un-traversable by Caddy and the deploy user, which
# breaks static/admin serving, the git-sync watcher, and the join's site_dir
# probe. The web path must be traversable; content under the site dir is public.
chmod 0755 /var/www /var/www/sites "${SITE_DIR}"

PROJECT_ALREADY_SCAFFOLDED=false
if [[ -f "${SITE_DIR}/package.json" ]] && [[ "$FORCE_PROJECT" != "true" ]]; then
  PROJECT_ALREADY_SCAFFOLDED=true
  skip "${SITE_DIR}/package.json exists — preserving project scaffold"
fi

if ! $PROJECT_ALREADY_SCAFFOLDED; then
  cd "${SITE_DIR}"

  cat > package.json << 'PKGJSON'
{
  "name": "site-starter-template",
  "type": "module",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "if [ -f tina/config.ts ]; then tinacms dev -c \"astro dev --host 0.0.0.0\"; else astro dev --host 0.0.0.0; fi",
    "build": "astro build",
    "preview": "astro preview --host 0.0.0.0",
    "check": "astro check",
    "astro:dev": "astro dev --host 0.0.0.0",
    "astro:build": "astro build",
    "tinacms:build": "tinacms build --local --skip-cloud-checks"
  },
  "dependencies": {
    "astro": "^7.0.2",
    "@astrojs/react": "^6.0.0",
    "@astrojs/mdx": "^7.0.0",
    "@astrojs/node": "^11.0.0",
    "@astrojs/sitemap": "^3.7.3",
    "@astrojs/check": "^0.9.9",
    "@tinacms/astro": "^0.5.0",
    "@tinacms/datalayer": "^2.0.25",
    "react": "^19.2.7",
    "react-dom": "^19.2.7",
    "sharp": "^0.35.2",
    "sqlite-level": "^2.1.1",
    "memory-level": "^1.0.0",
    "tinacms": "^3.9.3",
    "typescript": "^6.0.3"
  },
  "devDependencies": {
    "@tailwindcss/vite": "^4.3.1",
    "@tailwindcss/typography": "^0.5.20",
    "@tinacms/cli": "^2.5.1",
    "@types/node": "^26.0.0",
    "tailwindcss": "^4.3.1"
  }
}
PKGJSON

   cat > astro.config.mjs << 'ASTROCONF'
import { defineConfig } from "astro/config";
import node from "@astrojs/node";
import react from "@astrojs/react";
import mdx from "@astrojs/mdx";
import sitemap from "@astrojs/sitemap";
import tina from "@tinacms/astro/integration";
import { tinaAdminDevRedirect } from "@tinacms/astro/vite";
import tailwindcss from "@tailwindcss/vite";
export default defineConfig({
  output: "static",
  adapter: node({ mode: "standalone" }),
  integrations: [
    react(),
    mdx(),
    tina(),
    sitemap(),
  ],
  vite: {
    plugins: [tailwindcss(), tinaAdminDevRedirect()],
    ssr: { noExternal: ["@tinacms/astro", "@tinacms/bridge"] },
  },
});
ASTROCONF

  cat > tsconfig.json << 'TSCONF'
{
  "extends": "astro/tsconfigs/strict",
  "compilerOptions": {
    "jsx": "react-jsx",
    "jsxImportSource": "react",
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
  },
  "exclude": ["admin/**", "dist/**", "node_modules/**"]
}
TSCONF

  mkdir -p src/styles
  cat > src/styles/global.css << 'CSS'
@import "./theme.css";
CSS

  cat > src/styles/theme.css << 'CSS'
@import "tailwindcss";
@plugin "@tailwindcss/typography";

@theme {
  --color-primary: oklch(0.45 0.15 250);
  --color-primary-light: oklch(0.60 0.12 250);
  --color-primary-dark: oklch(0.30 0.18 250);
  --color-secondary: oklch(0.60 0.18 30);
  --color-secondary-light: oklch(0.75 0.14 30);
  --color-secondary-dark: oklch(0.45 0.20 30);
  --color-background: oklch(0.98 0.005 90);
  --color-surface: oklch(0.95 0.005 90);
  --color-foreground: oklch(0.20 0.02 250);
  --color-muted: oklch(0.45 0.02 250);
  --color-border: oklch(0.85 0.01 250);
  --color-accent: oklch(0.55 0.20 30);
  --font-heading: "Inter", sans-serif;
  --font-body: "Inter", sans-serif;
  --spacing-section: 6rem;
  --spacing-section-sm: 4rem;
  --radius-sm: 0.25rem;
  --radius-md: 0.5rem;
  --radius-lg: 1rem;
  --radius-full: 9999px;
}
CSS

  mkdir -p src/layouts
  cat > src/layouts/BaseLayout.astro << 'LAYOUT'
---
interface Props { title: string; description?: string; }
const { title, description = "Built with the site pipeline" } = Astro.props;
import "../styles/theme.css";
---
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="description" content={description} />
    <title>{title}</title>
    <link rel="icon" type="image/x-icon" href="/favicon.ico" />
    <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />
    {/* Preconnect to Google Fonts so the TCP+TLS handshake overlaps HTML parse.
        frontend-builder replaces these with project-specific font <link>s
        plus &display=swap. */}
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <meta property="og:title" content={title} />
    <meta property="og:description" content={description} />
  </head>
  <body class="bg-background text-foreground font-body antialiased">
    <slot />
  </body>
</html>
LAYOUT

   mkdir -p src/pages
   cat > src/pages/index.astro << 'PAGE'
---
import BaseLayout from "../layouts/BaseLayout.astro";
---
<BaseLayout title="Welcome">
  <main class="flex min-h-screen items-center justify-center">
    <div class="text-center max-w-2xl px-6">
      <h1 class="text-5xl font-heading font-bold text-primary mb-6">Site Pipeline Ready</h1>
      <p class="text-xl text-muted">Run the agent pipeline to generate this site.</p>
    </div>
  </main>
</BaseLayout>
PAGE

  mkdir -p src/content/pages src/content/settings
  cat > src/content.config.ts << 'TS'
import { defineCollection } from "astro:content";
import { z } from "astro/zod";
import { glob } from "astro/loaders";

const pages = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/pages" }),
  schema: z.object({
    title: z.string(),
    description: z.string().optional(),
    image: z.string().optional(),
  }),
});

const settings = defineCollection({
  loader: glob({ pattern: "*.json", base: "./src/content/settings" }),
  schema: z.object({
    siteName: z.string(),
    tagline: z.string().optional(),
    nav: z.array(z.object({ label: z.string(), href: z.string() })).optional(),
    footerLinks: z.array(z.object({ label: z.string(), href: z.string() })).optional(),
    contactEmail: z.string().optional(),
    copyrightText: z.string().optional(),
  }),
});

export const collections = { pages, settings };
TS

  # Seed a placeholder content entry so the glob loader finds something.
  # Use .md (not .mdx) — TinaCMS defaults to .md extension for collections.
  # Using .mdx causes "Invalid file extension: expected '.md' but got '.mdx'"
  # when TinaCMS tries to read the file.
  cat > src/content/pages/welcome.md << 'MD'
---
title: Welcome
description: Placeholder page — agents customize per project
---
# Welcome
This site was scaffolded by the pipeline.
MD

  # Seed global site settings — editors can edit nav/footer in TinaCMS
  cat > src/content/settings/site.json << 'JSON'
{
  "siteName": "Site Name",
  "tagline": "Placeholder tagline — agents customize per project",
  "nav": [
    { "label": "Home", "href": "/" }
  ],
  "footerLinks": [
    { "label": "Home", "href": "/" }
  ],
  "contactEmail": "info@example.com",
  "copyrightText": "All rights reserved."
}
JSON

  mkdir -p src/components/sections src/components/ui src/assets public pipeline

  # TinaCMS scaffold — always create config + routes so tinacms build runs
  # and /admin/ is available by default. Without tina/config.ts, the build
  # script skips tinacms build and /admin/ returns 404.
  mkdir -p tina src/pages/tina-island src/pages/api/tina src/lib/tina

  cat > tina/config.ts << 'TINACONF'
import { AbstractAuthProvider, defineConfig } from "tinacms";

class PasswordAuthProvider extends AbstractAuthProvider {
  async authenticate() {
    if (window.location.pathname !== "/admin/login.html") {
      window.location.href = "/admin/login.html";
    }
    return { access_token: "LOCAL", id_token: "LOCAL", refresh_token: "LOCAL" };
  }
  async getUser() {
    try {
      const response = await fetch("/api/tina/auth-check");
      if (!response.ok) return false;
      return { name: "Site Admin", email: "admin@localhost" };
    } catch { return false; }
  }
  async getToken() { return { id_token: "" }; }
  async logout() {
    try { await fetch("/api/tina/logout", { method: "POST" }); } catch {}
    window.location.href = "/admin/login.html";
  }
  async logOut() { return this.logout(); }
}

export default defineConfig({
  clientId: null,
  token: null,
  authProvider: new PasswordAuthProvider(),
  contentApiUrlOverride: "/api/tina/gql",
  build: {
    outputFolder: "admin",
    publicFolder: ".",
  },
  media: {
    tina: {
      publicFolder: "public",
      mediaRoot: "images",
      static: false,
    },
    accept: ["image/*"],
  },
  schema: {
    collections: [
      {
        name: "page",
        label: "Pages",
        path: "src/content/pages",
        format: "md",
        ui: { router: ({ document }) => `/${document._sys.filename === "index" ? "" : document._sys.filename}` },
        fields: [
          { name: "title", type: "string", required: true },
          { name: "description", type: "string" },
        ],
      },
      {
        name: "settings",
        label: "Site Settings",
        path: "src/content/settings",
        format: "json",
        ui: { router: () => "/" },
        fields: [
          { name: "siteName", type: "string", required: true },
          { name: "tagline", type: "string" },
          {
            name: "nav",
            type: "object",
            list: true,
            label: "Navigation Menu",
            fields: [
              { name: "label", type: "string", required: true },
              { name: "href", type: "string", required: true },
            ],
          },
          {
            name: "footerLinks",
            type: "object",
            list: true,
            fields: [
              { name: "label", type: "string", required: true },
              { name: "href", type: "string", required: true },
            ],
          },
          { name: "contactEmail", type: "string" },
          { name: "copyrightText", type: "string" },
        ],
      },
    ],
  },
});
TINACONF

  mkdir -p src/components/islands
  cat > src/components/islands/PageIslandMarker.astro << 'TINAMARKER'
---
// Hidden bootstrap target for Tina visual editing. Frontend-builder replaces or
// extends this with content-specific islands; do not leave the registry empty.
const { data } = Astro.props;
---
<span hidden data-static-copy>{data?.data?.page?._sys?.relativePath ?? 'page'}</span>
TINAMARKER

  cat > src/lib/tina/islands.ts << 'TINAISLANDS'
import type { IslandRegistry } from "@tinacms/astro/experimental";
import PageIslandMarker from "../../components/islands/PageIslandMarker.astro";
import { requestWithMetadata } from "./data";

const PAGE_QUERY = `query page($relativePath: String!) {
  page(relativePath: $relativePath) {
    ... on Document { _sys { relativePath filename } id }
    title
    description
  }
}`;

export const pageIslandWrapper = {
  tag: "div",
  className: "tina-page-island-marker",
};

export const islands: IslandRegistry = {
  page: {
    fetch: (_request, params) => requestWithMetadata(
      { data: { page: {} }, query: PAGE_QUERY, variables: { relativePath: params.get("relativePath") ?? "welcome.md" } },
      { priority: "primary" }
    ),
    component: PageIslandMarker,
    wrapper: pageIslandWrapper,
    propsFromData: (data) => ({ data }),
  },
};
TINAISLANDS

  cat > 'src/pages/tina-island/[name].ts' << 'TINAISLAND'
import type { APIRoute } from "astro";
import { experimental_createIslandRoute } from "@tinacms/astro/experimental";
import { islands } from "../../lib/tina/islands";

export const prerender = false;
export const POST: APIRoute = experimental_createIslandRoute(islands);
TINAISLAND

  cat > tina/databaseClient.ts << 'TINADB'
import { createDatabase } from "@tinacms/datalayer";
import { FilesystemBridge } from "@tinacms/datalayer";
import { resolve, buildSchema } from "@tinacms/graphql";
import { MemoryLevel } from "memory-level";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * Production-safe database client for TinaCMS self-hosting on Bun/Node.
 *
 * Uses memory-level (pure JS) instead of sqlite-level (native better-sqlite3
 * which Bun doesn't support). The index is rebuilt on each server start —
 * fast for small sites.
 *
 * Reads the generated _schema.json to avoid importing tina/config.ts at
 * runtime (which pulls in tinacms -> @heroicons/react/solid, a directory
 * import that Node ESM doesn't support).
 */

const database = createDatabase({
  databaseAdapter: new MemoryLevel(),
  bridge: new FilesystemBridge(process.cwd()),
  gitProvider: {
    onPut: async (key: string, value: string) => {
      const bridge = new FilesystemBridge(process.cwd());
      await bridge.put(key, value);
    },
    onDelete: async (key: string) => {
      const bridge = new FilesystemBridge(process.cwd());
      await bridge.delete(key);
    },
  },
});

let indexed = false;
let indexingPromise: Promise<void> | null = null;

async function ensureIndexed() {
  if (indexed) return;
  if (indexingPromise) return indexingPromise;
  indexingPromise = (async () => {
    try {
      console.log("[TinaCMS] Indexing content into in-memory database...");
      const schemaPath = join(process.cwd(), "tina", "__generated__", "_schema.json");
      const schemaJson = JSON.parse(readFileSync(schemaPath, "utf-8"));
      const { graphQLSchema, tinaSchema } = await buildSchema({ schema: schemaJson } as any);
      await database.indexContent({ graphQLSchema, tinaSchema });
      indexed = true;
      console.log("[TinaCMS] Indexing complete.");
    } catch (error) {
      console.error("[TinaCMS] Indexing failed:", error);
      indexed = false;
      indexingPromise = null;
    }
  })();
  return indexingPromise;
}

const databaseClient = {
  ...database,
  request: async ({
    query,
    variables,
    user,
  }: {
    query: string;
    variables: Record<string, unknown>;
    user?: { sub: string } | undefined;
  }) => {
    await ensureIndexed();
    return resolve({
      query,
      variables,
      database,
      ctxUser: user,
      verbose: false,
      silenceErrors: false,
    });
  },
};

export default databaseClient;
TINADB

  cat > 'src/pages/api/tina/[...routes].ts' << 'TINAAPI'
import type { APIRoute } from "astro";
import { createHmac, timingSafeEqual } from "node:crypto";
import { Socket } from "node:net";
import { IncomingMessage, ServerResponse } from "node:http";
import { TinaNodeBackend } from "@tinacms/datalayer";
import databaseClient from "../../../../tina/databaseClient";

export const prerender = false;

const SESSION_COOKIE = "tina_admin_session";
const SESSION_MAX_AGE_SECONDS = 60 * 60 * 12;

function authSecret() {
  return process.env.TINA_ADMIN_PASSWORD || "";
}

function signSession(value: string) {
  return createHmac("sha256", authSecret()).update(value).digest("hex");
}

function safeEqual(a: string, b: string) {
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  return ab.length === bb.length && timingSafeEqual(ab, bb);
}

function parseCookies(header: string | undefined) {
  return Object.fromEntries(
    (header || "").split(";").map((part) => part.trim()).filter(Boolean).map((part) => {
      const [name, ...rest] = part.split("=");
      try { return [name, decodeURIComponent(rest.join("="))]; }
      catch { return [name, rest.join("=")]; }
    })
  );
}

function isSessionValid(cookieHeader: string | undefined) {
  const secret = authSecret();
  if (!secret) return false;
  const raw = parseCookies(cookieHeader)[SESSION_COOKIE];
  if (!raw) return false;
  const [issuedAt, signature] = raw.split(".");
  const issued = Number(issuedAt);
  if (!Number.isFinite(issued) || !signature) return false;
  if (Date.now() - issued > SESSION_MAX_AGE_SECONDS * 1000) return false;
  return safeEqual(signature, signSession(issuedAt));
}

function sessionCookie(request: Request) {
  const issuedAt = String(Date.now());
  const secure = new URL(request.url).protocol === "https:" ? "; Secure" : "";
  return `${SESSION_COOKIE}=${encodeURIComponent(`${issuedAt}.${signSession(issuedAt)}`)}; Path=/; Max-Age=${SESSION_MAX_AGE_SECONDS}; HttpOnly; SameSite=Lax${secure}`;
}

function json(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

async function readPassword(request: Request) {
  try {
    const body = await request.json();
    return typeof body?.password === "string" ? body.password : "";
  } catch {
    return "";
  }
}

// Backend auth contract:
// - POST /api/tina/login sets the HttpOnly tina_admin_session cookie.
// - POST /api/tina/logout clears the cookie.
// - GET /api/tina/auth-check lets PasswordAuthProvider decide whether /admin is logged in.
function PasswordBackendAuthProvider() {
  return {
    isAuthorized: async (req: IncomingMessage) => {
      if (isSessionValid(req.headers.cookie)) return { isAuthorized: true as const };
      return { isAuthorized: false as const, errorCode: 401, errorMessage: "Unauthorized" };
    },
  };
}

const tinaHandler = TinaNodeBackend({
  authProvider: PasswordBackendAuthProvider(),
  databaseClient,
});

export const ALL: APIRoute = async ({ request }) => {
  const url = new URL(request.url);

  if (request.method === "POST" && url.pathname === "/api/tina/login") {
    const expected = authSecret();
    const provided = await readPassword(request);
    if (!expected || provided !== expected) return json({ success: false }, 401);
    return json({ success: true }, 200, { "Set-Cookie": sessionCookie(request) });
  }

  if (request.method === "POST" && url.pathname === "/api/tina/logout") {
    return json({ success: true }, 200, {
      "Set-Cookie": `${SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax`,
    });
  }

  if (request.method === "GET" && url.pathname === "/api/tina/auth-check") {
    const authenticated = isSessionValid(request.headers.get("cookie") || undefined);
    return json({ authenticated }, authenticated ? 200 : 401);
  }

  const socket = new Socket();
  const req = new IncomingMessage(socket);
  req.method = request.method;
  req.url = `/api/tina${url.pathname.replace(/^\/api\/tina/, "")}${url.search}`;
  req.headers = Object.fromEntries(request.headers.entries());

  if (request.body && request.method !== "GET" && request.method !== "HEAD") {
    const bodyBuffer = Buffer.from(await request.arrayBuffer());
    req.push(bodyBuffer);
    const contentType = request.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      try {
        (req as any).body = JSON.parse(bodyBuffer.toString());
      } catch {
        (req as any).body = undefined;
      }
    }
  }
  req.push(null);

  return new Promise<Response>((resolve) => {
    const chunks: Buffer[] = [];
    const res = new ServerResponse(req);

    const originalWrite = res.write.bind(res);
    res.write = function (chunk: any, ...rest: any[]) {
      if (typeof chunk === "string") chunks.push(Buffer.from(chunk));
      else if (Buffer.isBuffer(chunk)) chunks.push(chunk);
      return originalWrite(chunk, ...rest);
    } as any;

    const originalEnd = res.end.bind(res);
    res.end = function (chunk?: any, ...rest: any[]) {
      if (chunk) {
        if (typeof chunk === "string") chunks.push(Buffer.from(chunk));
        else if (Buffer.isBuffer(chunk)) chunks.push(chunk);
      }
      const body = Buffer.concat(chunks);
      const responseHeaders = new Headers();
      const rawHeaders = res.getHeaders();
      for (const [k, v] of Object.entries(rawHeaders)) {
        if (v != null) responseHeaders.set(k, Array.isArray(v) ? v.join(", ") : String(v));
      }
      originalEnd(chunk, ...rest);
      socket.destroy();
      resolve(
        new Response(body.length > 0 ? body : null, {
          status: res.statusCode || 200,
          headers: responseHeaders,
        })
      );
      return res;
    } as any;

    tinaHandler(req, res);
  });
};
TINAAPI

  cat > src/lib/tina/data.ts << 'TINADATA'
import { requestWithMetadata } from "@tinacms/astro/data";
import { tinaField } from "@tinacms/astro/tina-field";
export { requestWithMetadata, tinaField };
TINADATA

  # Placeholder admin/index.html — replaced by Phase 4.2 (local TinaCMS build).
  # Without this, /admin/ returns 404 until the admin SPA is built and synced.
  mkdir -p admin
  cat > admin/index.html << 'ADMINPLACEHOLDER'
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Admin — Pending Build</title></head>
<body style="font-family:sans-serif;padding:2rem;max-width:600px;margin:0 auto">
<h1>TinaCMS Admin</h1>
<p>The admin SPA has not been built yet. It is built locally on the control
node during Phase 4.2 and published by build-deployer.</p>
<p>If you see this after deployment, run the TinaCMS local build phase.</p>
</body>
</html>
ADMINPLACEHOLDER

  # Password auth login page — TinaCMS custom backend auth gate.
  # The admin SPA reads collections without auth; mutations require
  # a session cookie set by this login form. The TINA_ADMIN_PASSWORD
  # env var (in /etc/default/astro-ssr-<project>) controls access.
  cat > admin/login.html << 'LOGINHTML'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin Login</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0a0a0a;color:#e5e5e5;display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:#141414;border:1px solid #2a2a2a;border-radius:12px;padding:2.5rem;width:100%;max-width:380px}
h1{font-size:1.25rem;margin-bottom:1.5rem;text-align:center;color:#fff}
input{width:100%;padding:0.75rem 1rem;background:#0a0a0a;border:1px solid #2a2a2a;border-radius:8px;color:#fff;font-size:0.95rem;margin-bottom:1rem}
input:focus{outline:none;border-color:#4a4a4a}
button{width:100%;padding:0.75rem;background:#fff;color:#0a0a0a;border:none;border-radius:8px;font-size:0.95rem;font-weight:600;cursor:pointer}
button:hover{background:#e5e5e5}
button:disabled{opacity:0.5;cursor:default}
.error{color:#ef4444;font-size:0.85rem;text-align:center;margin-bottom:1rem;display:none}
</style>
</head>
<body>
<div class="card">
<h1>Admin Login</h1>
<div class="error" id="err">Incorrect password. Try again.</div>
<input type="password" id="pw" placeholder="Password" autofocus>
<button id="btn" onclick="login()">Login</button>
</div>
<script>
async function login(){
  const pw=document.getElementById('pw').value;
  const btn=document.getElementById('btn');
  const err=document.getElementById('err');
  btn.disabled=true;btn.textContent='Logging in...';err.style.display='none';
  try{
    const r=await fetch('/api/tina/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})});
    if(r.ok){const d=await r.json();if(d.success){window.location.href='/admin/';return;}}
    err.style.display='block';
  }catch(e){err.style.display='block';}
  btn.disabled=false;btn.textContent='Login';
}
document.getElementById('pw').addEventListener('keydown',e=>{if(e.key==='Enter')login();});
</script>
</body>
</html>
LOGINHTML

  for S in Hero Gallery Nav Footer Testimonials Contact CTA; do
    cat > "src/components/sections/${S}.astro" << COMP
---
interface Props { class?: string; }
const { class: className = "" } = Astro.props;
---
<section class={\`py-16 md:py-24 \${className}\`}>
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <p class="text-muted text-center">${S} section — agents customize per project</p>
  </div>
</section>
COMP
  done

  cat > .gitignore << 'GI'
node_modules/
dist/
.astro/
.DS_Store
pipeline/
pipeline/vps-connection.json
pipeline/.git-credentials
pipeline/bootstrap-result.json
pipeline/bootstrap*.json
pipeline/bootstrap*.log
pipeline/bootstrap*.pid
pipeline/bootstrap*.exit
pipeline/installation-summary.md
pipeline/installation.log
pipeline/setup-wrapper.*
pipeline/RESULT.md
pipeline/HUMAN_REVIEW.md
.opencode/
.env
.env.*
*.log
# Lockfiles are regenerated per-deploy by the auto-rebuild watcher; not part of
# the source-of-truth repo for this static-site pipeline.
bun.lockb
package-lock.json
# NOTE: admin/ is intentionally NOT ignored — the TinaCMS admin SPA is built
# locally on the control node and committed to git so the VPS never needs to
# run tinacms build (which OOMs on 2GB VMs). Do not add admin/ here.
# NOTE: public/media/ is intentionally NOT ignored — TinaCMS uploads committed
# editor images there via the Gitea GitProvider. Do not add public/media/ here.
GI

  # Initial install only — no scaffold build. The scaffold's stub components
  # are guaranteed to produce a build, but it's wasted work because Phase 4
  # immediately replaces them with real code. The placeholder dist/client/index.html
  # below covers Caddy until Phase 4 rsyncs and runs the real build.
  #
  # Install with bun: ~3-5x faster than npm install, produces bun.lockb.
  # We never commit bun.lockb to the scaffold repo (it's a per-deploy thing
  # the auto-rebuild watcher recreates if needed).
  bun install --silent 2>&1 | tail -3 || warn "bun install failed — Phase 4 will retry"

  # Fix ownership immediately after scaffold (prevents rsync Permission denied)
  if id -u debian >/dev/null 2>&1; then
    chown -R debian:debian "${SITE_DIR}"
  fi

  log "Project scaffold ready for ${PROJECT_NAME}"
fi

# Always write a placeholder index.html if dist/client is empty (covers fresh dir)
if [[ ! -f "${SITE_DIR}/dist/client/index.html" ]]; then
  mkdir -p "${SITE_DIR}/dist/client"
  echo "<h1>Ready for ${PROJECT_NAME}</h1>" > "${SITE_DIR}/dist/client/index.html"
fi

# =============================================================================
# PHASE 10: PROJECT CADDY SITE FRAGMENT (idempotent)
# =============================================================================
log "Phase 10/13: Caddy site fragment for ${PROJECT_NAME}"

# Remove legacy Caddy default BEFORE creating our site fragment.
# This MUST happen here (not earlier) because Phase 4 may have just created
# legacy.caddy by migrating the default Caddyfile. If we remove it at the
# top of the script, Phase 4 recreates it later and the conflict persists.
# In plain-IP mode with port 80, legacy.caddy's :80 block would conflict
# with our project's :80 block, causing Caddy to serve the default welcome
# page. sslip.io vhost projects don't conflict — Caddy routes by Host header.
if [[ -n "${SITE_PORT:-}" && "$SITE_PORT" == "80" && -f /etc/caddy/sites/legacy.caddy ]]; then
  rm -f /etc/caddy/sites/legacy.caddy
  warn "Removed legacy.caddy — port 80 now serves ${PROJECT_NAME}"
fi

CADDY_SITE_FILE="/etc/caddy/sites/${PROJECT_NAME}.caddy"
if [[ -f "$CADDY_SITE_FILE" && "$FORCE_PROJECT" != "true" ]]; then
  skip "Caddy site fragment exists — preserving: $CADDY_SITE_FILE"
else
  if [[ "$USE_TLS" == true ]]; then
    # Real-domain vhost routing with automatic TLS via Let's Encrypt.
    cat > "$CADDY_SITE_FILE" << CEOF
# Site: ${PROJECT_NAME}  (url: ${SITE_URL})
${SITE_HOST} {
    root * ${SITE_DIR}/dist/client
    encode gzip zstd
    handle /tina-island/* {
        reverse_proxy 127.0.0.1:${ASTRO_SSR_PORT}
    }
    handle /api/tina/* {
        reverse_proxy 127.0.0.1:${ASTRO_SSR_PORT}
    }
    redir /admin /admin/ permanent
    handle /tina/__generated__/* {
        root * ${SITE_DIR}
        file_server
    }
    handle /admin/* {
        root * ${SITE_DIR}
        file_server
    }
    @static_files {
        file {
            try_files {path} {path}/index.html
        }
    }
    handle @static_files {
        rewrite * {file_match.relative}
        file_server
    }
    handle {
        reverse_proxy 127.0.0.1:${ASTRO_SSR_PORT}
    }
    header {
        X-Content-Type-Options "nosniff"
        Content-Security-Policy "frame-ancestors 'self'"
        -Server
    }
}
CEOF
  elif [[ -n "$SITE_HOST" && "$SITE_HOST" == *".sslip.io" ]]; then
    # sslip.io vhost routing: Caddy auto-provisions Let's Encrypt TLS for
    # the sslip.io hostname (it's a valid DNS name). When a real domain is
    # acquired, just change SITE_HOST — the Caddy config stays the same.
    cat > "$CADDY_SITE_FILE" << CEOF
# Site: ${PROJECT_NAME}  (url: ${SITE_URL})
# sslip.io temporary hostname — replace with real domain when ready:
#   sed -i 's/${SITE_HOST}/myproject.example.com/' ${CADDY_SITE_FILE}
#   systemctl reload caddy
${SITE_HOST} {
    root * ${SITE_DIR}/dist/client
    encode gzip zstd
    handle /tina-island/* {
        reverse_proxy 127.0.0.1:${ASTRO_SSR_PORT}
    }
    handle /api/tina/* {
        reverse_proxy 127.0.0.1:${ASTRO_SSR_PORT}
    }
    redir /admin /admin/ permanent
    handle /tina/__generated__/* {
        root * ${SITE_DIR}
        file_server
    }
    handle /admin/* {
        root * ${SITE_DIR}
        file_server
    }
    @static_files {
        file {
            try_files {path} {path}/index.html
        }
    }
    handle @static_files {
        rewrite * {file_match.relative}
        file_server
    }
    handle {
        reverse_proxy 127.0.0.1:${ASTRO_SSR_PORT}
    }
    header {
        X-Content-Type-Options "nosniff"
        Content-Security-Policy "frame-ancestors 'self'"
        -Server
    }
}
CEOF
  else
    # Plain-IP, port-based routing (private IP fallback).
    # Each project listens on its own port (SITE_PORT).
    cat > "$CADDY_SITE_FILE" << CEOF
# Site: ${PROJECT_NAME}  (url: ${SITE_URL})
:${SITE_PORT} {
    root * ${SITE_DIR}/dist/client
    encode gzip zstd
    handle /tina-island/* {
        reverse_proxy 127.0.0.1:${ASTRO_SSR_PORT}
    }
    handle /api/tina/* {
        reverse_proxy 127.0.0.1:${ASTRO_SSR_PORT}
    }
    redir /admin /admin/ permanent
    handle /tina/__generated__/* {
        root * ${SITE_DIR}
        file_server
    }
    handle /admin/* {
        root * ${SITE_DIR}
        file_server
    }
    @static_files {
        file {
            try_files {path} {path}/index.html
        }
    }
    handle @static_files {
        rewrite * {file_match.relative}
        file_server
    }
    handle {
        reverse_proxy 127.0.0.1:${ASTRO_SSR_PORT}
    }
    header {
        X-Content-Type-Options "nosniff"
        Content-Security-Policy "frame-ancestors 'self'"
        -Server
    }
}
CEOF
    # Open the per-project port in the firewall (idempotent)
    ufw allow "${SITE_PORT}/tcp" >/dev/null 2>&1 || true
  fi
fi
chmod 0644 "$CADDY_SITE_FILE" 2>/dev/null || true

# Validate and reload Caddy
# IMPORTANT: Validate the main Caddyfile (which imports all fragments),
# not the individual fragment — a fragment alone is not a valid Caddyfile.
if caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
  systemctl reload caddy 2>/dev/null || systemctl restart caddy
else
  err "Caddy config invalid after adding ${PROJECT_NAME} fragment"
  err "Fragment saved at ${CADDY_SITE_FILE} — fix and run: caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile && systemctl reload caddy"
  exit 1
fi

# =============================================================================
# PHASE 11: GITEA REPO (idempotent via API)
# =============================================================================
log "Phase 11/13: Gitea repo ${PROJECT_NAME}"

GITEA_API="http://127.0.0.1:3000/api/v1"
# Gitea may still be (re)starting after earlier phases — wait for it to answer
# before judging auth, and distinguish "unreachable" (000) from "bad creds".
AUTH_STATUS="000"
for _i in $(seq 1 30); do
  AUTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -u "${GITEA_ADMIN_USER}:${GITEA_ADMIN_PASS}" "${GITEA_API}/user" 2>/dev/null) || AUTH_STATUS="000"
  [[ "$AUTH_STATUS" == "200" ]] && break
  sleep 2
done
if [[ "$AUTH_STATUS" == "000" || -z "$AUTH_STATUS" ]]; then
  err "Gitea unreachable on 127.0.0.1:3000 (status=000) — service likely down; check: systemctl status gitea"
  exit 1
elif [[ "$AUTH_STATUS" != "200" ]]; then
  err "Gitea admin auth failed for ${GITEA_ADMIN_USER} (status=${AUTH_STATUS})"
  exit 1
else
  GITEA_AUTH_OK=true

  # Check if repo exists before POST to avoid noise/errors
  REPO_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -u "${GITEA_ADMIN_USER}:${GITEA_ADMIN_PASS}" \
    "${GITEA_API}/repos/${GITEA_ADMIN_USER}/${PROJECT_NAME}" 2>/dev/null || echo "000")

  if [[ "$REPO_STATUS" == "200" ]]; then
    skip "Gitea repo ${GITEA_ADMIN_USER}/${PROJECT_NAME} already exists"
  else
    curl -s -X POST "${GITEA_API}/user/repos" \
      -H "Content-Type: application/json" \
      -u "${GITEA_ADMIN_USER}:${GITEA_ADMIN_PASS}" \
      -d "{\"name\":\"${PROJECT_NAME}\",\"default_branch\":\"main\",\"auto_init\":false}" \
      >/dev/null 2>&1 || warn "Gitea repo create returned non-zero"
    log "Gitea repo ${PROJECT_NAME} created"
  fi
fi

# Initialize local git repo if not already, and push
cd "${SITE_DIR}"
if [[ ! -d .git ]]; then
  git init -b main >/dev/null 2>&1
  git config user.email "pipeline@localhost"
  git config user.name "Site Pipeline"
  git add -A
  git commit -m "Initial template" --quiet 2>/dev/null || true
fi

# Set remote (idempotent) — only if Gitea auth succeeded
if $GITEA_AUTH_OK; then
  REMOTE_URL_CLEAN="http://127.0.0.1:3000/${GITEA_ADMIN_USER}/${PROJECT_NAME}.git"
  if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "$REMOTE_URL_CLEAN"
  else
    git remote add origin "$REMOTE_URL_CLEAN"
  fi

  # Credentials live in a 600-permission file rather than embedded in the
  # remote URL. git-sync-watch runs as `debian`, so the file must be readable
  # by debian. We place it inside the repo at .git/.gitea-credentials (the
  # entire .git/ is already excluded from the working tree's commit graph) and
  # use --local to scope the helper to this repo only.
  CRED_FILE="${SITE_DIR}/.git/.gitea-credentials"
  URLENC_PASS=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$GITEA_ADMIN_PASS" 2>/dev/null || printf '%s' "$GITEA_ADMIN_PASS")
  printf 'http://%s:%s@127.0.0.1:3000\n' "$GITEA_ADMIN_USER" "$URLENC_PASS" > "$CRED_FILE"
  chmod 600 "$CRED_FILE"
  if id -u debian >/dev/null 2>&1; then
    chown debian:debian "$CRED_FILE"
  fi
  git config --local credential.helper "store --file=$CRED_FILE"

  # Push only if there's something to push
  if git rev-parse HEAD >/dev/null 2>&1; then
    git push -u origin main --quiet 2>/dev/null || skip "git push skipped (already up-to-date or no commits)"
  fi
else
  skip "Gitea auth failed — skipping remote setup and push"
fi

# =============================================================================
# PHASE 12: GIT-SYNC SYSTEMD UNIT (per-project)
# =============================================================================
log "Phase 12/13: Git-sync watcher for ${PROJECT_NAME}"

GITSYNC_UNIT="/etc/systemd/system/git-sync-${PROJECT_NAME}.service"
if [[ -f "$GITSYNC_UNIT" && "$FORCE_PROJECT" != "true" ]]; then
  skip "git-sync-${PROJECT_NAME}.service exists — preserving"
else
  cat > "$GITSYNC_UNIT" << EOF
[Unit]
Description=Git-sync for ${PROJECT_NAME}
After=network.target gitea.service
[Service]
Type=simple
User=debian
WorkingDirectory=${SITE_DIR}
ExecStart=/usr/local/bin/git-sync-watch ${SITE_DIR}
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
fi
# --now starts the watcher immediately. Without it the unit was only enabled
# (would start on next reboot), so the very first deploy after bootstrap
# wouldn't get auto-rebuild on content changes until reboot.
systemctl enable --now "git-sync-${PROJECT_NAME}" >/dev/null 2>&1 || true

# =============================================================================
# PHASE 13: TINACMS / ASTRO SSR SERVICE (per-project)
# =============================================================================
log "Phase 13/13: TinaCMS Astro SSR service for ${PROJECT_NAME}"

TINACMS_DB_DIR="/var/lib/tinacms"
TINACMS_DB_PATH="${TINACMS_DB_DIR}/${PROJECT_NAME}.db"
ASTRO_SSR_UNIT="/etc/systemd/system/astro-ssr-${PROJECT_NAME}.service"
ASTRO_SSR_ENV="/etc/default/astro-ssr-${PROJECT_NAME}"
ASTRO_SSR_SUDOERS="/etc/sudoers.d/astro-ssr-${PROJECT_NAME}"

mkdir -p "$TINACMS_DB_DIR"
if id -u debian >/dev/null 2>&1; then
  chown debian:debian "$TINACMS_DB_DIR"
fi
chmod 750 "$TINACMS_DB_DIR" 2>/dev/null || true

EXISTING_TINA_ADMIN_PASS=""
if [[ -f "$ASTRO_SSR_ENV" && "$FORCE_PROJECT" != "true" ]]; then
  EXISTING_TINA_TOKEN=$(grep -E '^TINA_TOKEN=' "$ASTRO_SSR_ENV" 2>/dev/null | head -1 | cut -d= -f2- || true)
  EXISTING_GITEA_API_TOKEN=$(grep -E '^GITEA_API_TOKEN=' "$ASTRO_SSR_ENV" 2>/dev/null | head -1 | cut -d= -f2- || true)
  EXISTING_TINA_ADMIN_PASS=$(grep -E '^TINA_ADMIN_PASSWORD=' "$ASTRO_SSR_ENV" 2>/dev/null | head -1 | cut -d= -f2- || true)
fi

TINACMS_AUTH_TOKEN="${EXISTING_TINA_TOKEN:-$(openssl rand -hex 32)}"
TINA_ADMIN_PASSWORD="${EXISTING_TINA_ADMIN_PASS:-$(openssl rand -base64 12)}"
TINACMS_GITEA_TOKEN="${EXISTING_GITEA_API_TOKEN:-}"
if [[ -z "$TINACMS_GITEA_TOKEN" && "${GITEA_AUTH_OK:-false}" == "true" ]]; then
  TOKEN_NAME="tinacms-${PROJECT_NAME}"
  TOKEN_JSON=$(curl -s -X POST "${GITEA_API}/users/${GITEA_ADMIN_USER}/tokens" \
    -H "Content-Type: application/json" \
    -u "${GITEA_ADMIN_USER}:${GITEA_ADMIN_PASS}" \
    -d "{\"name\":\"${TOKEN_NAME}\",\"scopes\":[\"read:repository\",\"write:repository\"]}" 2>/dev/null || true)
  TINACMS_GITEA_TOKEN=$(python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("sha1") or data.get("token") or "")' <<<"$TOKEN_JSON" 2>/dev/null || true)
  if [[ -z "$TINACMS_GITEA_TOKEN" ]]; then
    TOKEN_JSON=$(curl -s -X POST "${GITEA_API}/users/${GITEA_ADMIN_USER}/tokens" \
      -H "Content-Type: application/json" \
      -u "${GITEA_ADMIN_USER}:${GITEA_ADMIN_PASS}" \
      -d "{\"name\":\"${TOKEN_NAME}-$(date +%s)\"}" 2>/dev/null || true)
    TINACMS_GITEA_TOKEN=$(python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("sha1") or data.get("token") or "")' <<<"$TOKEN_JSON" 2>/dev/null || true)
  fi
fi

if [[ -z "$TINACMS_GITEA_TOKEN" ]]; then
  warn "No Gitea API token available for TinaCMS — writing env file but SSR service will not be started"
fi

cat > "$ASTRO_SSR_ENV" << EOF
HOST=127.0.0.1
PORT=${ASTRO_SSR_PORT}
TINA_PUBLIC_IS_LOCAL=false
TINA_TOKEN=${TINACMS_AUTH_TOKEN}
TINA_PROJECT_NAME=${PROJECT_NAME}
TINA_DB_PATH=${TINACMS_DB_PATH}
TINA_COMMIT_MESSAGE="Edited with TinaCMS"
TINA_ADMIN_PASSWORD=${TINA_ADMIN_PASSWORD}
GITEA_HOST=${GITEA_PUBLIC_URL}
GITEA_OWNER=${GITEA_ADMIN_USER}
GITEA_REPO=${PROJECT_NAME}
GITEA_BRANCH=main
GITEA_API_TOKEN=${TINACMS_GITEA_TOKEN}
EOF
chmod 640 "$ASTRO_SSR_ENV"
if id -u debian >/dev/null 2>&1; then
  chown root:debian "$ASTRO_SSR_ENV"
fi

cat > "$ASTRO_SSR_UNIT" << EOF
[Unit]
Description=Astro SSR / TinaCMS backend for ${PROJECT_NAME}
After=network.target gitea.service

[Service]
Type=simple
User=debian
WorkingDirectory=${SITE_DIR}
EnvironmentFile=${ASTRO_SSR_ENV}
ExecStart=/usr/bin/env node ${SITE_DIR}/dist/server/entry.mjs
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > "$ASTRO_SSR_SUDOERS" << EOF
# Managed by astro-static setup-vps.sh Phase 13 — allows the deploy user to
# restart only this project's Astro SSR/TinaCMS backend after a successful build.
debian ALL=(root) NOPASSWD: /usr/bin/systemctl restart astro-ssr-${PROJECT_NAME}
debian ALL=(root) NOPASSWD: /usr/bin/systemctl status astro-ssr-${PROJECT_NAME}
EOF
chmod 0440 "$ASTRO_SSR_SUDOERS"
if ! visudo -cf "$ASTRO_SSR_SUDOERS" >/dev/null 2>&1; then
  rm -f "$ASTRO_SSR_SUDOERS"
  warn "Rejected sudoers drop-in for astro-ssr-${PROJECT_NAME}; site-build may not restart TinaCMS SSR"
fi

systemctl daemon-reload
systemctl enable "astro-ssr-${PROJECT_NAME}" >/dev/null 2>&1 || true
if [[ -f "${SITE_DIR}/dist/server/entry.mjs" && -n "$TINACMS_GITEA_TOKEN" ]]; then
  systemctl restart "astro-ssr-${PROJECT_NAME}" >/dev/null 2>&1 || warn "astro-ssr-${PROJECT_NAME} did not start — inspect: journalctl -u astro-ssr-${PROJECT_NAME}"
else
  skip "astro-ssr-${PROJECT_NAME} enabled but not started yet (build output or Gitea token missing)"
fi

# =============================================================================
# PERMISSIONS / OWNERSHIP
# =============================================================================
chmod 750 /etc/gitea 2>/dev/null || true
chmod 640 /etc/gitea/app.ini 2>/dev/null || true

if id -u debian >/dev/null 2>&1; then
  chown -R debian:debian "${SITE_DIR}"
fi

# Mark project complete
date -u +"%Y-%m-%dT%H:%M:%SZ site_dir=${SITE_DIR} url=${SITE_URL}" > "$PROJECT_MARKER"

# Final Caddy reload — earlier phases may have skipped reload due to validation
# failures caused by legacy.caddy conflicts. Now that legacy.caddy is removed
# (Phase 10) and all fragments are in place, try one more time before writing
# the final installation summary so any warning is recorded there.
if caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
  systemctl reload caddy 2>/dev/null || systemctl restart caddy
  log "Final Caddy reload successful — all site fragments active"
else
  err "Final Caddy validation still failing — Caddy site is not safe to publish"
  err "Run: caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile"
  exit 1
fi

# =============================================================================
# OUTPUT — machine-readable for the control node to parse
# =============================================================================
GENERATED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
NODE_VERSION=$(node --version 2>/dev/null || echo NONE)
BUN_VERSION=$(bun --version 2>/dev/null || echo NONE)
SYSTEM_BOOTSTRAPPED=$([ -f "$BOOTSTRAP_MARKER" ] && echo YES || echo NO)
if $SYSTEM_NEEDED; then
  SYSTEM_PHASES_RUN=YES
else
  SYSTEM_PHASES_RUN=NO
fi
GITEA_REPO_URL="${GITEA_PUBLIC_URL}/${GITEA_ADMIN_USER}/${PROJECT_NAME}.git"
GITEA_REPO_SSH="ssh://git@${SERVER_IP}/home/git/gitea-repositories/${GITEA_ADMIN_USER}/${PROJECT_NAME}.git"
_write_installation_summary 0
DIAGNOSTICS_JSON="$(_diagnostics_json)"

jq -n   --arg schema_version "astro-static-bootstrap-result/v1"   --arg project_name "$PROJECT_NAME"   --arg server_ip "$SERVER_IP"   --arg domain "$DOMAIN"   --argjson use_tls "$( [[ "$USE_TLS" == "true" ]] && printf 'true' || printf 'false' )"   --arg site_dir "$SITE_DIR"   --arg site_host "$SITE_HOST"   --arg site_port "${SITE_PORT:-}"   --arg site_url "$SITE_URL"   --arg gitea_url "$GITEA_PUBLIC_URL"   --arg gitea_user "$GITEA_ADMIN_USER"   --arg gitea_repo_url "$GITEA_REPO_URL"   --arg gitea_repo_ssh "$GITEA_REPO_SSH"   --arg node_version "$NODE_VERSION"   --arg bun_version "$BUN_VERSION"   --arg system_bootstrapped "$SYSTEM_BOOTSTRAPPED"   --arg system_phases_run "$SYSTEM_PHASES_RUN"   --arg caddy_site_file "$CADDY_SITE_FILE"   --arg astro_ssr_port "$ASTRO_SSR_PORT"   --arg astro_ssr_unit "astro-ssr-${PROJECT_NAME}" \
  --arg gitea_pass "$GITEA_ADMIN_PASS" \
  --arg tina_admin_password "$TINA_ADMIN_PASSWORD" \
  --arg installation_log "$INSTALL_LOG_PATH" \
  --arg installation_summary "$SUMMARY_PATH" \
  --argjson diagnostics "$DIAGNOSTICS_JSON" \
  --arg generated_at "$GENERATED_AT"   '{
    schema_version: $schema_version,
    project_name: $project_name,
    server_ip: $server_ip,
    domain: $domain,
    use_tls: $use_tls,
    site_dir: $site_dir,
    site_host: $site_host,
    site_port: (if $site_port == "" then null else ($site_port | tonumber) end),
    site_url: $site_url,
    gitea_url: $gitea_url,
    gitea_user: $gitea_user,
    gitea_pass: $gitea_pass,
    gitea_repo_url: $gitea_repo_url,
    gitea_repo_ssh: $gitea_repo_ssh,
    tina_admin_password: $tina_admin_password,
    node_version: $node_version,
    bun_version: $bun_version,
    system_bootstrapped: $system_bootstrapped,
    system_phases_run: $system_phases_run,
    caddy_site_file: $caddy_site_file,
    astro_ssr_port: ($astro_ssr_port | tonumber),
    astro_ssr_unit: $astro_ssr_unit,
    installation_log: $installation_log,
    installation_summary: $installation_summary,
    diagnostics: $diagnostics,
    generated_at: $generated_at
  }' > "$RESULT_PATH"
chmod 0600 "$RESULT_PATH"

cat << RESULT
===PIPELINE_RESULT===
RESULT_JSON=${RESULT_PATH}
SERVER_IP=${SERVER_IP}
SITE_DIR=${SITE_DIR}
SITE_URL=${SITE_URL}
GITEA_URL=${GITEA_PUBLIC_URL}
GITEA_ADMIN_USER=${GITEA_ADMIN_USER}
GITEA_ADMIN_PASS=[redacted]
INSTALLATION_LOG=${INSTALL_LOG_PATH}
INSTALLATION_SUMMARY=${SUMMARY_PATH}
PROJECT_NAME=${PROJECT_NAME}
===END_RESULT===
RESULT

log "VPS setup complete for ${PROJECT_NAME} (system_phases_run=${SYSTEM_PHASES_RUN})"
