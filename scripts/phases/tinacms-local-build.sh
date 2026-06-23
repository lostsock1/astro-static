#!/usr/bin/env bash
# Phase 4.2: TinaCMS Admin SPA Local Build
#
# Builds the TinaCMS admin SPA on the control node (Mac).
# The VPS (2GB RAM) OOM-kills esbuild during `tinacms build`, so the admin SPA
# must be built locally and left for the build-deployer phase to publish.
#
# Prerequisites:
#   - tina/config.ts exists in the project root
#   - Node.js + npm/bun available on the control node
#
# Output:
#   - admin/index.html + admin/assets/*
#   - tina/__generated__/* (TinaCMS generated schema/types)
#   - STATUS:TINACMS_BUILD_OK  (success)
#   - STATUS:TINACMS_BUILD_FAILED reason=<...>
#
# Usage:
#   cd <project_root>
#   bash ~/.config/opencode/astro-static/phases/tinacms-local-build.sh

set -euo pipefail

PROJECT_DIR="$(pwd)"

# --- helpers ---
log() { echo "[tinacms-local-build] $*"; }
fail() { echo "STATUS:TINACMS_BUILD_FAILED reason=$*"; exit 1; }

# --- preflight ---
[ -f "$PROJECT_DIR/tina/config.ts" ] || fail "no_tina_config"

if grep -q 'return (await fetch("/api/tina/auth-check")).ok' "$PROJECT_DIR/tina/config.ts" \
  || ! grep -q 'name:' "$PROJECT_DIR/tina/config.ts"; then
  fail "auth_user_shape_missing"
fi

ISLAND_ROUTE="$PROJECT_DIR/src/pages/tina-island/[name].ts"
[ -f "$ISLAND_ROUTE" ] || fail "no_tina_island_route"
grep -q 'export const POST' "$ISLAND_ROUTE" || fail "island_route_must_export_post"
! grep -q 'export const ALL' "$ISLAND_ROUTE" || fail "island_route_must_export_post"

# --- step 1: ensure dependencies are installed ---
log "Installing dependencies (if needed)..."
if [ ! -d "$PROJECT_DIR/node_modules" ]; then
  (cd "$PROJECT_DIR" && bun install --silent 2>&1 | tail -3) || \
    (cd "$PROJECT_DIR" && npm install --silent 2>&1 | tail -3) || \
    fail "install_failed"
fi

# --- step 2: build TinaCMS admin SPA locally ---
log "Building TinaCMS admin SPA locally..."

# The build script in package.json now only runs `astro build`.
# We call tinacms build directly with --local --skip-cloud-checks.
BUILD_OUTPUT=$(cd "$PROJECT_DIR" && npx tinacms build --local --skip-cloud-checks 2>&1) || {
  echo "$BUILD_OUTPUT"
  fail "tinacms_build_failed"
}

# --- step 3: verify admin SPA output ---
log "Verifying admin SPA output..."

# CRITICAL: tinacms build generates a .gitignore inside admin/ that ignores
# index.html and assets/. In our pipeline, the admin SPA MUST be committed
# to git or handed to build-deployer because the VPS cannot build it (OOM). Remove the generated .gitignore
# so git tracks the actual admin files.
rm -f "$PROJECT_DIR/admin/.gitignore"
[ ! -f "$PROJECT_DIR/admin/.gitignore" ] || fail "admin_gitignore_still_present"

# Copy the TinaCMS bridge.js from node_modules to the admin/ directory.
# The @tinacms/astro integration normally copies this during 'astro build' to
# dist/client/admin/bridge.js, but since Caddy serves /admin/* from the project
# root admin/ (not dist/client/admin/), and the local build doesn't run astro
# build, we copy it here so it is ready for the build-deployer phase.
# IMPORTANT: Must resolve @tinacms/bridge (the actual bundled 15KB runtime),
# NOT @tinacms/astro/dist/bridge.js (which is just a 50-byte re-export stub).
BRIDGE_SRC="$PROJECT_DIR/node_modules/@tinacms/bridge/dist/index.js"
if [ -f "$BRIDGE_SRC" ]; then
  cp "$BRIDGE_SRC" "$PROJECT_DIR/admin/bridge.js"
  log "Copied bridge.js ($(wc -c < "$PROJECT_DIR/admin/bridge.js") bytes) to admin/"
else
  fail "no_tina_bridge"
fi

BRIDGE_SIZE=$(wc -c < "$PROJECT_DIR/admin/bridge.js" | tr -d '[:space:]')
[ "$BRIDGE_SIZE" -gt 1000 ] || fail "tina_bridge_too_small size_bytes=$BRIDGE_SIZE"

[ -f "$PROJECT_DIR/admin/index.html" ] || fail "no_admin_index_html"
[ -d "$PROJECT_DIR/admin/assets" ] || fail "no_admin_assets_dir"

ADMIN_SIZE=$(du -sk "$PROJECT_DIR/admin" | cut -f1)
[ "$ADMIN_SIZE" -gt 50 ] || fail "admin_too_small size_kb=$ADMIN_SIZE"

log "Admin SPA built: ${ADMIN_SIZE}KB at $PROJECT_DIR/admin/"

# --- step 3.5: ensure admin/login.html exists (password auth gate) ---
# The login page is a static HTML form that POSTs to /api/tina/login.
# The backend auth provider checks TINA_ADMIN_PASSWORD env var.
if [ ! -f "$PROJECT_DIR/admin/login.html" ]; then
  if [ -f "$PROJECT_DIR/public/admin/login.html" ]; then
    cp "$PROJECT_DIR/public/admin/login.html" "$PROJECT_DIR/admin/login.html"
    log "Copied login.html from public/admin/ to admin/"
  else
    fail "no_admin_login_html"
  fi
fi

# --- step 4: verify generated schema (needed by databaseClient.ts at runtime) ---
if [ -f "$PROJECT_DIR/tina/__generated__/_schema.json" ]; then
  SCHEMA_SIZE=$(du -k "$PROJECT_DIR/tina/__generated__/_schema.json" | cut -f1)
  [ "$SCHEMA_SIZE" -gt 1 ] || fail "schema_too_small"
  log "Generated schema verified: ${SCHEMA_SIZE}KB"
else
  fail "no_generated_schema"
fi

log "Done. Admin and generated schema are ready for build-deployer."
echo "STATUS:TINACMS_BUILD_OK"
