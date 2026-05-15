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
#     Create site_dir, Caddy site fragment, Gitea repo, git-sync unit.
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
#   DOMAIN=auto         → each project gets its own port on the public IP;
#                         first project :80, subsequent :8081, :8082, ...
#                         (override per project with PROJECT_PORT=8090)
#   SITE_URL is emitted in PIPELINE_RESULT so the control node knows the URL.
#
# =============================================================================

set -euo pipefail
IFS=$'\n\t'
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
        echo "[!!] Apt lock still held after ${max_wait}s — forcing cleanup"
        fuser -k /var/lib/dpkg/lock-frontend 2>/dev/null || true
        rm -f /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock
        dpkg --configure -a 2>/dev/null || true
        break
      fi
      sleep 5
      waited=$((waited + 5))
      echo "[--] Waiting for apt lock... (${waited}s)"
    done
  else
    # Fallback: check if lock files exist and wait for them to disappear
    while [ -f /var/lib/dpkg/lock-frontend ] || [ -f /var/lib/dpkg/lock ]; do
      if [ "$waited" -ge "$max_wait" ]; then
        echo "[!!] Apt lock still held after ${max_wait}s — forcing cleanup"
        rm -f /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock
        dpkg --configure -a 2>/dev/null || true
        break
      fi
      # Check if any apt/dpkg process is actually running — lock files may be stale
      if ! pgrep -x apt-get >/dev/null 2>&1 && ! pgrep -x dpkg >/dev/null 2>&1; then
        echo "[--] Lock files exist but no apt/dpkg process running — removing stale locks"
        rm -f /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock
        dpkg --configure -a 2>/dev/null || true
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
GITEA_ADMIN_USER="${GITEA_ADMIN_USER:-siteadmin}"
# Strip =+/ and newlines from base64: those characters break the password when
# it's embedded in URL contexts (git remote http://user:pass@host/...) or
# argv expansion. Keep this in sync with bg-bootstrap.sh's generator.
GITEA_ADMIN_PASS="${GITEA_ADMIN_PASS:-$(openssl rand -base64 24 | tr -d '=+/\n' | cut -c1-24)}"
GITEA_ADMIN_EMAIL="${GITEA_ADMIN_EMAIL:-admin@localhost}"
PROJECT_NAME="${PROJECT_NAME:-default}"
GITEA_VERSION="1.25.5"
NODE_MAJOR=22
FORCE_SYSTEM="${FORCE_SYSTEM:-false}"
FORCE_PROJECT="${FORCE_PROJECT:-false}"

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
RESULT_PATH="/tmp/pipeline-result.json"

# --- Helpers ---
log()  { echo "[OK] $*"; }
warn() { echo "[!!] $*"; }
err()  { echo "[ERR] $*" >&2; }
skip() { echo "[--] $*"; }

mkdir -p "${STATE_DIR}" "${PROJECT_STATE_DIR}"
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
    GENERATED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    NODE_VERSION=$(node --version 2>/dev/null || echo NONE)
    BUN_VERSION=$(bun --version 2>/dev/null || echo NONE)
    SYSTEM_BOOTSTRAPPED=$([ -f "$BOOTSTRAP_MARKER" ] && echo YES || echo NO)
    GITEA_REPO_URL="${_GITEA_PUBLIC_URL}/${_GITEA_ADMIN_USER}/${_PROJECT_NAME}.git"
    GITEA_REPO_SSH="ssh://git@${_SERVER_IP}/home/git/gitea-repositories/${_GITEA_ADMIN_USER}/${_PROJECT_NAME}.git"
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
      --arg node_version "$NODE_VERSION" \
      --arg bun_version "$BUN_VERSION" \
      --arg system_bootstrapped "$SYSTEM_BOOTSTRAPPED" \
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
        node_version: $node_version,
        bun_version: $bun_version,
        system_bootstrapped: $system_bootstrapped,
        exit_code: $exit_code,
        generated_at: $generated_at,
        trap_generated: true
      }' > "$RESULT_PATH" 2>/dev/null || true
    chmod 0644 "$RESULT_PATH" 2>/dev/null || true
    warn "EXIT trap wrote result JSON (exit_code=$exit_code)"
  fi
}
trap _ensure_result_and_perms EXIT

