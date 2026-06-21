#!/usr/bin/env python3
from __future__ import annotations

import json
import os
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
        (pipeline / "vps-connection.json").write_text(json.dumps({
            "schema_version": "1.0",
            "project_name": "demo-site",
            "ssh_host": "example.com",
            "ssh_port": 22,
            "ssh_user": "debian",
            "ssh_key": "/Users/demo/.ssh/id_ed25519",
        }))
        phase = {"status": "completed"}
        (pipeline / "00-pipeline-state.json").write_text(json.dumps({
            "project_name": "demo-site",
            "started_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "needs_human_review": False,
            "review_file": None,
            "phases": {
                "0_bootstrap": dict(phase),
                "1_design_extraction": dict(phase),
                "2_research": dict(phase),
                "2_5_brief_validation": dict(phase),
                "3_asset_generation": dict(phase),
                "3_5_image_generation": dict(phase),
                "3_6_video_generation": dict(phase),
                "_bootstrap_join": dict(phase),
                "4_frontend_build": dict(phase),
                "5_deploy": dict(phase),
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
        (project / "tina/config.ts").write_text(
            'import { LocalAuthProvider, defineConfig } from "tinacms";\n'
            'export default defineConfig({ clientId: null, token: null, authProvider: new LocalAuthProvider(), contentApiUrlOverride: "/api/tina/gql", schema: { collections: [{ name: "page", path: "src/content/page", ui: { router: () => "/" }, fields: [{ name: "title", type: "string" }, { name: "bullets", type: "string", list: true }, { name: "heroVideo", type: "string" }] }] } });\n'
        )
        (project / "src/pages/tina-island").mkdir(parents=True)
        (project / "src/pages/tina-island/[name].ts").write_text("export const prerender = false;\n")
        (project / "src/pages/api/tina").mkdir(parents=True)
        (project / "src/pages/api/tina/[...routes].ts").write_text("export const prerender = false;\n")
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

    def test_frontend_builder_uses_site_build_so_ssr_restarts(self) -> None:
        text = (AGENTS / "frontend-builder.md").read_text()
        self.assertIn('/usr/local/bin/site-build', text)
        self.assertIn('REMOTE_BUILD_CMD=', text)
        self.assertNotIn('bun install --silent && bun run check && bun run build', text)

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
            self.assertIn("LocalAuthProvider", result.stdout)

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
            (project / "tina/config.ts").write_text(
                'import { LocalAuthProvider, defineConfig } from "tinacms";\n'
                'export default defineConfig({ clientId: null, token: null, authProvider: new LocalAuthProvider(), contentApiUrlOverride: "/api/tina/gql", schema: { collections: [{ name: "page", path: "src/content/page", ui: { router: () => "/" }, fields: [] }] } });\n'
            )
            (project / "src/pages/tina-island").mkdir(parents=True)
            (project / "src/pages/tina-island/[name].ts").write_text("export const prerender = false;\n")
            (project / "src/pages/api/tina").mkdir(parents=True)
            (project / "src/pages/api/tina/[...routes].ts").write_text("export const prerender = false;\n")
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


if __name__ == "__main__":
    unittest.main()
