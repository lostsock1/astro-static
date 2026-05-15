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


if __name__ == "__main__":
    unittest.main()