# --- Detect IP ---
SERVER_IP=$(ip -4 addr show scope global | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1)
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

# DOMAIN=none is treated identically to DOMAIN=auto: no public hostname, no
# TLS, plain-IP routing. The brief schema accepts "none" as a sentinel for
# "this site has no DNS yet"; we use the same auto-port assignment so a fresh
# bootstrap on `none` doesn't try to obtain a Let's Encrypt cert for a
# nonexistent host.
if [[ "$DOMAIN" == "auto" || "$DOMAIN" == "none" ]]; then
  USE_TLS=false
  GIT_HOST="${SERVER_IP}:3000"

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
        grep -oE '^:[0-9]+' "$f" 2>/dev/null | tr -d ':'
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
    # Note: legacy.caddy removal is deferred to Phase 10 (after Phase 4 may
    # create it via Caddyfile migration). Removing it here is too early.
  else
    SITE_URL="http://${SERVER_IP}:${SITE_PORT}"
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
if [[ "$USE_TLS" == "true" ]]; then
  GITEA_PUBLIC_URL="https://${GIT_HOST}"
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
  log "Phase 1/12: System packages"
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
  log "Phase 2/12: Firewall"
  # Only reset if ufw is inactive — preserves operator customizations on re-run
  if ! ufw status | grep -q "Status: active"; then
    ufw --force reset >/dev/null 2>&1 || true
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow ssh
    ufw allow 80/tcp
    ufw allow 443/tcp
    if [[ "$USE_TLS" != "true" ]]; then ufw allow 3000/tcp; fi
    ufw --force enable
  else
    skip "ufw already active — verifying required ports"
    ufw allow ssh      >/dev/null
    ufw allow 80/tcp   >/dev/null
    ufw allow 443/tcp  >/dev/null
    if [[ "$USE_TLS" != "true" ]]; then ufw allow 3000/tcp >/dev/null; fi
  fi
  systemctl enable --now fail2ban >/dev/null 2>&1 || true
fi

# =============================================================================
# PHASE 3: GITEA
# =============================================================================
if $SYSTEM_NEEDED; then
  log "Phase 3/12: Gitea ${GITEA_VERSION}"

  id -u git >/dev/null 2>&1 || \
    adduser --system --shell /bin/bash --gecos 'Git Version Control' \
      --group --disabled-password --home /home/git git

  CURRENT_GITEA_VERSION=$(/usr/local/bin/gitea --version 2>/dev/null | awk '{print $3}' || echo "")
  if [[ "$CURRENT_GITEA_VERSION" != "$GITEA_VERSION" ]]; then
    wget -q -O /usr/local/bin/gitea.new \
      "https://dl.gitea.com/gitea/${GITEA_VERSION}/gitea-${GITEA_VERSION}-linux-amd64"
    chmod +x /usr/local/bin/gitea.new
    mv /usr/local/bin/gitea.new /usr/local/bin/gitea
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

  if [[ "$USE_TLS" == true ]]; then
    GITEA_ROOT_URL="https://${GIT_HOST}/"
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
INSTALL_LOCK = true
SECRET_KEY   = ${GITEA_SECRET}

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
  else
    skip "/etc/gitea/app.ini exists — preserving operator config"
  fi

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

  systemctl enable --now gitea >/dev/null 2>&1 || true
  # If we replaced the binary, restart to pick it up
  if [[ "$CURRENT_GITEA_VERSION" != "$GITEA_VERSION" ]]; then
    systemctl restart gitea
  fi

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
  log "Phase 4/12: Caddy"

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

  mkdir -p /etc/caddy/sites

  # Migrate legacy single-file Caddyfile to imports pattern if needed.
  # We consider the Caddyfile "legacy" if it contains anything besides
  # comments/whitespace and has no `import /etc/caddy/sites/*` line.
  if [[ -f /etc/caddy/Caddyfile ]] && ! grep -q 'import /etc/caddy/sites/' /etc/caddy/Caddyfile; then
    if grep -qE '^[^#[:space:]]' /etc/caddy/Caddyfile; then
      cp /etc/caddy/Caddyfile "/etc/caddy/sites/legacy.caddy"
      log "Migrated existing Caddyfile → /etc/caddy/sites/legacy.caddy"
    fi
    cat > /etc/caddy/Caddyfile << 'CEOF'
