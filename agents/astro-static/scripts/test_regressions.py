#!/usr/bin/env python3
from __future__ import annotations

import base64
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AGENTS = (
    ROOT / "agents" / "astro-static"
    if (ROOT / "agents" / "astro-static").exists()
    else ROOT.parent
    if (ROOT.parent / "schemas").exists() and (ROOT.parent / "README.md").exists()
    else ROOT.parent / "agents" / "astro-static"
)
COMMANDS = AGENTS.parent.parent / "commands"


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
        (pipeline / "01-tina-blueprint.json").write_text(json.dumps(self._valid_tina_blueprint()))
        (pipeline / "03-tina-coverage.json").write_text(json.dumps(self._valid_tina_coverage()))
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
                "2_6_tina_blueprint": dict(phase),
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

    def _valid_tina_blueprint(self) -> dict:
        return {
            "schema_version": "astro-static-tina-blueprint/v1",
            "project_name": "demo-site",
            "settings": {
                "siteName": "Demo",
                "tagline": "Demo site",
                "nav": [{"label": "Home", "href": "/"}],
                "footerLinks": [],
                "copyrightText": "© Demo",
                "seo": {"title": "Demo", "description": "Demo site"},
            },
            "pages": [{
                "id": "home",
                "slug": "/",
                "title": "Home",
                "sections": [{
                    "id": "hero-home",
                    "type": "hero",
                    "fields": [
                        {"name": "headline", "field_type": "string", "source_default": "Demo"},
                        {"name": "backgroundImage", "field_type": "image", "source_default": "/images/hero.webp"},
                    ],
                }],
            }],
            "collections": [],
            "blocks": [{
                "type": "hero",
                "label": "Hero",
                "renderer": "HeroBlock",
                "fields": ["headline", "backgroundImage"],
            }],
            "media_fields": [{
                "field_ref": "pages.home.sections.hero-home.backgroundImage",
                "field_type": "image",
                "owner": "block",
                "source_default": "/images/hero.webp",
                "tina_field_path": "sections[0].backgroundImage",
                "content_path": "src/content/pages/home.json.sections[0].backgroundImage",
                "render_intent": "hero background image",
                "required_marker": "data-tina-field",
                "surface_kind": "background_image",
            }],
            "editable_surface_map": [
                {
                    "field_ref": "settings.siteName",
                    "field_type": "string",
                    "owner": "settings",
                    "source_default": "Demo",
                    "tina_field_path": "siteName",
                    "content_path": "src/content/settings/site.json.siteName",
                    "render_intent": "site header brand text",
                    "required_marker": "data-tina-field",
                    "surface_kind": "text",
                },
                {
                    "field_ref": "settings.nav[0].label",
                    "field_type": "string",
                    "owner": "settings",
                    "source_default": "Home",
                    "tina_field_path": "nav[0].label",
                    "content_path": "src/content/settings/site.json.nav[0].label",
                    "render_intent": "header navigation label",
                    "required_marker": "data-tina-field",
                    "surface_kind": "text",
                },
                {
                    "field_ref": "settings.copyrightText",
                    "field_type": "string",
                    "owner": "settings",
                    "source_default": "© Demo",
                    "tina_field_path": "copyrightText",
                    "content_path": "src/content/settings/site.json.copyrightText",
                    "render_intent": "footer copyright text",
                    "required_marker": "data-tina-field",
                    "surface_kind": "text",
                },
                {
                    "field_ref": "pages.home.sections.hero-home.headline",
                    "field_type": "string",
                    "owner": "block",
                    "source_default": "Demo",
                    "tina_field_path": "sections[0].headline",
                    "content_path": "src/content/pages/home.json.sections[0].headline",
                    "render_intent": "hero headline text",
                    "required_marker": "data-tina-field",
                    "surface_kind": "text",
                },
                {
                    "field_ref": "pages.home.sections.hero-home.backgroundImage",
                    "field_type": "image",
                    "owner": "block",
                    "source_default": "/images/hero.webp",
                    "tina_field_path": "sections[0].backgroundImage",
                    "content_path": "src/content/pages/home.json.sections[0].backgroundImage",
                    "render_intent": "hero background image",
                    "required_marker": "data-tina-field",
                    "surface_kind": "background_image",
                },
            ],
        }

    def _valid_tina_coverage(self) -> dict:
        blueprint = self._valid_tina_blueprint()
        coverage = []
        for surface in blueprint["editable_surface_map"]:
            coverage.append({
                "field_ref": surface["field_ref"],
                "declared_in_blueprint": True,
                "tina_schema_path": "tina/config.ts",
                "astro_schema_path": "src/content.config.ts",
                "content_file": surface["content_path"].split(".json", 1)[0] + ".json",
                "renderer_file": "src/components/tina/blocks/HeroBlock.astro",
                "island_name": "hero-home" if surface["owner"] == "block" else "settings-site",
                "has_tina_field_marker": surface["required_marker"] == "data-tina-field",
                "surface_kind": surface["surface_kind"],
            })
        return {
            "schema_version": "astro-static-tina-coverage/v1",
            "project_name": "demo-site",
            "coverage": coverage,
        }

    def _write_blueprint_creative_brief(self, pipeline: Path, sections: list[str] | None = None) -> None:
        (pipeline / "01-creative-brief.json").write_text(json.dumps({
            "schema_version": "astro-static-creative-brief/v1",
            "project_name": "demo-site",
            "client_name": "Demo",
            "site_type": "landing",
            "tagline": "Make the whole page editable",
            "brand_personality": {},
            "content_structure": {
                "pages": [{
                    "name": "Home",
                    "slug": "/",
                    "purpose": "Convert visitors",
                    "sections": sections or [
                        "Hero with headline, deck, CTA, and editable background image",
                        "Feature grid with three repeated feature cards",
                        "Gallery of editable image cards",
                        "Final CTA section with button",
                    ],
                }],
            },
            "competitive_analysis": {},
            "recommendations": {"cta_strategy": "Book a demo"},
            "review_flags": [],
            "content_model": {"collections": []},
            "color_direction": {},
            "typography_direction": {},
        }))

    def _load_validate_pipeline_module(self) -> Any:
        module_name = "astro_static_validate_pipeline_under_test"
        spec = importlib.util.spec_from_file_location(module_name, ROOT / "validate-pipeline.py")
        if spec is None or spec.loader is None:
            self.fail("could not load validate-pipeline.py module")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def _write_minimal_tina_project(self, project: Path) -> None:
        self._write_minimal_pipeline_project(
            project,
            '@import "tailwindcss";\n@theme { --color-background: oklch(0.94 0.01 140); --font-body: "Inter"; }\n',
        )
        (project / "package.json").write_text(json.dumps({
            "dependencies": {
                "astro": "^7.0.2",
                "@astrojs/node": "^11.0.0",
                "@astrojs/mdx": "^7.0.0",
                "@astrojs/react": "^6.0.0",
                "@tailwindcss/vite": "^4.3.1",
                "tailwindcss": "^4.3.1",
                "@tinacms/astro": "^0.5.0",
                "tinacms": "^3.9.3",
            },
            "devDependencies": {"@tinacms/cli": "^2.5.1"},
        }))
        (project / ".gitignore").write_text(
            "node_modules/\ndist/\n.astro/\n.opencode/\n.env\npipeline/vps-connection.json\npipeline/vps-connection.json.*\npipeline/.git-credentials\npipeline/bootstrap*.log\n"
            ".env.*\n*.log\npipeline/bootstrap-result.json\npipeline/bootstrap-result.json.*\npipeline/bootstrap*.json\npipeline/bootstrap*.pid\npipeline/bootstrap*.exit\n"
            "pipeline/installation-summary.md\npipeline/installation.log\npipeline/setup-wrapper.*\npipeline/RESULT.md\npipeline/HUMAN_REVIEW.md\n"
        )
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
            'class PasswordAuthProvider extends AbstractAuthProvider { authenticate(){} async getUser(){ const response = await fetch("/api/tina/auth-check"); if (!response.ok) return false; return { name: "Site Admin", email: "admin@localhost" }; } getToken(){ return { id_token: "" } } logout(){ return fetch("/api/tina/logout", { method: "POST" }) } }\n'
            'export default defineConfig({ clientId: null, token: null, authProvider: new PasswordAuthProvider(), contentApiUrlOverride: "/api/tina/gql", build: { outputFolder: "admin", publicFolder: "." }, schema: { collections: [{ name: "page", path: "src/content/pages", ui: { router: () => "/" }, fields: [{ name: "title", type: "string" }, { name: "bullets", type: "string", list: true }, { name: "heroVideo", type: "string" }] }] } });\n'
        )
        (project / "tsconfig.json").write_text(json.dumps({
            "extends": "astro/tsconfigs/strict",
            "exclude": ["admin/**", "dist/**", "node_modules/**"],
        }))
        (project / "src/pages/tina-island").mkdir(parents=True)
        (project / "src/pages/tina-island/[name].ts").write_text(
            'import { experimental_createIslandRoute } from "@tinacms/astro/experimental";\n'
            'const islands = { page: { fetch: async () => ({}), component: (() => null) as any, wrapper: { tag: "main" }, propsFromData: () => ({}) } };\n'
            'export const prerender = false;\n'
            'export const POST = experimental_createIslandRoute(islands);\n'
        )
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
                        "field_ref": "pages.home.sections.hero-home.backgroundImage",
                        "content_path": "src/content/pages/home.json.sections[0].backgroundImage",
                        "tina_default_value": "/images/hero-background.webp",
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
            self.assertEqual(entry["field_ref"], "pages.home.sections.hero-home.backgroundImage")
            self.assertEqual(entry["content_path"], "src/content/pages/home.json.sections[0].backgroundImage")
            self.assertEqual(entry["tina_default_value"], "/images/hero-background.webp")
            self.assertNotIn("output_path", entry)
            self.assertTrue((project / entry["path"]).is_file())
            self.assertTrue((project / "src/assets/images/hero-background.lqip.txt").is_file())

    def test_validator_rejects_placeholder_only_content_images_when_instagram_assets_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_pipeline_project(
                project,
                '@import "tailwindcss";\n@theme { --color-background: oklch(0.94 0.01 140); --font-body: "Inter"; }\n',
            )
            brief_path = project / "pipeline/00-brief.json"
            brief = json.loads(brief_path.read_text())
            brief.update({
                "instagram_handle": "demo_profile",
                "instagram_use": "both",
                "reference_urls": ["https://www.instagram.com/demo_profile/"],
            })
            brief_path.write_text(json.dumps(brief))

            ig_assets = project / "pipeline/00-instagram/assets"
            ig_assets.mkdir(parents=True)
            for i in range(3):
                (ig_assets / f"post-{i + 1:03d}.jpg").write_bytes(b"\xff\xd8" + (b"real-instagram-photo" * 1024) + b"\xff\xd9")

            placeholder = project / "src/assets/images/hero-background.svg"
            placeholder.parent.mkdir(parents=True, exist_ok=True)
            placeholder.write_text('<svg aria-label="hero placeholder"></svg>')
            manifest_path = project / "pipeline/02-asset-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["content_images"] = [
                {"id": "hero-background", "path": "src/assets/images/hero-background.svg", "status": "placeholder"}
            ]
            manifest_path.write_text(json.dumps(manifest))

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "assets", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Instagram assets", result.stdout)
            self.assertIn("placeholder", result.stdout)

    def test_phase_35_prefers_instagram_assets_before_ppq_generation(self) -> None:
        orchestrator = (AGENTS / "orchestrator.md").read_text()
        self.assertIn("Prefer scraped Instagram assets before PPQ generation", orchestrator)
        self.assertIn("pipeline/00-instagram/assets", orchestrator)
        self.assertIn("status: \"scraped_instagram\"", orchestrator)

    def test_phase_36_requires_instagram_stills_for_ai_animated_backgrounds(self) -> None:
        orchestrator = (AGENTS / "orchestrator.md").read_text()
        asset_generator = (AGENTS / "asset-generator.md").read_text()
        vid_gen = (AGENTS / "vid-gen.md").read_text()
        for text in [orchestrator, asset_generator, vid_gen]:
            self.assertIn("Instagram", text)
            self.assertIn("image-to-video", text)
        self.assertIn("source_image_public_path", orchestrator)
        self.assertIn("AI-animated", orchestrator)

    def test_frontend_builder_documents_editable_background_media_contract(self) -> None:
        text = (AGENTS / "frontend-builder.md").read_text()
        self.assertIn("Hardcoded public media/background paths", text)
        self.assertIn("bgImage", text)
        self.assertIn("data-tina-field", text)

    def test_validator_rejects_instagram_video_without_image_to_video_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_pipeline_project(
                project,
                '@import "tailwindcss";\n@theme { --color-background: oklch(0.94 0.01 140); --font-body: "Inter"; }\n',
            )
            brief_path = project / "pipeline/00-brief.json"
            brief = json.loads(brief_path.read_text())
            brief.update({
                "instagram_handle": "demo_profile",
                "instagram_use": "both",
                "reference_urls": ["https://www.instagram.com/demo_profile/"],
            })
            brief_path.write_text(json.dumps(brief))
            creative_path = project / "pipeline/01-creative-brief.json"
            creative = json.loads(creative_path.read_text())
            creative["motion_direction"] = {"video_backgrounds": True}
            creative_path.write_text(json.dumps(creative))

            ig_assets = project / "pipeline/00-instagram/assets"
            ig_assets.mkdir(parents=True)
            for i in range(3):
                (ig_assets / f"post-{i + 1:03d}.jpg").write_bytes(b"\xff\xd8" + (b"real-instagram-photo" * 1024) + b"\xff\xd9")

            poster = project / "src/assets/images/hero-background.jpg"
            poster.parent.mkdir(parents=True, exist_ok=True)
            poster.write_bytes(b"\xff\xd8" + (b"selected-instagram-photo" * 1024) + b"\xff\xd9")
            video = project / "public/videos/hero-bg.mp4"
            video.parent.mkdir(parents=True, exist_ok=True)
            video.write_bytes(b"0" * 150_000)
            manifest_path = project / "pipeline/02-asset-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["content_images"] = [{
                "id": "hero-background",
                "path": "src/assets/images/hero-background.jpg",
                "status": "scraped_instagram",
                "source": "instagram_scrape",
                "source_path": "pipeline/00-instagram/assets/post-001.jpg",
                "public_path": "/images/instagram/hero-background.jpg",
            }]
            manifest["video_backgrounds"] = [{
                "id": "hero-background-video",
                "type": "hero-bg",
                "output_path": "public/videos/hero-bg.mp4",
                "poster_path": "src/assets/images/hero-background.jpg",
                "duration": "5",
                "aspect_ratio": "16:9",
                "status": "generated",
                "image_url": None,
            }]
            manifest_path.write_text(json.dumps(manifest))

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "assets", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("image-to-video", result.stdout)
            self.assertIn("Instagram", result.stdout)

    def test_validator_accepts_instagram_video_with_image_to_video_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_pipeline_project(
                project,
                '@import "tailwindcss";\n@theme { --color-background: oklch(0.94 0.01 140); --font-body: "Inter"; }\n',
            )
            brief_path = project / "pipeline/00-brief.json"
            brief = json.loads(brief_path.read_text())
            brief.update({
                "instagram_handle": "demo_profile",
                "instagram_use": "both",
                "reference_urls": ["https://www.instagram.com/demo_profile/"],
            })
            brief_path.write_text(json.dumps(brief))
            creative_path = project / "pipeline/01-creative-brief.json"
            creative = json.loads(creative_path.read_text())
            creative["motion_direction"] = {"video_backgrounds": True}
            creative_path.write_text(json.dumps(creative))

            ig_assets = project / "pipeline/00-instagram/assets"
            ig_assets.mkdir(parents=True)
            for i in range(3):
                (ig_assets / f"post-{i + 1:03d}.jpg").write_bytes(b"\xff\xd8" + (b"real-instagram-photo" * 1024) + b"\xff\xd9")

            poster = project / "src/assets/images/hero-background.jpg"
            poster.parent.mkdir(parents=True, exist_ok=True)
            poster.write_bytes(b"\xff\xd8" + (b"selected-instagram-photo" * 1024) + b"\xff\xd9")
            video = project / "public/videos/hero-bg.mp4"
            video.parent.mkdir(parents=True, exist_ok=True)
            video.write_bytes(b"0" * 150_000)
            manifest_path = project / "pipeline/02-asset-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["content_images"] = [{
                "id": "hero-background",
                "path": "src/assets/images/hero-background.jpg",
                "status": "scraped_instagram",
                "source": "instagram_scrape",
                "source_path": "pipeline/00-instagram/assets/post-001.jpg",
                "public_path": "/images/instagram/hero-background.jpg",
            }]
            manifest["video_backgrounds"] = [{
                "id": "hero-background-video",
                "type": "hero-bg",
                "output_path": "public/videos/hero-bg.mp4",
                "poster_path": "src/assets/images/hero-background.jpg",
                "duration": "5",
                "aspect_ratio": "16:9",
                "status": "generated",
                "image_url": "https://scontent-lhr8-1.xx.fbcdn.net/v/t51.2885-15/demo.jpg?stp=dst-jpg_e35",
            }]
            manifest_path.write_text(json.dumps(manifest))

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "assets", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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

    def test_setup_vps_scaffold_uses_latest_astro7_tina_stack(self) -> None:
        text = (ROOT / "setup-vps.sh").read_text()
        for expected in [
            '"astro": "^7.0.2"',
            '"@astrojs/node": "^11.0.0"',
            '"@astrojs/mdx": "^7.0.0"',
            '"@astrojs/react": "^6.0.0"',
            '"@tinacms/astro": "^0.5.0"',
            '"tinacms": "^3.9.3"',
            '"@tinacms/cli": "^2.5.1"',
            '"tailwindcss": "^4.3.1"',
        ]:
            self.assertIn(expected, text)
        self.assertIn('adapter: node({ mode: "standalone" })', text)
        self.assertIn('tinaAdminDevRedirect()', text)
        self.assertIn('import { z } from "astro/zod";', text)
        self.assertNotIn('import { defineCollection, z } from "astro:content";', text)
        self.assertNotIn('src/fetch.ts', text)

    def test_reference_stack_documents_astro7_strict_html_risks(self) -> None:
        text = (AGENTS / "references" / "reference-stack.md").read_text()
        for expected in ["Astro 7", "Vite 8", "Rust compiler", "src/fetch.ts", "invalid HTML"]:
            self.assertIn(expected, text)
        self.assertIn("does not make content editable", text)

    def test_reference_stack_uses_astro_zod_import_for_content_schemas(self) -> None:
        text = (AGENTS / "references" / "reference-stack.md").read_text()
        self.assertIn("import { z } from 'astro/zod';", text)
        self.assertNotIn("import { defineCollection, z } from 'astro:content';", text)
        self.assertNotIn('import { defineCollection, z } from "astro:content";', text)

    def test_frontend_builder_requires_blueprint_and_coverage_contract(self) -> None:
        text = (AGENTS / "frontend-builder.md").read_text()
        self.assertIn("pipeline/01-tina-blueprint.json", text)
        self.assertIn("pipeline/03-tina-coverage.json", text)
        self.assertIn("editable_surface_map", text)
        self.assertIn("Do not generate editable structure from `content_structure` prose", text)
        self.assertIn("STATUS:TINA_COVERAGE_WRITTEN", text)

    def test_asset_generator_and_shot_schemas_are_field_ref_aware(self) -> None:
        text = (AGENTS / "asset-generator.md").read_text()
        self.assertIn("pipeline/01-tina-blueprint.json", text)
        self.assertIn("media_fields", text)
        self.assertIn("field_ref", text)
        self.assertIn("tina_default_value", text)
        image_schema = json.loads((AGENTS / "schemas" / "02-image-shot-list.schema.json").read_text())
        video_schema = json.loads((AGENTS / "schemas" / "02-video-shot-list.schema.json").read_text())
        self.assertTrue({"field_ref", "content_path", "tina_default_value"}.issubset(set(image_schema["$defs"]["image"]["required"])))
        self.assertTrue({"field_ref", "content_path", "tina_default_value"}.issubset(set(video_schema["$defs"]["video"]["required"])))

    def test_image_shot_list_rejects_entries_without_field_ref_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_pipeline_project(
                project,
                '@import "tailwindcss";\n@theme { --color-background: oklch(0.94 0.01 140); --font-body: "Inter"; }\n',
            )
            (project / "pipeline/02-image-shot-list.json").write_text(json.dumps({
                "schema_version": "1.0",
                "project_name": "demo-site",
                "images": [{
                    "id": "hero-background",
                    "type": "hero",
                    "prompt": "hero",
                    "output_path": "src/assets/images/hero-background.webp",
                }],
            }))

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "assets", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("field_ref", result.stdout)

    def test_edit_site_command_invalidates_blueprint_and_coverage(self) -> None:
        text = (COMMANDS / "astro-static" / "edit-site.md").read_text()
        self.assertIn("pipeline/01-tina-blueprint.json", text)
        self.assertIn("pipeline/03-tina-coverage.json", text)
        self.assertIn("content model / IA / page-structure changes → invalidate `2_6_tina_blueprint`", text)
        self.assertIn("Tina coverage changes → rerun Phase 4.1", text)

    def test_new_site_command_runs_instagram_wizard(self) -> None:
        text = (COMMANDS / "astro-static" / "new-site.md").read_text()
        self.assertIn("Stage 1", text)
        self.assertIn("one stage at a time", text)
        self.assertIn("Confirm", text)
        self.assertIn("instagram_handle", text)
        self.assertIn("instagram_use", text)
        for use in ("design_reference", "brand_research", "content", "both"):
            self.assertIn(use, text)
        self.assertIn("generation report", text.lower())

    def test_orchestrator_emits_completion_report_and_credentials_handoff(self) -> None:
        text = (AGENTS / "orchestrator.md").read_text()
        self.assertIn("Generation Issue Ledger", text)
        self.assertIn("pipeline/generation-report.md", text)
        self.assertIn("Operator completion summary", text)
        self.assertIn("credentials", text.lower())
        self.assertIn("Never write credentials into `pipeline/RESULT.md`", text)
        self.assertIn("must never contain secrets", text)

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
            '@static_files',
            'reverse_proxy 127.0.0.1:${ASTRO_SSR_PORT}',
            'chmod 0644 "$CADDY_SITE_FILE"',
        ]:
            self.assertIn(expected, text)
        self.assertNotIn('dist/index.html', text)
        self.assertIn('err "Caddy config invalid after adding ${PROJECT_NAME} fragment"', text)
        self.assertIn('err "Final Caddy validation still failing', text)
        self.assertIn('if $SYSTEM_NEEDED; then\n  SYSTEM_PHASES_RUN=YES', text)
        self.assertNotIn('SYSTEM_PHASES_RUN=$($SYSTEM_NEEDED', text)

    def test_setup_vps_scaffold_implements_tina_password_auth_contract(self) -> None:
        text = (ROOT / "setup-vps.sh").read_text()
        for expected in [
            "class PasswordAuthProvider",
            "authProvider: new PasswordAuthProvider()",
            'return { name: "Site Admin", email: "admin@localhost" }',
            "function PasswordBackendAuthProvider",
            "POST /api/tina/login",
            "POST /api/tina/logout",
            "GET /api/tina/auth-check",
            "tina_admin_session",
            'Content-Security-Policy "frame-ancestors',
            'export const POST: APIRoute = experimental_createIslandRoute(islands);',
            '"exclude": ["admin/**", "dist/**", "node_modules/**"]',
        ]:
            self.assertIn(expected, text)
        self.assertIn('err "Gitea admin ${GITEA_ADMIN_USER} still not working', text)
        self.assertIn('err "Gitea credentials invalid for ${GITEA_ADMIN_USER}', text)
        self.assertNotIn('LocalBackendAuthProvider', text)
        self.assertNotIn('X-Frame-Options "DENY"', text)
        self.assertNotIn('export const ALL: APIRoute = experimental_createIslandRoute(islands);', text)

    def test_tinacms_local_build_requires_login_and_bridge_artifacts(self) -> None:
        text = (ROOT / "phases/tinacms-local-build.sh").read_text()
        self.assertIn('fail "no_admin_login_html"', text)
        self.assertIn('fail "no_tina_bridge"', text)
        self.assertIn('auth_user_shape_missing', text)
        self.assertIn('island_route_must_export_post', text)
        self.assertIn('admin_gitignore_still_present', text)

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

    def test_build_deployer_uses_ssr_entry_and_live_smoke_contract(self) -> None:
        text = (AGENTS / "build-deployer.md").read_text()
        self.assertIn('dist/server/entry.mjs', text)
        self.assertIn('BUILD_MODE=ssr', text)
        self.assertIn('SITE_URL=$(jq -r', text)
        self.assertIn('SITE_URL="$SITE_URL" SITE_DIR="$SITE_DIR"', text)
        self.assertIn('STATUS:BUILD_FAILED reason=no_build_output', text)
        self.assertIn("elif test -f '$SITE_DIR/dist/client/index.html'; then printf static", text)

    def test_validator_requires_tina_files_when_tina_dependency_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_pipeline_project(
                project,
                '@import "tailwindcss";\n@theme { --color-background: oklch(0.94 0.01 140); --font-body: "Inter"; }\n',
            )
            (project / "package.json").write_text(json.dumps({
                "dependencies": {"astro": "^7.0.2", "@tinacms/astro": "^0.5.0", "tinacms": "^3.9.3"},
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
                "dependencies": {"astro": "^7.0.2", "@tinacms/astro": "^0.5.0", "tinacms": "^3.9.3"},
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

    def test_validator_rejects_password_auth_get_user_boolean_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "tina/config.ts").write_text(
                'import { AbstractAuthProvider, defineConfig } from "tinacms";\n'
                'class PasswordAuthProvider extends AbstractAuthProvider { async getUser(){ try { return (await fetch("/api/tina/auth-check")).ok; } catch { return false; } } }\n'
                'export default defineConfig({ clientId: null, token: null, authProvider: new PasswordAuthProvider(), contentApiUrlOverride: "/api/tina/gql", build: { outputFolder: "admin", publicFolder: "." }, schema: { collections: [{ name: "page", path: "src/content/pages", ui: { router: () => "/" }, fields: [] }] } });\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("PasswordAuthProvider.getUser", result.stdout)
            self.assertIn("name", result.stdout)

    def test_validator_rejects_tina_island_all_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "src/pages/tina-island/[name].ts").write_text(
                'export const prerender = false;\nexport const ALL = experimental_createIslandRoute({});\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("tina-island", result.stdout)
            self.assertIn("POST", result.stdout)

    def test_validator_rejects_empty_tina_island_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "src/pages/tina-island/[name].ts").write_text(
                'import { experimental_createIslandRoute } from "@tinacms/astro/experimental";\n'
                'const islands = {};\n'
                'export const prerender = false;\n'
                'export const POST = experimental_createIslandRoute(islands);\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("island registry", result.stdout)

    def test_validator_rejects_tina_collection_format_extension_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "src/content/pages/home.md").write_text('---\ntitle: "Home"\n---\nBody\n')
            (project / "tina/config.ts").write_text(
                'import { AbstractAuthProvider, defineConfig } from "tinacms";\n'
                'class PasswordAuthProvider extends AbstractAuthProvider { async getUser(){ return { name: "Site Admin", email: "admin@localhost" }; } getToken(){ return { id_token: "" } } logout(){ return fetch("/api/tina/logout", { method: "POST" }) } }\n'
                'export default defineConfig({ clientId: null, token: null, authProvider: new PasswordAuthProvider(), contentApiUrlOverride: "/api/tina/gql", build: { outputFolder: "admin", publicFolder: "." }, schema: { collections: [{ name: "page", path: "src/content/pages", format: "mdx", ui: { router: () => "/" }, fields: [{ name: "title", type: "string" }] }] } });\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("format", result.stdout)
            self.assertIn("home.md", result.stdout)

    def test_validator_rejects_content_frontmatter_src_assets_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "src/content/pages/home.md").write_text(
                '---\ntitle: "Home"\nimage: "src/assets/images/hero.svg"\n---\nBody\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("src/assets", result.stdout)

    def test_validator_rejects_astro_content_page_without_request_with_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "src/pages").mkdir(exist_ok=True)
            (project / "src/pages/index.astro").write_text(
                '---\nimport { getCollection } from "astro:content";\nconst entries = await getCollection("pages");\n---\n<main><h1 data-tina-field="page.title">{entries.length}</h1></main>\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requestWithMetadata", result.stdout)
            self.assertIn("src/pages/index.astro", result.stdout)

    def test_validator_requires_tina_tsconfig_excludes_generated_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "tsconfig.json").write_text(json.dumps({"extends": "astro/tsconfigs/strict"}))

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("tsconfig.json", result.stdout)
            self.assertIn("admin/**", result.stdout)

    def test_validator_rejects_unsafe_gitignore_for_pipeline_push(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / ".gitignore").write_text("node_modules/\n")

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(".gitignore", result.stdout)
            self.assertIn("pipeline/vps-connection.json", result.stdout)

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

    def test_smoke_accepts_ssr_live_http_without_static_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            dist_client = project / "dist/client"
            dist_server = project / "dist/server"
            dist_client.mkdir(parents=True)
            dist_server.mkdir(parents=True)
            (dist_server / "entry.mjs").write_text("export default {};\n")
            (dist_client / "assets").mkdir()
            (dist_client / "assets/style.css").write_text(":root{--color-primary: red; --font-body: sans-serif}")
            live_root = project / "live"
            live_root.mkdir()
            (live_root / "index.html").write_text(
                '<html><head><title>SSR Demo</title><link href="/assets/style.css" rel="stylesheet"></head>'
                '<body><main>SSR Demo</main></body></html>'
            )
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            sock.close()
            server = subprocess.Popen(
                ["python3", "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                cwd=live_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                result = subprocess.run(
                    ["bash", str(ROOT / "phases" / "smoke.sh")],
                    cwd=project,
                    env={**os.environ, "SITE_URL": f"http://127.0.0.1:{port}", "SITE_DIR": str(project)},
                    text=True,
                    capture_output=True,
                    timeout=20,
                )
            finally:
                server.terminate()
                server.wait(timeout=5)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("STATUS:SMOKE_OK", result.stdout)

    def test_validator_requires_tina_click_to_edit_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_pipeline_project(
                project,
                '@import "tailwindcss";\n@theme { --color-background: oklch(0.94 0.01 140); --font-body: "Inter"; }\n',
            )
            (project / "package.json").write_text(json.dumps({
                "dependencies": {"astro": "^7.0.2", "@tinacms/astro": "^0.5.0", "tinacms": "^3.9.3"},
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

    def test_validator_rejects_hardcoded_copy_variables_in_tina_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "src/components/HardcodedHeroCopy.astro").write_text(
                '---\nconst heroTitle = "Come dance with us tonight";\n---\n<h1 data-tina-field="page.title">{heroTitle}</h1>\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("hardcoded copy variable", result.stdout)
            self.assertIn("heroTitle", result.stdout)

    def test_validator_rejects_data_static_copy_for_marketing_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "src/components/StaticCopyEscape.astro").write_text(
                '<section><h2 data-static-copy>Levando Canoa Pro Mundo</h2></section>\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("data-static-copy must be reserved", result.stdout)
            self.assertIn("Levando Canoa Pro Mundo", result.stdout)

    def test_validator_accepts_explicit_ui_static_copy_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "src/components/StaticUiCopy.astro").write_text(
                '<button data-static-copy="ui">Fechar</button>\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_validator_rejects_hardcoded_copy_in_object_arrays(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "src/components/HardcodedCards.astro").write_text(
                '---\nconst cards = [{ title: "Freedom na Estrada", desc: "De Canoa Quebrada para Rototom Sunsplash" }];\n---\n<section>{cards.map((card) => <h2>{card.title}</h2>)}</section>\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("hardcoded copy object field", result.stdout)
            self.assertIn("Freedom na Estrada", result.stdout)

    def test_validator_rejects_hardcoded_visible_component_props(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "src/components/HardcodedProps.astro").write_text(
                '<Footer brandName="FREEDOM BAR" tagline="Templo do Reggae — Canoa Quebrada" />\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("hardcoded visible component prop", result.stdout)
            self.assertIn("brandName", result.stdout)

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

    def test_validator_rejects_hardcoded_background_images_in_tina_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "src/components/HardcodedBackground.astro").write_text(
                '<section data-tina-field={fields.bgImage} style="background-image: url(\'/images/hero.jpg\')"></section>\n'
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("hardcoded background image", result.stdout)
            self.assertIn("/images/hero.jpg", result.stdout)

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
        self.assertFalse(schema["properties"]["phases"].get("additionalProperties"))
        expected = {
            "0_bootstrap_launch",
            "1_design_extraction",
            "2_research",
            "2_5_brief_validation",
            "2_6_tina_blueprint",
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

    def test_tina_blueprint_schema_accepts_valid_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_pipeline_project(
                project,
                '@import "tailwindcss";\n@theme { --color-background: oklch(0.94 0.01 140); --font-body: "Inter"; }\n',
            )

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "blueprint", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_tina_coverage_schema_accepts_valid_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_tina_coverage_rejects_missing_blueprint_field_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            coverage = self._valid_tina_coverage()
            coverage["coverage"] = [
                item for item in coverage["coverage"]
                if item["field_ref"] != "pages.home.sections.hero-home.backgroundImage"
            ]
            (project / "pipeline/03-tina-coverage.json").write_text(json.dumps(coverage))

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing coverage for blueprint field_ref", result.stdout)
            self.assertIn("pages.home.sections.hero-home.backgroundImage", result.stdout)

    def test_tina_coverage_is_required_for_build_phase(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_tina_project(project)
            (project / "pipeline/03-tina-coverage.json").unlink()

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "build", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("03-tina-coverage.json", result.stdout)

    def test_tina_blueprint_schema_rejects_missing_settings_nav_footer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_pipeline_project(
                project,
                '@import "tailwindcss";\n@theme { --color-background: oklch(0.94 0.01 140); --font-body: "Inter"; }\n',
            )
            blueprint = self._valid_tina_blueprint()
            blueprint["settings"].pop("nav")
            (project / "pipeline/01-tina-blueprint.json").write_text(json.dumps(blueprint))

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "blueprint", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("settings", result.stdout)
            self.assertIn("nav", result.stdout)

    def test_tina_blueprint_schema_rejects_visible_field_without_field_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_pipeline_project(
                project,
                '@import "tailwindcss";\n@theme { --color-background: oklch(0.94 0.01 140); --font-body: "Inter"; }\n',
            )
            blueprint = self._valid_tina_blueprint()
            blueprint["editable_surface_map"][0].pop("field_ref")
            (project / "pipeline/01-tina-blueprint.json").write_text(json.dumps(blueprint))

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "blueprint", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("field_ref", result.stdout)

    def test_tina_blueprint_schema_rejects_media_field_without_render_intent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_pipeline_project(
                project,
                '@import "tailwindcss";\n@theme { --color-background: oklch(0.94 0.01 140); --font-body: "Inter"; }\n',
            )
            blueprint = self._valid_tina_blueprint()
            blueprint["media_fields"][0].pop("render_intent")
            (project / "pipeline/01-tina-blueprint.json").write_text(json.dumps(blueprint))

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "blueprint", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("render_intent", result.stdout)

    def test_tina_blueprint_schema_rejects_static_exemption_without_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_pipeline_project(
                project,
                '@import "tailwindcss";\n@theme { --color-background: oklch(0.94 0.01 140); --font-body: "Inter"; }\n',
            )
            blueprint = self._valid_tina_blueprint()
            blueprint["editable_surface_map"].append({
                "field_ref": "ui.controls.closeLabel",
                "field_type": "string",
                "owner": "settings",
                "source_default": "Close",
                "tina_field_path": "ui.closeLabel",
                "content_path": "src/content/settings/site.json.ui.closeLabel",
                "render_intent": "static UI close button label",
                "required_marker": "static-exempt",
                "surface_kind": "text",
            })
            (project / "pipeline/01-tina-blueprint.json").write_text(json.dumps(blueprint))

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "blueprint", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("static_exemption_reason", result.stdout)

    def test_tina_blueprint_schema_rejects_duplicate_editable_surface_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self._write_minimal_pipeline_project(
                project,
                '@import "tailwindcss";\n@theme { --color-background: oklch(0.94 0.01 140); --font-body: "Inter"; }\n',
            )
            blueprint = self._valid_tina_blueprint()
            duplicate = dict(blueprint["editable_surface_map"][-1])
            duplicate["render_intent"] = "duplicate hero image alias"
            blueprint["editable_surface_map"].append(duplicate)
            (project / "pipeline/01-tina-blueprint.json").write_text(json.dumps(blueprint))

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "blueprint", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate field_ref", result.stdout)

    def test_tina_blueprint_schema_fails_closed_without_jsonschema_for_advanced_keywords(self) -> None:
        validator = self._load_validate_pipeline_module()
        validator.HAVE_JSONSCHEMA = False
        validator.Draft202012Validator = None
        schema = json.loads((AGENTS / "schemas" / "01-tina-blueprint.schema.json").read_text())
        issues = []

        validator.validate_value(
            self._valid_tina_blueprint(),
            schema,
            schema,
            "$",
            issues,
            "01-tina-blueprint.json",
        )

        self.assertTrue(
            any("jsonschema library required" in issue.message for issue in issues),
            [issue.message for issue in issues],
        )

    def test_tina_blueprint_generator_creates_schema_valid_blocks_and_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            pipeline = project / "pipeline"
            pipeline.mkdir()
            self._write_blueprint_creative_brief(pipeline)

            result = subprocess.run(
                ["python3", str(ROOT / "phases" / "tina-blueprint.py"), "generate", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("STATUS:TINA_BLUEPRINT_OK", result.stdout)

            blueprint = json.loads((pipeline / "01-tina-blueprint.json").read_text())
            block_types = [block["type"] for block in blueprint["blocks"]]
            self.assertEqual(block_types, ["hero", "featureGrid", "gallery", "cta"])
            self.assertEqual(blueprint["settings"]["siteName"], "Demo")
            self.assertIn("nav", blueprint["settings"])
            self.assertIn("footerLinks", blueprint["settings"])
            self.assertIn("copyrightText", blueprint["settings"])
            field_types = {surface["field_ref"]: surface["field_type"] for surface in blueprint["editable_surface_map"]}
            self.assertEqual(field_types["pages.home.sections.features-home.items"], "object-list")
            self.assertEqual(field_types["pages.home.sections.hero-home.backgroundImage"], "image")

            validate = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "blueprint", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )
            self.assertEqual(validate.returncode, 0, validate.stdout + validate.stderr)

    def test_tina_blueprint_generator_creates_unique_ids_for_repeated_section_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            pipeline = project / "pipeline"
            pipeline.mkdir()
            self._write_blueprint_creative_brief(
                pipeline,
                sections=[
                    "CTA section with button for bookings",
                    "Final CTA section with button for newsletter signup",
                ],
            )

            result = subprocess.run(
                ["python3", str(ROOT / "phases" / "tina-blueprint.py"), "generate", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            blueprint = json.loads((pipeline / "01-tina-blueprint.json").read_text())
            section_ids = [section["id"] for section in blueprint["pages"][0]["sections"]]
            field_refs = [surface["field_ref"] for surface in blueprint["editable_surface_map"]]
            tina_paths = [surface["tina_field_path"] for surface in blueprint["editable_surface_map"]]
            self.assertEqual(len(section_ids), len(set(section_ids)))
            self.assertEqual(len(field_refs), len(set(field_refs)))
            self.assertEqual(len(tina_paths), len(set(tina_paths)))
            self.assertIn("cta-home-2", section_ids)

    def test_tina_blueprint_generator_supports_initial_block_library(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            pipeline = project / "pipeline"
            pipeline.mkdir()
            self._write_blueprint_creative_brief(
                pipeline,
                sections=[
                    "Hero splash with background image",
                    "Split feature section with image and copy",
                    "Feature grid with benefit cards",
                    "Card grid for service cards",
                    "Gallery of editable images",
                    "Testimonial quote carousel",
                    "CTA section with booking button",
                    "FAQ accordion with common questions",
                    "Contact form section with email and phone",
                    "Rich text story section",
                    "Media feature with video or image",
                    "Event schedule agenda list",
                    "Team grid with staff portraits",
                ],
            )

            result = subprocess.run(
                ["python3", str(ROOT / "phases" / "tina-blueprint.py"), "generate", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            blueprint = json.loads((pipeline / "01-tina-blueprint.json").read_text())
            self.assertEqual(
                {block["type"] for block in blueprint["blocks"]},
                {"hero", "splitFeature", "featureGrid", "cardGrid", "gallery", "testimonial", "cta", "faq", "contact", "richText", "mediaFeature", "eventSchedule", "teamGrid"},
            )
            media_refs = {field["field_ref"] for field in blueprint["media_fields"]}
            self.assertTrue(any("team-grid" in ref for ref in media_refs))
            self.assertTrue(any("media-feature" in ref for ref in media_refs))

    def test_tina_blueprint_generator_rejects_briefs_flagged_for_human_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            pipeline = project / "pipeline"
            pipeline.mkdir()
            self._write_blueprint_creative_brief(pipeline)
            brief = json.loads((pipeline / "01-creative-brief.json").read_text())
            brief["_requires_human_confirmation"] = True
            (pipeline / "01-creative-brief.json").write_text(json.dumps(brief))

            result = subprocess.run(
                ["python3", str(ROOT / "phases" / "tina-blueprint.py"), "generate", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("STATUS:TINA_BLUEPRINT_FAILED", result.stdout + result.stderr)
            self.assertIn("brief_flagged_for_human_confirmation", result.stdout + result.stderr)

    def test_tina_blueprint_generator_rejects_unknown_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            pipeline = project / "pipeline"
            pipeline.mkdir()
            self._write_blueprint_creative_brief(pipeline, sections=["A bespoke manifesto rotator with unclear fields"])

            result = subprocess.run(
                ["python3", str(ROOT / "phases" / "tina-blueprint.py"), "generate", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("STATUS:TINA_BLUEPRINT_UNSUPPORTED_BLOCK", result.stdout + result.stderr)
            self.assertIn("bespoke manifesto", result.stdout + result.stderr)

    def test_orchestrator_phase_headings_match_canonical_order(self) -> None:
        text = (AGENTS / "orchestrator.md").read_text()
        headings = re.findall(r"^### Phase ([0-9.]+): (.+)$", text, flags=re.MULTILINE)
        observed = [number for number, _title in headings]
        self.assertEqual(observed, [
            "0", "1", "2", "2.5", "2.6", "3", "3.5", "3.6", "3.8", "4.1", "4.2", "4.3", "5",
        ])
        self.assertIn("### Phase 2.6: Tina Blueprint Contract", text)
        self.assertIn("### Phase 4.1: Frontend Codegen", text)
        self.assertIn("@astro-static/frontend-builder", text)
        self.assertIn("### Phase 5: Publish Result", text)
        self.assertNotIn("### Phase 5: Deploy", text)

    def test_readme_expected_regression_count_matches_suite(self) -> None:
        readme = (AGENTS / "README.md").read_text()
        test_count = sum(1 for name in dir(type(self)) if name.startswith("test_"))
        self.assertIn(f"Ran {test_count} tests", readme)

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

    def test_ppq_auth_helper_and_agents_use_opencode_credentials(self) -> None:
        helper = ROOT / "phases" / "ppq-auth.sh"
        self.assertTrue(helper.is_file())
        helper_text = helper.read_text()
        self.assertIn('.local/share/opencode/auth.json', helper_text)
        self.assertIn('.config/opencode/opencode.json', helper_text)
        self.assertNotIn(str(Path.home()), helper_text)  # no machine-specific home path baked in
        self.assertIn('STATUS:MISSING_PPQ_API_KEY', helper_text)
        for agent in ["img-gen.md", "vid-gen.md", "asset-generator.md"]:
            text = (AGENTS / agent).read_text()
            self.assertIn('ppq-auth.sh', text)
            self.assertIn('PPQ_API_KEY_SOURCE', text)

    def test_package_matrix_accepts_newer_rejects_downgrade_and_major(self) -> None:
        module = self._load_validate_pipeline_module()

        def errors_for(overrides: dict) -> list:
            deps = dict(module.CANONICAL_PACKAGE_RANGES)
            deps.update(overrides)
            issues: list = []
            module.validate_package_matrix(deps, issues)
            return [i for i in issues if i.level == "error"]

        # exact tested ranges pass
        self.assertEqual(errors_for({}), [])
        # newer patch/minor on the same release line is accepted
        self.assertEqual(errors_for({"astro": "^7.1.5"}), [])
        # downgrade below the tested floor is rejected
        self.assertTrue(errors_for({"astro": "^7.0.1"}))
        # a different major is rejected
        self.assertTrue(errors_for({"astro": "^8.0.0"}))
        # 0.x packages are locked to the tested minor (caret-incompatible bump rejected)
        self.assertTrue(errors_for({"@tinacms/astro": "^0.6.0"}))
        # a missing canonical dependency is still rejected
        missing_deps = dict(module.CANONICAL_PACKAGE_RANGES)
        del missing_deps["astro"]
        missing_issues: list = []
        module.validate_package_matrix(missing_deps, missing_issues)
        self.assertTrue([i for i in missing_issues if i.level == "error"])
        # unparseable specifiers warn but do not fail the build
        warn_deps = dict(module.CANONICAL_PACKAGE_RANGES)
        warn_deps["astro"] = "latest"
        warn_issues: list = []
        module.validate_package_matrix(warn_deps, warn_issues)
        self.assertFalse([i for i in warn_issues if i.level == "error"])
        self.assertTrue([i for i in warn_issues if i.level == "warning"])

    def test_img_vid_agents_use_self_contained_model_toolkit(self) -> None:
        for agent in ("img-gen.md", "vid-gen.md"):
            text = (AGENTS / agent).read_text()
            self.assertNotIn("skills/filmmaker", text)  # stale, uninstalled path
            self.assertIn("astro-static/models/model-lookup.sh", text)
        models_dir = next(
            (p for p in (ROOT / "models", AGENTS.parent.parent / "models") if p.is_dir()),
            None,
        )
        self.assertIsNotNone(models_dir, "models/ toolkit not found in repo or install layout")
        lookup = (models_dir / "model-lookup.sh").read_text()
        for stale in ("refresh-model-library.sh", "validate-ppq-models.sh", "_parse_ppq_models.py"):
            self.assertNotIn(stale, lookup)
        self.assertNotIn("to_entries[] | sort_by", lookup)  # jq antipattern: sort_by after [] flatten errors
        refresh = (models_dir / "refresh-models.sh").read_text()
        self.assertNotIn("validate-ppq-models.sh", refresh)
        self.assertNotIn("skills/filmmaker", refresh)

    def test_push_gitea_excludes_generated_and_secret_paths(self) -> None:
        text = (ROOT / "phases" / "push-gitea.sh").read_text()
        for expected in [
            'node_modules/',
            'dist/',
            '.astro/',
            '.opencode/',
            '.env',
            'pipeline/vps-connection.json',
            'pipeline/vps-connection.json.*',
            'pipeline/installation-summary.md',
            'pipeline/installation.log',
            'pipeline/setup-wrapper.*',
            'git rm --cached --ignore-unmatch',
            "':!node_modules/'",
            "':!dist/'",
            "':!pipeline/installation-summary.md'",
            "':!pipeline/installation.log'",
            "':!pipeline/setup-wrapper.*'",
            "':!pipeline/vps-connection.json.*'",
            "':!pipeline/bootstrap-result.json.*'",
        ]:
            self.assertIn(expected, text)

        validator = (ROOT / "validate-pipeline.py").read_text()
        self.assertIn("'pipeline/installation-summary.md'", validator)
        self.assertIn("'pipeline/installation.log'", validator)
        self.assertIn("'pipeline/setup-wrapper.*'", validator)
        self.assertIn("'pipeline/bootstrap-result.json'", validator)
        self.assertIn("'pipeline/bootstrap-result.json.*'", validator)
        self.assertIn("'pipeline/vps-connection.json.*'", validator)

    def test_build_deployer_does_not_complete_phase_before_gitea_snapshot(self) -> None:
        deployer = (AGENTS / "build-deployer.md").read_text()
        orchestrator = (AGENTS / "orchestrator.md").read_text()
        self.assertIn("Do not mark `4_3_build_deploy` completed", deployer)
        self.assertNotIn("mark `4_3_build_deploy` completed", deployer.replace("Do not mark `4_3_build_deploy` completed", ""))
        self.assertIn("Mark `4_3_build_deploy.status = \"completed\"` only after", orchestrator)

    def test_build_deployer_excludes_secret_installation_artifacts_from_rsync(self) -> None:
        deployer = (AGENTS / "build-deployer.md").read_text()
        for expected in [
            "--exclude='pipeline/vps-connection.json'",
            "--exclude='pipeline/vps-connection.json.*'",
            "--exclude='pipeline/bootstrap-result.json'",
            "--exclude='pipeline/bootstrap-result.json.*'",
        ]:
            self.assertIn(expected, deployer)
        self.assertIn("--exclude='pipeline/installation.log'", deployer)
        self.assertIn("--exclude='pipeline/setup-wrapper.*'", deployer)

    def test_build_deployer_uses_portable_timeout_for_rsync(self) -> None:
        deployer = (AGENTS / "build-deployer.md").read_text()
        self.assertIn("Portable timeout", deployer)
        self.assertIn("_timeout 240 rsync", deployer)
        self.assertNotIn("\ntimeout 240 rsync", deployer)

    def test_timeout_fallback_normalizes_alarm_to_pipeline_timeout_status(self) -> None:
        push = (ROOT / "phases" / "push-gitea.sh").read_text()
        deployer = (AGENTS / "build-deployer.md").read_text()
        for text in [push, deployer]:
            self.assertIn("return 124", text)
            self.assertNotIn("perl -e 'alarm shift; exec @ARGV'", text)

    def test_temp_secret_artifacts_are_excluded_from_rsync_git_and_validation(self) -> None:
        deployer = (AGENTS / "build-deployer.md").read_text()
        push = (ROOT / "phases" / "push-gitea.sh").read_text()
        validator = (ROOT / "validate-pipeline.py").read_text()
        for pattern in ["pipeline/vps-connection.json.*", "pipeline/bootstrap-result.json.*"]:
            self.assertIn(pattern, deployer)
            self.assertIn(pattern, push)
            self.assertIn(pattern, validator)
            self.assertIn(f"':!{pattern}'", push)

    def test_hyperframes_optional_failure_is_recorded_as_skipped_when_continuing(self) -> None:
        orchestrator = (AGENTS / "orchestrator.md").read_text()
        self.assertIn('mark `3_8_hyperframes_hero_optional.status = "skipped"`', orchestrator)
        self.assertNotIn('mark the phase failed and continue', orchestrator)
        self.assertIn('Phase 3.8 completed or skipped', orchestrator)

    def test_instagram_content_modes_match_brief_schema(self) -> None:
        schema = json.loads((AGENTS / "schemas" / "00-brief.schema.json").read_text())
        enum = schema["properties"]["instagram_use"]["enum"]
        for value in ["design_reference", "brand_research", "both", "content", "content_images", "media", "photos"]:
            self.assertIn(value, enum)

    def test_ig_download_rejects_paths_outside_instagram_pipeline_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()

            result = subprocess.run(
                ["bash", str(ROOT / "phases" / "ig-download.sh"), "http://127.0.0.1:1/image.jpg", "../evil.jpg"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("STATUS:IG_DOWNLOAD_FAILED reason=unsafe_output_path", result.stdout + result.stderr)
            self.assertFalse((root / "evil.jpg").exists())

    def test_ig_download_rejects_unsafe_cdn_urls_and_redacts_query_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)

            result = subprocess.run(
                [
                    "bash",
                    str(ROOT / "phases" / "ig-download.sh"),
                    "http://127.0.0.1:1/image.jpg?token=super-secret",
                    "pipeline/00-instagram/assets/post-001.jpg",
                ],
                cwd=project,
                text=True,
                capture_output=True,
            )

            combined = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, combined)
            self.assertIn("STATUS:IG_DOWNLOAD_FAILED reason=unsafe_url", combined)
            self.assertNotIn("super-secret", combined)
            self.assertFalse((project / "pipeline/00-instagram/assets/post-001.jpg").exists())

    def test_ig_download_does_not_follow_redirects_or_log_full_cdn_url(self) -> None:
        text = (ROOT / "phases" / "ig-download.sh").read_text()
        self.assertNotIn("curl -sS -L", text)
        self.assertNotIn("url=$CDN_URL", text)
        self.assertIn("--max-redirs 0", text)
        self.assertIn("url=$SAFE_URL", text)

    def test_asset_fallback_rejects_paths_that_escape_project_root_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            (project / "pipeline").mkdir()
            (project / "pipeline/02-asset-manifest.json").write_text(json.dumps({
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
            }))
            (project / "pipeline/02-image-shot-list.json").write_text(json.dumps({
                "schema_version": "1.0",
                "project_name": "demo-site",
                "images": [{
                    "id": "escape",
                    "type": "hero",
                    "prompt": "escape",
                    "output_path": "../evil.webp",
                    "dimensions": "1200x800",
                    "field_ref": "pages.home.sections.hero-home.backgroundImage",
                    "content_path": "src/content/pages/home.json.sections[0].backgroundImage",
                    "tina_default_value": "/images/evil.webp",
                }],
            }))

            result = subprocess.run(
                ["bash", str(ROOT / "phases" / "asset-fallbacks.sh"), "images"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("STATUS:ASSET_FALLBACK_FAILED reason=unsafe_path", result.stdout + result.stderr)
            self.assertFalse((root / "evil.svg").exists())

    def test_instagram_extractor_uses_current_frontmatter_schema(self) -> None:
        text = (AGENTS / "instagram-extractor.md").read_text()
        frontmatter = text.split("---", 2)[1]
        self.assertNotIn("tools:", frontmatter)
        self.assertNotIn("maxSteps:", frontmatter)
        self.assertIn("steps: 60", frontmatter)
        self.assertIn('skill:', frontmatter)
        self.assertIn('"*": deny', frontmatter)

    def test_instagram_extractor_profile_contract_uses_schema_envelope_and_schema_validation(self) -> None:
        text = (AGENTS / "instagram-extractor.md").read_text()
        for expected in [
            '"schema_version": "astro-static-instagram/v1"',
            '"extracted_at"',
            '"source_url"',
            '"extraction_metadata"',
            "00-instagram-extraction.schema.json",
            "validate-pipeline.py --phase instagram",
        ]:
            self.assertIn(expected, text)
        self.assertNotIn("python3 -c \"import json; json.load(open('pipeline/00-instagram/<file>.json'))", text)

    def test_instagram_phase_validator_rejects_profile_json_without_schema_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            ig_dir = project / "pipeline/00-instagram"
            ig_dir.mkdir(parents=True)
            (ig_dir / "assets").mkdir()
            (ig_dir / "extraction-report.md").write_text("# Instagram extraction\n")
            (ig_dir / "profile.json").write_text(json.dumps({
                "schema_version": "astro-static-instagram/v1",
                "profile": {"username": "demo", "display_name": "Demo"},
                "extraction_metadata": {"method": "search/instagram", "stealth_used": True},
            }))

            result = subprocess.run(
                ["python3", str(ROOT / "validate-pipeline.py"), "--phase", "instagram", ".", "--pipeline-dir", "pipeline/"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("00-instagram/profile.json", result.stdout)
            self.assertIn("source_url", result.stdout)

    def test_gen_lqip_rejects_paths_that_escape_project_root_before_writing(self) -> None:
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow is not installed")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            image_dir = project / "public/images"
            image_dir.mkdir(parents=True)
            image_path = image_dir / "source.png"
            image_path.write_bytes(base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
            ))

            result = subprocess.run(
                ["python3", str(ROOT / "phases" / "gen-lqip.py"), "public/images/source.png", "--out", "../evil.lqip.txt"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("unsafe_output_path", result.stdout + result.stderr)
            self.assertFalse((root / "evil.lqip.txt").exists())

    def test_setup_vps_firewall_allows_active_ssh_port_and_does_not_kill_apt(self) -> None:
        text = (ROOT / "setup-vps.sh").read_text()
        self.assertIn('SSH_PORT="${SSH_PORT:-22}"', text)
        self.assertIn('ufw allow "${SSH_PORT}/tcp"', text)
        self.assertNotIn('fuser -k /var/lib/dpkg/lock-frontend', text)
        self.assertNotIn('rm -f /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock', text)

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

    def test_setup_vps_mandatory_installation_logging_and_summary(self) -> None:
        text = (ROOT / "setup-vps.sh").read_text()
        self.assertIn('INSTALL_LOG_PATH="${STATE_DIR}/install-${PROJECT_NAME}-', text)
        self.assertIn('exec > >(tee -a "$INSTALL_LOG_PATH") 2>&1', text)
        self.assertIn('ln -sfn "$INSTALL_LOG_PATH" "${STATE_DIR}/latest-install.log"', text)
        self.assertIn('SUMMARY_PATH="${STATE_DIR}/installation-summary-${PROJECT_NAME}.md"', text)
        self.assertIn('## URLs', text)
        self.assertIn('## Credentials', text)
        self.assertIn('## Installation Diagnostics', text)
        self.assertIn('record_diagnostic', text)
        self.assertIn('diagnostics: $diagnostics', text)
        self.assertIn('installation_log: $installation_log', text)
        self.assertIn('installation_summary: $installation_summary', text)
        self.assertIn('chmod 0600 "$SUMMARY_PATH"', text)

    def test_bootstrap_join_fetches_installation_log_and_summary_owner_only(self) -> None:
        text = (ROOT / "phases/bootstrap-join.sh").read_text()
        self.assertIn('REMOTE_INSTALLATION_LOG=$(jq -r', text)
        self.assertIn('.installation_log // empty', text)
        self.assertIn('REMOTE_INSTALLATION_SUMMARY=$(jq -r', text)
        self.assertIn('.installation_summary // empty', text)
        self.assertIn('sudo cat \\"$REMOTE_INSTALLATION_LOG\\"', text)
        self.assertIn('> pipeline/installation.log', text)
        self.assertIn('sudo cat \\"$REMOTE_INSTALLATION_SUMMARY\\"', text)
        self.assertIn('> pipeline/installation-summary.md', text)
        self.assertIn('chmod 600 pipeline/installation.log', text)
        self.assertIn('chmod 600 pipeline/installation-summary.md', text)


if __name__ == "__main__":
    unittest.main()
