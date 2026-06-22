#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
AGENTS = ROOT.parent / "agents" / "astro-static"


class AstroStaticRegressionTests(unittest.TestCase):
    def _write_valid_dist_shell(self, dist: Path) -> None:
        (dist / "assets").mkdir(exist_ok=True)
        (dist / "assets/style.css").write_text(":root{--color-primary: red; --font-body: sans-serif}")
        (dist / "index.html").write_text(
            '<html><head><title>Demo</title><link href="/assets/style.css" rel="stylesheet"></head>'
            '<body><main>Demo</main></body></html>'
        )

    def _write_minimal_pipeline_project(self, project: Path, theme_css: str) -> None:
        pipeline = project / "pipeline"
        pipeline.mkdir()
        (project / "src/styles").mkdir(parents=True)
        (project / "src/layouts").mkdir(parents=True)
        (project / "src/assets").mkdir(parents=True)
        (project / "public").mkdir()
        (project / "src/styles/theme.css").write_text(theme_css)
        (project / "src/layouts/BaseLayout.astro").write_text('---\nimport "../styles/theme.css";\n---\n<slot />')
        for path in [
            "src/assets/logo.png",
            "public/favicon.ico",
            "public/favicon-32x32.png",
            "public/favicon-16x16.png",
            "public/apple-touch-icon.png",
            "public/og-image.png",
        ]:
            target = project / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"placeholder")
        (pipeline / "00-brief.json").write_text(json.dumps({
            "schema_version": "1.0",
            "project_name": "demo-site",
            "client_name": "Demo",
            "site_type": "landing",
        }))
        (pipeline / "01-creative-brief.json").write_text(json.dumps({
            "schema_version": "1.0",
            "client_name": "Demo",
            "site_type": "landing",
            "brand_personality": {},
            "content_structure": {"pages": [{"name": "Home", "slug": "/", "purpose": "Demo"}]},
            "competitive_analysis": {},
            "recommendations": {},
            "review_flags": [],
            "content_model": {"collections": []},
            "color_direction": {},
            "typography_direction": {},
        }))
        (pipeline / "02-font-config.json").write_text(json.dumps({
            "schema_version": "1.0",
            "heading": {"family": "Inter", "google_url": "https://fonts.googleapis.com/css2?family=Inter&display=swap"},
            "body": {"family": "Inter", "google_url": "https://fonts.googleapis.com/css2?family=Inter&display=swap"},
        }))
        (pipeline / "02-asset-manifest.json").write_text(json.dumps({
            "schema_version": "1.0",
            "logo": {"source": "generated", "primary_path": "src/assets/logo.png", "png": "src/assets/logo.png"},
            "favicon": {
                "ico": "public/favicon.ico",
                "png_32": "public/favicon-32x32.png",
                "png_16": "public/favicon-16x16.png",
                "apple_touch": "public/apple-touch-icon.png",
            },
            "og_image": {"path": "public/og-image.png"},
            "theme": {"css": "src/styles/theme.css"},
            "font_config": "pipeline/02-font-config.json",
            "content_images": [],
            "video_backgrounds": [],
        }))
        vps_connection = pipeline / "vps-connection.json"
        vps_connection.write_text(json.dumps({
            "schema_version": "1.0",
            "project_name": "demo-site",
            "ssh_host": "example.com",
            "ssh_port": 22,
            "ssh_user": "debian",
            "ssh_key": "/Users/demo/.ssh/id_ed25519",
        }))
        vps_connection.chmod(0o600)
        phase = {"status": "completed"}
        (pipeline / "00-pipeline-state.json").write_text(json.dumps({
            "project_name": "demo-site",
            "started_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "needs_human_review": False,
            "review_file": None,
            "phases": {
                "0_bootstrap_launch": dict(phase),
                "1_design_extraction": dict(phase),
                "2_research": dict(phase),
                "2_5_brief_validation": dict(phase),
                "3_asset_generation": dict(phase),
                "3_5_image_generation": dict(phase),
                "3_6_video_generation": dict(phase),
                "3_8_hyperframes_hero_optional": dict(phase),
                "4_1_frontend_codegen": dict(phase),
                "4_2_tinacms_local_build": dict(phase),
                "4_3_build_deploy": dict(phase),
                "5_publish_result": dict(phase),
            },
        }))

    def _write_minimal_tina_project(self, project: Path) -> None:
        self._write_minimal_pipeline_project(
            project,
            '@import "tailwindcss";\n@theme { --color-background: oklch(0.94 0.01 140); --font-body: "Inter"; }\n',
        )
        (project / "package.json").write_text(json.dumps({
            "dependencies": {"astro": "^6.4.8", "@tinacms/astro": "^0.5.0", "tinacms": "^3.9.3"},
            "devDependencies": {},
        }))
        (project / "astro.config.mjs").write_text(
            'import tina from "@tinacms/astro/integration";\n'
            'import { tinaAdminDevRedirect } from "@tinacms/astro/vite";\n'
            'import node from "@astrojs/node";\n'
            'export default { integrations: [tina()], vite: { plugins: [tinaAdminDevRedirect()] }, adapter: node({ mode: "standalone" }) };\n'
        )
        (project / "tina").mkdir()
        (project / "src/content/pages").mkdir(parents=True)
        (project / "tina/config.ts").write_text(
            'import { AbstractAuthProvider, defineConfig } from "tinacms";\n'
            'class PasswordAuthProvider extends AbstractAuthProvider { authenticate(){} getUser(){ return fetch("/api/tina/auth-check") } getToken(){ return { id_token: "" } } logout(){ return fetch("/api/tina/logout", { method: "POST" }) } }\n'
            'export default defineConfig({ clientId: null, token: null, authProvider: new PasswordAuthProvider(), contentApiUrlOverride: "/api/tina/gql", build: { outputFolder: "admin", publicFolder: "." }, schema: { collections: [{ name: "page", path: "src/content/pages", ui: { router: () => "/" }, fields: [{ name: "title", type: "string" }, { name: "bullets", type: "string", list: true }, { name: "heroVideo", type: "string" }] }] } });\n'
        )
        (project / "src/pages/tina-island").mkdir(parents=True)
        (project / "src/pages/tina-island/[name].ts").write_text("export const prerender = false;\n")
        (project / "src/pages/api/tina").mkdir(parents=True)
        (project / "src/pages/api/tina/[...routes].ts").write_text(
            'export const prerender = false;\n'
            'const SESSION_COOKIE = "tina_admin_session";\n'
            'function PasswordBackendAuthProvider() { return { isAuthorized: async () => ({ isAuthorized: true }) }; }\n'
            'export const POST = "/api/tina/login";\n'
            'export const LOGOUT = "/api/tina/logout";\n'
            'export const CHECK = "/api/tina/auth-check";\n'
        )
        (project / "src/lib/tina").mkdir(parents=True)
        (project / "src/lib/tina/data.ts").write_text(
            'import { requestWithMetadata } from "@tinacms/astro/data";\n'
            'import { tinaField } from "@tinacms/astro/tina-field";\n'
            'export { requestWithMetadata, tinaField };\n'
        )
        (project / "src/components").mkdir(parents=True, exist_ok=True)
        (project / "src/components/Editable.astro").write_text('---\nconst field = "page.title";\n---\n<h1 data-tina-field={field}>{{title}}</h1>\n')

    def test_asset_fallback_images_writes_manifest_path_and_lqip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "pipeline").mkdir()
            manifest = {
                "schema_version": "1.0",
                "logo": {"source": "generated", "primary_path": "src/assets/logo.png"},
                "favicon": {
                    "ico": "public/favicon.ico",
                    "png_32": "public/favicon-32x32.png",
                    "png_16": "public/favicon-16x16.png",
                    "apple_touch": "public/apple-touch-icon.png",
                },
                "og_image": {"path": "public/og-image.png"},
                "theme": {"css": "src/styles/theme.css"},
                "font_config": "pipeline/02-font-config.json",
                "content_images": [],
                "video_backgrounds": [],
            }
            shot_list = {
                "schema_version": "1.0",
                "project_name": "demo-site",
                "images": [
                    {
                        "id": "hero-background",
                        "type": "hero",
                        "prompt": "hero",
                        "output_path": "src/assets/images/hero-background.webp",
                        "dimensions": "1920x1080",
                    }
                ],
            }
            (project / "pipeline/02-asset-manifest.json").write_text(json.dumps(manifest))
            (project / "pipeline/02-image-shot-list.json").write_text(json.dumps(shot_list))

            result = subprocess.run(
                ["bash", str(ROOT / "phases" / "asset-fallbacks.sh"), "images"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            updated = json.loads((project / "pipeline/02-asset-manifest.json").read_text())
            entry = updated["content_images"][0]
            self.assertEqual(entry["path"], "src/assets/images/hero-background.svg")
            self.assertNotIn("output_path", entry)
            self.assertTrue((project / entry["path"]).is_file())
            self.assertTrue((project / "src/assets/images/hero-background.lqip.txt").is_file())

    def test_orchestrator_validates_manifest_content_image_path_key(self) -> None:
        text = (AGENTS / "astro-static" / "orchestrator.md").read_text() if (AGENTS / "astro-static" / "orchestrator.md").exists() else (AGENTS / "orchestrator.md").read_text()
        self.assertIn(".content_images[].path", text)
        self.assertNotIn(".content_images[].output_path", text)

    def test_design_extractor_reference_path_is_not_duplicated(self) -> None:
        text = (AGENTS / "design-extractor.md").read_text()
        self.assertIn("`references/reference-stack.md`", text)
        self.assertNotIn("references/references/reference-stack.md", text)

    def test_smoke_accepts_href_before_rel_stylesheet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            (dist / "assets").mkdir()
            (dist / "assets/style.css").write_text(":root{--color-primary: red; --font-body: sans-serif}")
            (dist / "about").mkdir()
            (dist / "about/index.html").write_text("about")
            (dist / "index.html").write_text(
                '<html><head><title>Demo</title><link href="/assets/style.css" rel="stylesheet"></head>'
                '<body><nav><a href="/about/">About</a></nav></body></html>'
            )
            result = subprocess.run(
                ["bash", str(ROOT / "phases" / "smoke.sh")],
                cwd=dist,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_smoke_rejects_mp4_video_poster(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            self._write_valid_dist_shell(dist)
            (dist / "videos").mkdir()
            (dist / "videos/clip.mp4").write_bytes(b"0" * 150_000)
            (dist / "index.html").write_text(
                '<html><head><title>Demo</title><link href="/assets/style.css" rel="stylesheet"></head>'
                '<body><video src="/videos/clip.mp4" poster="/videos/clip.mp4"></video></body></html>'
            )
            result = subprocess.run(["bash", str(ROOT / "phases" / "smoke.sh")], cwd=dist, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("video_poster_is_video", result.stdout)

    def test_smoke_rejects_static_video_poster_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            self._write_valid_dist_shell(dist)
            (dist / "videos").mkdir()
            (dist / "images").mkdir()
            (dist / "videos/clip.mp4").write_bytes(b"0" * 150_000)
            (dist / "images/poster.webp").write_bytes(b"poster")
            (dist / "index.html").write_text(
                '<html><head><title>Demo</title><link href="/assets/style.css" rel="stylesheet"></head>'
                '<body><img class="video-bg__poster" src="/images/poster.webp"><video src="/videos/clip.mp4" poster="/images/poster.webp"></video></body></html>'
            )
            result = subprocess.run(["bash", str(ROOT / "phases" / "smoke.sh")], cwd=dist, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("video_static_poster_layer", result.stdout)

    def test_smoke_detects_tina_project_root_from_dist_client(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            dist = project / "dist/client"
            dist.mkdir(parents=True)
            self._write_valid_dist_shell(dist)
            (project / "tina").mkdir()
            (project / "tina/config.ts").write_text("export default {};\n")

            result = subprocess.run(["bash", str(ROOT / "phases" / "smoke.sh")], cwd=dist, text=True, capture_output=True)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("admin_spa_missing", result.stdout)

    def test_validator_rejects_unscaled_oklch_lightness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_pipeline_project(
                project,
                '@import "tailwindcss";\n@theme { --color-background: oklch(9.4 0.01 140); --font-body: "Inter"; }\n',
            )
            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid oklch() lightness", result.stdout)

    def test_setup_vps_scaffold_uses_latest_astro6_tina_stack(self) -> None:
        text = (ROOT / "setup-vps.sh").read_text()
        for expected in [
            '"astro": "^6.4.8"',
            '"@astrojs/node": "^10.1.4"',
            '"@astrojs/mdx": "^6.0.3"',
            '"@astrojs/react": "^5.0.7"',
            '"@tinacms/astro": "^0.5.0"',
            '"tinacms": "^3.9.3"',
            '"@tinacms/cli": "^2.5.1"',
            '"tailwindcss": "^4.3.1"',
        ]:
            self.assertIn(expected, text)
        self.assertIn('adapter: node({ mode: "standalone" })', text)
        self.assertIn('tinaAdminDevRedirect()', text)

    def test_setup_vps_provisions_tina_ssr_backend_consistently(self) -> None:
        text = (ROOT / "setup-vps.sh").read_text()
        self.assertNotRegex(text, r"Phase [0-9.]+/12")
        for expected in [
            'log "Phase 13/13: TinaCMS Astro SSR service for ${PROJECT_NAME}"',
            'ASTRO_SSR_PORT',
            'astro-ssr-${PROJECT_NAME}',
            'ExecStart=/usr/bin/env node ${SITE_DIR}/dist/server/entry.mjs',
            'root * ${SITE_DIR}/dist/client',
            'handle /tina-island/*',
            'handle /api/tina/*',
            'reverse_proxy 127.0.0.1:${ASTRO_SSR_PORT}',
            'dist/client/index.html',
            'astro_ssr_port: ($astro_ssr_port | tonumber)',
            'astro_ssr_unit: $astro_ssr_unit',
            'UNIT="astro-ssr-$(basename "$SITE_DIR")"',
            'sudo -n systemctl restart "$UNIT"',
            'bun run check',
        ]:
            self.assertIn(expected, text)
        self.assertNotIn('dist/index.html', text)

    def test_setup_vps_scaffold_implements_tina_password_auth_contract(self) -> None:
        text = (ROOT / "setup-vps.sh").read_text()
        for expected in [
            "class PasswordAuthProvider",
            "authProvider: new PasswordAuthProvider()",
            "function PasswordBackendAuthProvider",
            "POST /api/tina/login",
            "POST /api/tina/logout",
            "GET /api/tina/auth-check",
            "tina_admin_session",
            'Content-Security-Policy "frame-ancestors',
        ]:
            self.assertIn(expected, text)
        self.assertNotIn('LocalBackendAuthProvider', text)
        self.assertNotIn('X-Frame-Options "DENY"', text)

    def test_tinacms_local_build_requires_login_and_bridge_artifacts(self) -> None:
        text = (ROOT / "phases/tinacms-local-build.sh").read_text()
        self.assertIn('fail "no_admin_login_html"', text)
        self.assertIn('fail "no_tina_bridge"', text)

    def test_frontend_builder_is_local_codegen_only(self) -> None:
        text = (AGENTS / "frontend-builder.md").read_text()
        self.assertIn('local codegen only', text)
        self.assertIn('STATUS:FRONTEND_CODEGEN_OK', text)
        self.assertNotIn('/usr/local/bin/site-build', text)
        self.assertNotIn('REMOTE_BUILD_CMD=', text)
        self.assertNotIn('rsync -avz', text)
        self.assertNotIn('ssh -p', text)
        self.assertNotIn('bun install --silent && bun run check && bun run build', text)

    def test_tinacms_local_build_is_local_only(self) -> None:
        text = (ROOT / "phases/tinacms-local-build.sh").read_text()
        self.assertNotIn('vps-connection.json', text)
        self.assertNotIn('rsync', text)
        self.assertNotIn('systemctl restart', text)
        self.assertNotIn('SSH_CMD', text)

    def test_orchestrator_uses_site_build_so_ssr_restarts(self) -> None:
        text = (AGENTS / "orchestrator.md").read_text()
        self.assertIn('/usr/local/bin/site-build', text)
        self.assertIn('reason=astro_ssr_restart', text)
        self.assertNotIn('timeout 180 bun install --silent', text)
        self.assertNotIn('timeout 180 bun run check', text)
        self.assertNotIn('timeout 300 bun run build', text)

    def test_validator_requires_tina_files_when_tina_dependency_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_pipeline_project(
                project,
                '@import "tailwindcss";\n@theme { --color-background: oklch(0.94 0.01 140); --font-body: "Inter"; }\n',
            )
            (project / "package.json").write_text(json.dumps({
                "dependencies": {"astro": "^6.4.8", "@tinacms/astro": "^0.5.0", "tinacms": "^3.9.3"},
                "devDependencies": {},
            }))
            (project / "astro.config.mjs").write_text("export default {}")

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("tina/config.ts", result.stdout)
            self.assertIn("src/pages/tina-island/[name].ts", result.stdout)
            self.assertIn("src/pages/api/tina/[...routes].ts", result.stdout)

    def test_validator_rejects_tina_config_without_self_hosted_auth_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_pipeline_project(
                project,
                '@import "tailwindcss";\n@theme { --color-background: oklch(0.94 0.01 140); --font-body: "Inter"; }\n',
            )
            (project / "package.json").write_text(json.dumps({
                "dependencies": {"astro": "^6.4.8", "@tinacms/astro": "^0.5.0", "tinacms": "^3.9.3"},
                "devDependencies": {},
            }))
            (project / "astro.config.mjs").write_text(
                'import tina from "@tinacms/astro/integration";\n'
                'import { tinaAdminDevRedirect } from "@tinacms/astro/vite";\n'
                'import node from "@astrojs/node";\n'
                'export default { integrations: [tina()], vite: { plugins: [tinaAdminDevRedirect()] }, adapter: node({ mode: "standalone" }) };\n'
            )
            (project / "tina").mkdir()
            (project / "tina/config.ts").write_text(
                'import { defineConfig } from "tinacms";\n'
                'export default defineConfig({ clientId: null, token: null, contentApiUrlOverride: "/api/tina/gql", schema: { collections: [] } });\n'
            )
            (project / "src/pages/tina-island").mkdir(parents=True)
            (project / "src/pages/tina-island/[name].ts").write_text("export const prerender = false;\n")
            (project / "src/pages/api/tina").mkdir(parents=True)
            (project / "src/pages/api/tina/[...routes].ts").write_text("export const prerender = false;\n")

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("PasswordAuthProvider", result.stdout)

    def test_validator_rejects_tina_local_auth_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "tina/config.ts").write_text(
                'import { LocalAuthProvider, defineConfig } from "tinacms";\n'
                'export default defineConfig({ clientId: null, token: null, authProvider: new LocalAuthProvider(), contentApiUrlOverride: "/api/tina/gql", build: { outputFolder: "admin", publicFolder: "." }, schema: { collections: [{ name: "page", path: "src/content/pages", ui: { router: () => "/" }, fields: [] }] } });\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("LocalAuthProvider is not allowed", result.stdout)
            self.assertIn("PasswordAuthProvider", result.stdout)

    def test_validator_rejects_tina_api_without_password_auth_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "src/pages/api/tina/[...routes].ts").write_text("export const prerender = false;\n")

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("/api/tina/login", result.stdout)
            self.assertIn("/api/tina/logout", result.stdout)
            self.assertIn("/api/tina/auth-check", result.stdout)

    def test_validator_requires_tina_click_to_edit_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_pipeline_project(
                project,
                '@import "tailwindcss";\n@theme { --color-background: oklch(0.94 0.01 140); --font-body: "Inter"; }\n',
            )
            (project / "package.json").write_text(json.dumps({
                "dependencies": {"astro": "^6.4.8", "@tinacms/astro": "^0.5.0", "tinacms": "^3.9.3"},
                "devDependencies": {},
            }))
            (project / "astro.config.mjs").write_text(
                'import tina from "@tinacms/astro/integration";\n'
                'import { tinaAdminDevRedirect } from "@tinacms/astro/vite";\n'
                'import node from "@astrojs/node";\n'
                'export default { integrations: [tina()], vite: { plugins: [tinaAdminDevRedirect()] }, adapter: node({ mode: "standalone" }) };\n'
            )
            (project / "tina").mkdir()
            (project / "src/content/pages").mkdir(parents=True)
            (project / "tina/config.ts").write_text(
                'import { AbstractAuthProvider, defineConfig } from "tinacms";\n'
                'class PasswordAuthProvider extends AbstractAuthProvider { authenticate(){} getUser(){ return fetch("/api/tina/auth-check") } getToken(){ return { id_token: "" } } logout(){ return fetch("/api/tina/logout", { method: "POST" }) } }\n'
                'export default defineConfig({ clientId: null, token: null, authProvider: new PasswordAuthProvider(), contentApiUrlOverride: "/api/tina/gql", build: { outputFolder: "admin", publicFolder: "." }, schema: { collections: [{ name: "page", path: "src/content/pages", ui: { router: () => "/" }, fields: [] }] } });\n'
            )
            (project / "src/pages/tina-island").mkdir(parents=True)
            (project / "src/pages/tina-island/[name].ts").write_text("export const prerender = false;\n")
            (project / "src/pages/api/tina").mkdir(parents=True)
            (project / "src/pages/api/tina/[...routes].ts").write_text(
                'export const prerender = false;\n'
                'const SESSION_COOKIE = "tina_admin_session";\n'
                'function PasswordBackendAuthProvider() { return { isAuthorized: async () => ({ isAuthorized: true }) }; }\n'
                'export const POST = "/api/tina/login";\n'
                'export const LOGOUT = "/api/tina/logout";\n'
                'export const CHECK = "/api/tina/auth-check";\n'
            )
            (project / "src/lib/tina").mkdir(parents=True)
            (project / "src/lib/tina/data.ts").write_text('import { requestWithMetadata } from "@tinacms/astro/data";\nexport { requestWithMetadata };\n')

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("data-tina-field", result.stdout)

    def test_validator_rejects_hardcoded_visible_text_in_tina_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "src/components/HardcodedCopy.astro").write_text(
                '---\nconst title = "Editable";\n---\n<section><h2>Hardcoded marketing promise</h2><p data-tina-field={title}>{title}</p></section>\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("hardcoded visible text", result.stdout)
            self.assertIn("Hardcoded marketing promise", result.stdout)

    def test_validator_rejects_typewriter_text_without_tina_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "src/components/MissingField.astro").write_text(
                '---\nconst operatorName = "Demo GmbH";\n---\n<footer><span data-typewriter>{operatorName}</span></footer>\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("data-typewriter text node is missing data-tina-field", result.stdout)

    def test_validator_rejects_hardcoded_tina_media_elements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "src/components/HardcodedMedia.astro").write_text(
                '<section><VideoBackground src="/videos/hero.mp4" poster="/videos/poster.webp" /></section>\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("hardcoded media path", result.stdout)
            self.assertIn("/videos/hero.mp4", result.stdout)

    def test_validator_rejects_hardcoded_service_bullet_arrays(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "src/pages/index.astro").write_text(
                '---\nconst cards = [{ bullets: ["NAS setup", "Access control"] }];\n---\n<div data-tina-field="page.title">{cards.length}</div>\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("hardcoded service bullet array", result.stdout)

    def test_validator_rejects_img_without_tina_field_in_tina_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            # Dynamic src bypasses the hardcoded-path check so only the
            # data-tina-field requirement is exercised.
            (project / "src/components/Gallery.astro").write_text(
                '---\nconst photo = "photo-123.webp";\nconst alt = "Demo";\n---\n<section><img src={photo} alt={alt} /></section>\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("img element missing data-tina-field", result.stdout)

    def test_validator_rejects_content_images_usage_without_tina_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "src/components/HeroBg.astro").write_text(
                '---\nimport { contentImages } from "../lib/content-images";\n'
                'const heroBg = contentImages["hero-background"];\n---\n'
                '<section><img src={heroBg.src.src} alt="" /></section>\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("contentImages", result.stdout)
            self.assertIn("Tina image field override", result.stdout)

    def test_validator_accepts_content_images_with_tina_override_and_field(self) -> None:
        """contentImages is fine IF the component also accepts a Tina image prop,
        resolves Tina-first, and renders data-tina-field on the image node."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "src/components/HeroBg.astro").write_text(
                '---\nimport { contentImages } from "../lib/content-images";\n'
                'const { bgImage, fields = {} } = Astro.props;\n'
                'const fallback = contentImages["hero-background"];\n'
                'const src = bgImage ?? fallback.src.src;\n---\n'
                '<section><img src={src} alt="" data-tina-field={fields.bgImage} /></section>\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_validator_accepts_img_with_data_static_media_escape(self) -> None:
        """Decorative images that are intentionally non-editable (icons, avatars)
        pass when marked data-static-media."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "src/components/Icon.astro").write_text(
                '<img src="/images/icon.svg" alt="" data-static-media />\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_pipeline_contract_exists_and_schema_uses_canonical_phase_ids(self) -> None:
        contract = AGENTS / "references" / "pipeline-contract.md"
        self.assertTrue(contract.is_file(), "pipeline-contract.md is the canonical phase graph")
        contract_text = contract.read_text()
        schema = json.loads((AGENTS / "schemas" / "00-pipeline-state.schema.json").read_text())
        phase_props = set(schema["properties"]["phases"]["properties"].keys())
        required = set(schema["properties"]["phases"]["required"])
        expected = {
            "0_bootstrap_launch",
            "1_design_extraction",
            "2_research",
            "2_5_brief_validation",
            "3_asset_generation",
            "3_5_image_generation",
            "3_6_video_generation",
            "3_8_hyperframes_hero_optional",
            "4_1_frontend_codegen",
            "4_2_tinacms_local_build",
            "4_3_build_deploy",
            "5_publish_result",
        }
        self.assertTrue(expected.issubset(phase_props))
        self.assertEqual(expected, required)
        for phase_id in expected:
            self.assertIn(f"`{phase_id}`", contract_text)
        for legacy in ["0_bootstrap", "_bootstrap_join", "4_frontend_build", "5_deploy"]:
            self.assertNotIn(f'"{legacy}"', json.dumps(schema))

    def test_no_obsolete_space_status_grammar_in_astro_static_agents(self) -> None:
        offenders: list[str] = []
        pattern = re.compile(r"STATUS:\s+(?:OK|FAILED)\b")
        for path in AGENTS.rglob("*.md"):
            text = path.read_text()
            if pattern.search(text):
                offenders.append(str(path.relative_to(AGENTS)))
        self.assertEqual(offenders, [], "Use STATUS:<TOKEN> with no space after colon")

    def test_bootstrap_result_fetch_uses_owner_only_channel(self) -> None:
        setup = (ROOT / "setup-vps.sh").read_text()
        join = (ROOT / "phases" / "bootstrap-join.sh").read_text()
        self.assertIn('umask 077', setup)
        self.assertIn('RESULT_PATH="${STATE_DIR}/pipeline-result.json"', setup)
        self.assertIn('chmod 0600 "$RESULT_PATH"', setup)
        self.assertNotIn('chmod 0644 "$RESULT_PATH"', setup)
        self.assertNotIn('sudo chmod 644 /tmp/pipeline-result.json', join)
        self.assertNotIn(':/tmp/pipeline-result.json" pipeline/bootstrap-result.json', join)
        self.assertIn('sudo cat /var/lib/site-pipeline/pipeline-result.json', join)
        self.assertIn('chmod 600 pipeline/bootstrap-result.json', join)

    def test_setup_vps_skips_root_ssh_lockout_hardening_without_deploy_user(self) -> None:
        text = (ROOT / "setup-vps.sh").read_text()
        self.assertIn('Direct root invocation has no verified non-root deploy user', text)
        self.assertNotIn("Verify root's authorized_keys", text)

    def test_result_template_redacts_secret_values(self) -> None:
        text = (AGENTS / "orchestrator.md").read_text()
        self.assertNotIn("TinaCMS Admin Password:** <TINA_ADMIN_PASSWORD", text)
        self.assertNotIn("Gitea Password:** <gitea_pass", text)
        self.assertIn("Credentials are not printed", text)
        self.assertIn("pipeline/vps-connection.json", text)

    def test_validator_rejects_open_secret_file_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_pipeline_project(
                project,
                '@import "tailwindcss";\n@theme { --color-background: oklch(0.94 0.01 140); --font-body: "Inter"; }\n',
            )
            (project / "pipeline/vps-connection.json").chmod(0o644)

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("secret file permissions", result.stdout)
            self.assertIn("0600", result.stdout)

    def test_validator_rejects_asset_path_traversal_and_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_pipeline_project(
                project,
                '@import "tailwindcss";\n@theme { --color-background: oklch(0.94 0.01 140); --font-body: "Inter"; }\n',
            )
            manifest_path = project / "pipeline/02-asset-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["logo"]["primary_path"] = "../secrets/logo.png"
            manifest["content_images"] = [{"id": "bad", "path": "/etc/passwd", "status": "generated"}]
            manifest_path.write_text(json.dumps(manifest))

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "assets", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe artifact path", result.stdout)
            self.assertIn("absolute paths are not allowed", result.stdout)
            self.assertIn("path traversal is not allowed", result.stdout)

    def test_bootstrap_join_rejects_invalid_json_shell_values_before_ssh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            pipeline = project / "pipeline"
            pipeline.mkdir()
            (pipeline / "bootstrap.exit").write_text("0\n")
            vps_connection = pipeline / "vps-connection.json"
            vps_connection.write_text(json.dumps({
                "schema_version": "1.0",
                "project_name": "demo-site",
                "ssh_host": "bad;host",
                "ssh_port": 22,
                "ssh_user": "debian",
                "ssh_key": "/Users/demo/.ssh/id_ed25519",
            }))
            vps_connection.chmod(0o600)

            result = subprocess.run(
                ["bash", str(ROOT / "phases/bootstrap-join.sh")],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("STATUS:INVALID_VPS_CONFIG reason=bad_ssh_host", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