# Managed by site-pipeline setup-vps.sh
# Per-site configs live in /etc/caddy/sites/ and are imported here.
# Do not edit per-site config in this file — create a new fragment.

import /etc/caddy/sites/*.caddy
CEOF
  elif [[ ! -f /etc/caddy/Caddyfile ]]; then
    cat > /etc/caddy/Caddyfile << 'CEOF'
# Managed by site-pipeline setup-vps.sh
import /etc/caddy/sites/*.caddy
CEOF
  fi

  # Ensure a global git.* site fragment exists (shared across all projects)
  if [[ ! -f /etc/caddy/sites/_gitea.caddy ]]; then
    if [[ "$USE_TLS" == true ]]; then
      cat > /etc/caddy/sites/_gitea.caddy << CEOF
${GIT_HOST} {
    reverse_proxy 127.0.0.1:3000
}
CEOF
    else
      # Plain-IP mode — Caddy can't host git.IP; Gitea listens on :3000 directly
      cat > /etc/caddy/sites/_gitea.caddy << 'CEOF'
# Gitea runs on :3000 directly in plain-IP mode.
# Add a reverse_proxy block here once a real domain is configured.
CEOF
    fi
  fi

  systemctl enable --now caddy >/dev/null 2>&1 || true
fi

# =============================================================================
# PHASE 5: NODE.JS
# =============================================================================
if $SYSTEM_NEEDED; then
  log "Phase 5/12: Node.js ${NODE_MAJOR}"
  CURRENT_NODE=$(node --version 2>/dev/null | grep -oP '^v\K[0-9]+' || echo "0")
  if [[ "$CURRENT_NODE" -lt "$NODE_MAJOR" ]]; then
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
      | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg 2>/dev/null
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
  log "Phase 6/12: Bun"
  if ! command -v bun >/dev/null 2>&1; then
    curl -fsSL https://bun.sh/install | bash
    [[ -f /root/.bun/bin/bun ]]  && ln -sf /root/.bun/bin/bun  /usr/local/bin/bun
    [[ -f /root/.bun/bin/bunx ]] && ln -sf /root/.bun/bin/bunx /usr/local/bin/bunx
  else
    skip "Bun $(bun --version 2>/dev/null) already installed"
  fi
fi

# =============================================================================
# PHASE 7: IMAGE TOOLS
# =============================================================================
if $SYSTEM_NEEDED; then
  log "Phase 7/12: Image tools"
  wait_for_apt_lock 30
  apt-get install -y -qq pngquant jpegoptim imagemagick potrace librsvg2-bin webp \
    || { warn "Image tools install failed — retrying"; wait_for_apt_lock 15; apt-get install -y -qq pngquant jpegoptim imagemagick potrace librsvg2-bin webp; }
fi

# =============================================================================
# PHASE 8: SHARED BUILD/SYNC SCRIPTS
# =============================================================================
if $SYSTEM_NEEDED; then
  log "Phase 8/12: Shared build + sync scripts"

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
    # Auto-rebuild: content changed, so the static dist/ must be regenerated.
    # bun run build is 3-5x faster than npx astro build on cold caches; on
    # warm caches both finish in seconds. A failed build must NOT be silently
    # swallowed — operators need to see it. We still don't exit the watcher
    # (content loop keeps running), but we write a failure marker and tail
    # the error into build.log so the state is visible via `ls` or
    # `systemctl status git-sync-*`.
    TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    echo "=== $TS build start ===" >> "$BUILD_LOG"
    if bun run build >> "$BUILD_LOG" 2>&1; then
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
git pull origin main --quiet 2>/dev/null || true
# bun install + bun run build — 3-5x faster cold install than npm; package.json
# `build` script still points at `astro build`, so this works without touching
# the scaffold's script definitions.
bun install --silent
bun run build
echo "[build] Done — $(date)"
BUILD
  chmod +x /usr/local/bin/site-build

  # Mark system phases complete
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
      --password "$GITEA_ADMIN_PASS" 2>/dev/null \
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
      warn "Gitea admin ${GITEA_ADMIN_USER} still not working (status=${AUTH_VERIFY}) — Phase 11 will skip repo creation"
    fi
  else
    skip "Gitea admin ${GITEA_ADMIN_USER} verified"
  fi
fi

# =============================================================================
# PHASE 9: PROJECT SITE DIR + ASTRO TEMPLATE (per-project, idempotent)
# =============================================================================
log "Phase 9/12: Project ${PROJECT_NAME} site_dir at ${SITE_DIR}"

mkdir -p "${SITE_DIR}/dist"

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
    "dev": "astro dev --host 0.0.0.0",
    "build": "astro build",
    "preview": "astro preview --host 0.0.0.0",
    "check": "astro check"
  },
  "dependencies": {
    "astro": "^5.2.0",
    "@astrojs/react": "^4.2.0",
    "@astrojs/mdx": "^4.0.0",
    "@astrojs/check": "^0.9.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "sharp": "^0.33.0",
    "typescript": "^5.7.0"
  },
  "devDependencies": {
    "@tailwindcss/vite": "^4.0.0",
    "@tailwindcss/typography": "^0.5.0",
    "tailwindcss": "^4.0.0"
  }
}
PKGJSON

   cat > astro.config.mjs << 'ASTROCONF'
import { defineConfig } from "astro/config";
import react from "@astrojs/react";
import mdx from "@astrojs/mdx";
import tailwindcss from "@tailwindcss/vite";
export default defineConfig({
  output: "static",
  integrations: [
    react(),
    mdx(),
  ],
  vite: { plugins: [tailwindcss()] },
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
  }
}
TSCONF

  mkdir -p src/styles
  cat > src/styles/global.css << 'CSS'
@import "tailwindcss";
@import "./theme.css";
@plugin "@tailwindcss/typography";
CSS

  cat > src/styles/theme.css << 'CSS'
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
import "../styles/global.css";
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

  mkdir -p src/content/pages
  cat > src/content.config.ts << 'TS'
import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";
const pages = defineCollection({
  loader: glob({ pattern: "**/*.mdx", base: "./src/content/pages" }),
  schema: z.object({
    title: z.string(),
    description: z.string().optional(),
    image: z.string().optional(),
  }),
});
export const collections = { pages };
TS

  # Seed a placeholder content entry so the glob loader finds something
  cat > src/content/pages/welcome.mdx << 'MD'
---
title: Welcome
description: Placeholder page — agents customize per project
---
# Welcome
This site was scaffolded by the pipeline.
MD

  mkdir -p src/components/sections src/components/ui src/assets public pipeline

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
.opencode/
.env
# Lockfiles are regenerated per-deploy by the auto-rebuild watcher; not part of
# the source-of-truth repo for this static-site pipeline.
bun.lockb
package-lock.json
GI

  # Initial install only — no scaffold build. The scaffold's stub components
  # are guaranteed to produce a build, but it's wasted work because Phase 4
  # immediately replaces them with real code. The placeholder dist/index.html
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

# Always write a placeholder index.html if dist is empty (covers fresh dir)
if [[ ! -f "${SITE_DIR}/dist/index.html" ]]; then
  mkdir -p "${SITE_DIR}/dist"
  echo "<h1>Ready for ${PROJECT_NAME}</h1>" > "${SITE_DIR}/dist/index.html"
fi

# =============================================================================
# PHASE 10: PROJECT CADDY SITE FRAGMENT (idempotent)
# =============================================================================
log "Phase 10/12: Caddy site fragment for ${PROJECT_NAME}"

# Remove legacy Caddy default BEFORE creating our site fragment.
# This MUST happen here (not earlier) because Phase 4 may have just created
# legacy.caddy by migrating the default Caddyfile. If we remove it at the
# top of the script, Phase 4 recreates it later and the conflict persists.
# In plain-IP mode with port 80, legacy.caddy's :80 block conflicts with
# our project's :80 block, causing Caddy to serve the default welcome page.
if [[ "$SITE_PORT" == "80" && -f /etc/caddy/sites/legacy.caddy ]]; then
  rm -f /etc/caddy/sites/legacy.caddy
  warn "Removed legacy.caddy — port 80 now serves ${PROJECT_NAME}"
fi

CADDY_SITE_FILE="/etc/caddy/sites/${PROJECT_NAME}.caddy"
if [[ -f "$CADDY_SITE_FILE" && "$FORCE_PROJECT" != "true" ]]; then
  skip "Caddy site fragment exists — preserving: $CADDY_SITE_FILE"
else
  if [[ "$USE_TLS" == true ]]; then
    # Vhost-routed: multiple projects coexist, each on its own hostname.
    cat > "$CADDY_SITE_FILE" << CEOF
# Site: ${PROJECT_NAME}  (url: ${SITE_URL})
${SITE_HOST} {
    root * ${SITE_DIR}/dist
    file_server
    encode gzip zstd
    header {
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        -Server
    }
}
CEOF
  else
    # Plain-IP mode: each project listens on its own port (SITE_PORT).
    # Port is auto-assigned or pinned via PROJECT_PORT (see resolve block above).
    cat > "$CADDY_SITE_FILE" << CEOF
# Site: ${PROJECT_NAME}  (url: ${SITE_URL})
:${SITE_PORT} {
    root * ${SITE_DIR}/dist
    file_server
    encode gzip zstd
    header {
        X-Content-Type-Options "nosniff"
        -Server
    }
}
CEOF
    # Open the ports in the firewall (idempotent)
    ufw allow "${SITE_PORT}/tcp" >/dev/null 2>&1 || true
  fi
fi

# Validate and reload Caddy
# IMPORTANT: Validate the main Caddyfile (which imports all fragments),
# not the individual fragment — a fragment alone is not a valid Caddyfile.
if caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
  systemctl reload caddy 2>/dev/null || systemctl restart caddy
else
  # Non-fatal: site fragment is preserved on disk; Caddy just doesn't reload.
  # The orchestrator can fix the config and reload manually.
  warn "Caddy config invalid after adding ${PROJECT_NAME} fragment — skipping reload"
  warn "Fragment saved at ${CADDY_SITE_FILE} — fix and run: caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile && systemctl reload caddy"
fi

# =============================================================================
# PHASE 11: GITEA REPO (idempotent via API)
# =============================================================================
log "Phase 11/12: Gitea repo ${PROJECT_NAME}"

GITEA_API="http://127.0.0.1:3000/api/v1"
AUTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -u "${GITEA_ADMIN_USER}:${GITEA_ADMIN_PASS}" "${GITEA_API}/user" 2>/dev/null || echo "000")
if [[ "$AUTH_STATUS" != "200" ]]; then
  warn "Gitea credentials invalid for ${GITEA_ADMIN_USER} (status=${AUTH_STATUS}) — skipping repo creation (non-fatal)"
  GITEA_AUTH_OK=false
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
log "Phase 12/12: Git-sync watcher for ${PROJECT_NAME}"

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
# PERMISSIONS / OWNERSHIP
# =============================================================================
chmod 750 /etc/gitea 2>/dev/null || true
chmod 640 /etc/gitea/app.ini 2>/dev/null || true

if id -u debian >/dev/null 2>&1; then
  chown -R debian:debian "${SITE_DIR}"
fi

# Mark project complete
date -u +"%Y-%m-%dT%H:%M:%SZ site_dir=${SITE_DIR} url=${SITE_URL}" > "$PROJECT_MARKER"

# =============================================================================
# OUTPUT — machine-readable for the control node to parse
# =============================================================================
GENERATED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
NODE_VERSION=$(node --version 2>/dev/null || echo NONE)
BUN_VERSION=$(bun --version 2>/dev/null || echo NONE)
SYSTEM_BOOTSTRAPPED=$([ -f "$BOOTSTRAP_MARKER" ] && echo YES || echo NO)
SYSTEM_PHASES_RUN=$($SYSTEM_NEEDED && echo YES || echo NO)
GITEA_REPO_URL="${GITEA_PUBLIC_URL}/${GITEA_ADMIN_USER}/${PROJECT_NAME}.git"
GITEA_REPO_SSH="ssh://git@${SERVER_IP}/home/git/gitea-repositories/${GITEA_ADMIN_USER}/${PROJECT_NAME}.git"

jq -n   --arg schema_version "astro-static-bootstrap-result/v1"   --arg project_name "$PROJECT_NAME"   --arg server_ip "$SERVER_IP"   --arg domain "$DOMAIN"   --argjson use_tls "$( [[ "$USE_TLS" == "true" ]] && printf 'true' || printf 'false' )"   --arg site_dir "$SITE_DIR"   --arg site_host "$SITE_HOST"   --arg site_port "${SITE_PORT:-}"   --arg site_url "$SITE_URL"   --arg gitea_url "$GITEA_PUBLIC_URL"   --arg gitea_user "$GITEA_ADMIN_USER"   --arg gitea_repo_url "$GITEA_REPO_URL"   --arg gitea_repo_ssh "$GITEA_REPO_SSH"   --arg node_version "$NODE_VERSION"   --arg bun_version "$BUN_VERSION"   --arg system_bootstrapped "$SYSTEM_BOOTSTRAPPED"   --arg system_phases_run "$SYSTEM_PHASES_RUN"   --arg caddy_site_file "$CADDY_SITE_FILE"   --arg generated_at "$GENERATED_AT"   '{
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
    node_version: $node_version,
    bun_version: $bun_version,
    system_bootstrapped: $system_bootstrapped,
    system_phases_run: $system_phases_run,
    caddy_site_file: $caddy_site_file,
    generated_at: $generated_at
  }' > "$RESULT_PATH"
chmod 0644 "$RESULT_PATH"

cat << RESULT
===PIPELINE_RESULT===
RESULT_JSON=${RESULT_PATH}
SERVER_IP=${SERVER_IP}
SITE_DIR=${SITE_DIR}
SITE_URL=${SITE_URL}
GITEA_URL=${GITEA_PUBLIC_URL}
GITEA_ADMIN_USER=${GITEA_ADMIN_USER}
GITEA_ADMIN_PASS=[redacted]
PROJECT_NAME=${PROJECT_NAME}
===END_RESULT===
RESULT

# Final Caddy reload — earlier phases may have skipped reload due to validation
# failures caused by legacy.caddy conflicts. Now that legacy.caddy is removed
# (Phase 10) and all fragments are in place, try one more time.
if caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
  systemctl reload caddy 2>/dev/null || systemctl restart caddy
  log "Final Caddy reload successful — all site fragments active"
else
  warn "Final Caddy validation still failing — Caddy may need manual config fix"
  warn "Run: caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile"
fi

log "VPS setup complete for ${PROJECT_NAME} (system_phases_run=$($SYSTEM_NEEDED && echo yes || echo no))"
