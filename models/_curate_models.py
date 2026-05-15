#!/usr/bin/env python3
"""Merge live PPQ API cache + curated metadata → ppq-model-library.md.

Reads JSON cache from validate-ppq-models.sh output (stdin or --cache).
Writes curated markdown reference to stdout or --output.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Curated metadata: human knowledge the API cannot provide ──────────────

CURATED_VIDEO: dict[str, dict] = {
    "veo3": {
        "tier": "premium",
        "dialect": "veo",
        "strengths": ["Narrative-heavy detail tolerance (100-300 words)", "Audio-native generation", "Multiple aspect ratios"],
        "best_for": "Cinematic establishing shots with ambient audio",
        "gotchas": ["No negative prompt — use positive exclusion like 'desolate landscape with no buildings'", "Describe temporal progression: starts with... then... finally..."],
        "prompt_len": "100-300 words",
    },
    "veo3-fast": {
        "tier": "standard",
        "dialect": "veo",
        "strengths": ["Same Veo quality, faster generation", "Audio-native", "Cheaper than veo3"],
        "best_for": "Quick iterations, budget-conscious Veo quality",
        "gotchas": ["Same dialect as veo3 but shorter prompts preferred (50-150 words)"],
        "prompt_len": "50-150 words",
    },
    "kling-3.0": {
        "tier": "premium",
        "dialect": "kling",
        "strengths": ["Physics-strong", "Detail-tolerant", "Negative prompt support"],
        "best_for": "Action sequences, physics-heavy scenes",
        "gotchas": ["Always use negative prompt", "Specify hand positions when visible"],
        "prompt_len": "50-150 words",
    },
    "kling-2.1-master": {
        "tier": "premium",
        "dialect": "kling",
        "strengths": ["1080p native", "Negative prompt", "Image-to-video capable"],
        "best_for": "Highest-quality Kling output at 1080p",
        "gotchas": ["Expensive — use for hero shots only", "Same dialect as all Kling models"],
        "prompt_len": "50-150 words",
    },
    "kling-2.1-pro": {
        "tier": "standard",
        "dialect": "kling",
        "strengths": ["1080p at budget price", "Negative prompt", "t2v + i2v"],
        "best_for": "Standard-quality Kling at best value",
        "gotchas": ["Renamed to Kling 2.6 — same model, new branding"],
        "prompt_len": "50-150 words",
    },
    "kling-2.1-standard": {
        "tier": "budget",
        "dialect": "kling",
        "strengths": ["Cheapest Kling option", "720p"],
        "best_for": "Rough previews, animatics",
        "gotchas": ["720p only", "KNOWN BUG: size param underscore issue — may be unreliable"],
        "prompt_len": "50-150 words",
    },
    "kling-2.5-turbo": {
        "tier": "standard",
        "dialect": "kling",
        "strengths": ["Fast Kling generation", "Negative prompt"],
        "best_for": "Quick Kling iterations, balanced quality/speed",
        "gotchas": ["16:9 and 9:16 only (no 1:1)"],
        "prompt_len": "50-150 words",
    },
    "kling-o3-standard": {
        "tier": "standard",
        "dialect": "kling",
        "strengths": ["Up to 15s duration", "Negative prompt", "Image-to-video"],
        "best_for": "Longer Kling clips (10s, 15s)",
        "gotchas": ["Pricey at 15s ($2.898)"],
        "prompt_len": "50-150 words",
    },
    "kling-o3-pro": {
        "tier": "premium",
        "dialect": "kling",
        "strengths": ["Highest Kling O3 quality"],
        "best_for": "Premium Kling shots",
        "gotchas": ["Flat pricing — no duration/quality variants"],
        "prompt_len": "50-150 words",
    },
    "kling-v1-standard": {
        "tier": "budget",
        "dialect": "kling",
        "strengths": ["Legacy Kling model"],
        "best_for": "N/A — use newer Kling models",
        "gotchas": ["LEGACY — prefer kling-2.1-standard or kling-2.5-turbo"],
        "prompt_len": "50-150 words",
    },
    "runway-gen4": {
        "tier": "budget",
        "dialect": "runway",
        "strengths": ["Cheapest video model on PPQ", "720p and 1080p options", "Image reference support"],
        "best_for": "Budget projects, high-volume generation",
        "gotchas": ["720p is extremely cheap ($0.069)", "1080p limited to 5s"],
        "prompt_len": "30-80 words",
    },
    "runway-aleph": {
        "tier": "standard",
        "dialect": "runway",
        "strengths": ["Runway's latest model", "5s/10s options"],
        "best_for": "Runway quality above Gen-4",
        "gotchas": ["No aspect_ratio control", "No image reference support"],
        "prompt_len": "30-80 words",
    },
    "grok-imagine-video-t2v": {
        "tier": "standard",
        "dialect": "grok",
        "strengths": ["480p and 720p", "Up to 15s duration", "Resolution control"],
        "best_for": "xAI ecosystem, longer clips at 480p",
        "gotchas": ["Grok's video model — newer, less battle-tested"],
        "prompt_len": "50-150 words",
    },
    "seedance-2": {
        "tier": "premium",
        "dialect": "seedance",
        "strengths": ["480p/720p resolution control", "4-15s duration", "Image reference", "High quality"],
        "best_for": "Premium ByteDance video, Chinese-market content",
        "gotchas": ["Expensive at 720p 15s ($4.54)", "Use @ reference syntax for best results"],
        "prompt_len": "Detailed scene descriptions",
    },
    "seedance-2-fast": {
        "tier": "standard",
        "dialect": "seedance",
        "strengths": ["Same as seedance-2 but ~20% cheaper/faster", "480p/720p", "4-15s"],
        "best_for": "Seedance quality at better speed/price",
        "gotchas": ["Slightly lower quality ceiling than seedance-2"],
        "prompt_len": "Detailed scene descriptions",
    },
    "seedance-v1-lite": {
        "tier": "budget",
        "dialect": "seedance",
        "strengths": ["Cheap Seedance access", "Resolution + aspect ratio control"],
        "best_for": "Budget Seedance, quick previews",
        "gotchas": ["Lower quality than seedance-2"],
        "prompt_len": "50-100 words",
    },
    "hailuo-02-pro": {
        "tier": "standard",
        "dialect": "hailuo",
        "strengths": ["MiniMax's best video model", "Image reference support"],
        "best_for": "MiniMax ecosystem video",
        "gotchas": ["Flat pricing — no quality/duration variants"],
        "prompt_len": "50-150 words",
    },
    "hailuo-02-standard": {
        "tier": "standard",
        "dialect": "hailuo",
        "strengths": ["Same price as Pro tier", "Image reference"],
        "best_for": "Standard MiniMax video",
        "gotchas": ["Same price as Pro — prefer hailuo-02-pro"],
        "prompt_len": "50-150 words",
    },
    "minimax-video": {
        "tier": "standard",
        "dialect": "hailuo",
        "strengths": ["Legacy MiniMax video", "Image reference"],
        "best_for": "N/A — prefer hailuo-02-pro",
        "gotchas": ["LEGACY — use hailuo-02-pro instead"],
        "prompt_len": "50-150 words",
    },
    "pika-v2.2": {
        "tier": "standard",
        "dialect": "pika",
        "strengths": ["Negative prompt", "Aspect ratio control", "Image reference"],
        "best_for": "Pika ecosystem, stylized content",
        "gotchas": ["Flat pricing — no quality variants"],
        "prompt_len": "50-100 words",
    },
    "pixverse-v4.5": {
        "tier": "standard",
        "dialect": "pixverse",
        "strengths": ["Negative prompt", "Aspect ratio control", "Image reference"],
        "best_for": "PixVerse ecosystem",
        "gotchas": ["i2v fails with 404 — PPQ signed URLs not accessible to pixverse provider"],
        "prompt_len": "50-100 words",
    },
    "luma-dream-machine": {
        "tier": "standard",
        "dialect": "luma",
        "strengths": ["Aspect ratio control"],
        "best_for": "Luma ecosystem, dreamlike content",
        "gotchas": ["No image reference support"],
        "prompt_len": "50-100 words",
    },
    "haiper-video-v2": {
        "tier": "budget",
        "dialect": "haiper",
        "strengths": ["Cheap ($0.184)", "Resolution control"],
        "best_for": "Budget video generation",
        "gotchas": ["No aspect ratio control", "No image reference"],
        "prompt_len": "50-100 words",
    },
    "wan-t2v": {
        "tier": "standard",
        "dialect": "wan",
        "strengths": ["Negative prompt", "Aspect ratio + image reference"],
        "best_for": "Wan ecosystem",
        "gotchas": ["Flat pricing"],
        "prompt_len": "50-100 words",
    },
    "mochi-v1": {
        "tier": "standard",
        "dialect": "mochi",
        "strengths": ["Genmo's video model"],
        "best_for": "N/A — legacy",
        "gotchas": ["LEGACY — no longer actively developed"],
        "prompt_len": "50-100 words",
    },
}

CURATED_IMAGE: dict[str, dict] = {
    "gpt-image-2": {
        "tier": "standard",
        "dialect": "gpt-image",
        "strengths": ["OpenAI's latest image model", "Multiple quality tiers"],
        "best_for": "General-purpose image generation, best quality/price ratio",
        "gotchas": ["Quality tiers affect pricing significantly"],
    },
    "gpt-image-1.5": {
        "tier": "standard",
        "dialect": "gpt-image",
        "strengths": ["Good balance of quality and cost"],
        "best_for": "Mid-tier image generation",
        "gotchas": ["Overlapping pricing with gpt-image-2"],
    },
    "gpt-image-1": {
        "tier": "standard",
        "dialect": "gpt-image",
        "strengths": ["OpenAI's first native image model (GPT-4o based)"],
        "best_for": "Compatibility with GPT-4o image workflows",
        "gotchas": ["Prefer gpt-image-2 for new projects"],
    },
    "nano-banana-pro": {
        "tier": "premium",
        "dialect": "gemini",
        "strengths": ["Gemini 3.0 image generation", "High quality"],
        "best_for": "Premium Google-quality images",
        "gotchas": ["PPQ branded as 'Nano Banana Pro'"],
    },
    "nano-banana-2": {
        "tier": "standard",
        "dialect": "gemini",
        "strengths": ["Gemini 3.1 Flash image", "Resolution tiers (1K/2K/4K)"],
        "best_for": "Good quality at reasonable price, resolution control",
        "gotchas": ["Edit variant available (nano-banana-2-edit)"],
    },
    "flux-2-pro": {
        "tier": "standard",
        "dialect": "flux",
        "strengths": ["High quality, Flux ecosystem", "Size variants"],
        "best_for": "Flux-quality generation at competitive price",
        "gotchas": ["Pro version — use flux-2-flex for budget"],
    },
    "flux-2-flex": {
        "tier": "budget",
        "dialect": "flux",
        "strengths": ["Flexible Flux generation"],
        "best_for": "Budget Flux quality",
        "gotchas": ["Higher base price than flux-2-pro for some sizes"],
    },
    "flux-2-pro-i2i": {
        "tier": "standard",
        "dialect": "flux",
        "strengths": ["Image-to-image editing", "Same quality as flux-2-pro"],
        "best_for": "Editing existing images with Flux quality",
        "gotchas": ["Requires source image_url"],
    },
    "grok-imagine": {
        "tier": "standard",
        "dialect": "grok",
        "strengths": ["xAI's image generation"],
        "best_for": "xAI ecosystem image generation",
        "gotchas": ["Edit variant available (grok-imagine-edit)"],
    },
    "imagen4-preview": {
        "tier": "standard",
        "dialect": "imagen",
        "strengths": ["Google's latest Imagen model"],
        "best_for": "Google-quality image generation",
        "gotchas": ["Preview — pricing may change"],
    },
    "imagen3": {
        "tier": "standard",
        "dialect": "imagen",
        "strengths": ["Stable Google image generation"],
        "best_for": "Reliable Google-quality images",
        "gotchas": ["Prefer imagen4-preview for new projects"],
    },
    "flux-kontext-pro": {
        "tier": "standard",
        "dialect": "flux",
        "strengths": ["Context-aware Flux generation"],
        "best_for": "Contextual image editing",
        "gotchas": ["Different from flux-2-pro — purpose-built for context"],
    },
    "seedream-4.5": {
        "tier": "standard",
        "dialect": "seedream",
        "strengths": ["ByteDance's image model"],
        "best_for": "ByteDance ecosystem, stylized images",
        "gotchas": ["Edit variant available (seedream-4.5-edit)"],
    },
    "kling-o1-image": {
        "tier": "standard",
        "dialect": "kling",
        "strengths": ["Kling's image generation"],
        "best_for": "Kling ecosystem reference frames for Kling video",
        "gotchas": ["Good t2i→i2v chain pairing with Kling video models"],
    },
    "qwen-image": {
        "tier": "standard",
        "dialect": "qwen",
        "strengths": ["Qwen's image generation", "I2I variant available"],
        "best_for": "Qwen ecosystem images",
        "gotchas": ["Both t2i and i2i at same price"],
    },
    "recraft-v3": {
        "tier": "standard",
        "dialect": "recraft",
        "strengths": ["Recraft V3 generation", "SVG output option"],
        "best_for": "Vector-style imagery, design-focused",
        "gotchas": ["SVG variant costs 2x (recraft-v3-svg)"],
    },
    "fast-sdxl": {
        "tier": "budget",
        "dialect": "sdxl",
        "strengths": ["Cheapest t2i option ($0.0144)", "Fast"],
        "best_for": "Quick previews, animatics, budget reference frames",
        "gotchas": ["SDXL quality ceiling — not for final output"],
    },
}

CURATED_I2V: dict[str, dict] = {
    "veo3-i2v": {
        "tier": "premium",
        "dialect": "veo",
        "strengths": ["Highest quality i2v", "Audio generation"],
        "best_for": "Premium image-to-video with ambient audio",
    },
    "veo3-fast-i2v": {
        "tier": "standard",
        "dialect": "veo",
        "strengths": ["Fast Veo i2v", "Cheaper than veo3-i2v"],
        "best_for": "Veo quality i2v at better price",
    },
    "kling-2.1-master-i2v": {
        "tier": "premium",
        "dialect": "kling",
        "strengths": ["Kling Master quality i2v", "5s/10s"],
        "best_for": "Premium Kling i2v",
    },
    "kling-2.5-turbo-i2v": {
        "tier": "standard",
        "dialect": "kling",
        "strengths": ["Fast Kling i2v", "5s/10s at same price"],
        "best_for": "Standard Kling i2v, best value",
    },
    "kling-2.1-pro-i2v": {
        "tier": "standard",
        "dialect": "kling",
        "strengths": ["Kling Pro quality i2v"],
        "best_for": "Mid-tier Kling i2v",
    },
    "kling-o3-standard-i2v": {
        "tier": "standard",
        "dialect": "kling",
        "strengths": ["Up to 15s i2v"],
        "best_for": "Longer Kling i2v clips",
    },
    "kling-o3-pro-i2v": {
        "tier": "premium",
        "dialect": "kling",
        "strengths": ["Premium Kling O3 i2v"],
        "best_for": "Best Kling i2v quality",
    },
    "seedance-2-i2v": {
        "tier": "premium",
        "dialect": "seedance",
        "strengths": ["Seedance quality i2v", "720p resolution control"],
        "best_for": "Premium Seedance i2v",
    },
    "seedance-2-fast-i2v": {
        "tier": "standard",
        "dialect": "seedance",
        "strengths": ["Fast Seedance i2v"],
        "best_for": "Seedance i2v at better speed/price",
    },
    "grok-imagine-video-i2v": {
        "tier": "standard",
        "dialect": "grok",
        "strengths": ["Grok i2v, up to 15s"],
        "best_for": "xAI ecosystem i2v",
    },
    "haiper-video-v2-i2v": {
        "tier": "budget",
        "dialect": "haiper",
        "strengths": ["Cheapest dedicated i2v ($0.23)"],
        "best_for": "Budget image-to-video",
    },
}

# ── Recommended t2i→i2v chains ──────────────────────────────────────────

RECOMMENDED_CHAINS = {
    "budget": {
        "t2i": "fast-sdxl",
        "i2v": "haiper-video-v2-i2v",
        "total_est": 0.2444,
        "notes": "Cheapest possible chain. SDXL + Haiper. Preview quality only.",
    },
    "standard": {
        "t2i": "nano-banana-2",
        "i2v": "kling-2.5-turbo-i2v",
        "total_est": 0.6095,
        "notes": "Good quality/price. Gemini Flash t2i → Kling Turbo i2v.",
    },
    "kling_native": {
        "t2i": "kling-o1-image",
        "i2v": "kling-2.5-turbo-i2v",
        "total_est": 0.5635,
        "notes": "Kling-native chain. Best consistency for Kling video output.",
    },
    "premium": {
        "t2i": "nano-banana-pro",
        "i2v": "veo3-fast-i2v",
        "total_est": 1.0235,
        "notes": "Premium chain. Gemini 3 Pro → Veo 3 Fast i2v with audio.",
    },
    "ultra": {
        "t2i": "nano-banana-pro",
        "i2v": "veo3-i2v",
        "total_est": 3.7835,
        "notes": "Maximum quality. Gemini 3 Pro → Veo 3 Quality i2v with audio.",
    },
}


# ── Markdown generation ─────────────────────────────────────────────────

def _min_price(pricing: list[dict]) -> float:
    """Get the minimum price from a pricing variants list."""
    best = float("inf")
    for v in pricing:
        for _, price in v.get("sizes", {}).items():
            if price < best:
                best = price
    return best if best != float("inf") else 0.0


def _format_pricing_table(pricing: list[dict]) -> str:
    """Format pricing variants as a markdown table."""
    lines = []
    for v in pricing:
        qual = v.get("quality", "default")
        sizes = v.get("sizes", {})
        if qual != "default":
            lines.append(f"  Quality: **{qual}**")
        for size, price in sorted(sizes.items()):
            label = size.replace("_", " ").strip()
            lines.append(f"  | `{label}` | ${price:.4f} |")
    return "\n".join(lines)


def _tier_badge(tier: str) -> str:
    colors = {"budget": "🟢", "standard": "🟡", "premium": "🔴"}
    return f"{colors.get(tier, '⚪')} {tier.upper()}"


def generate_markdown(cache: dict) -> str:
    video = cache.get("video_models", {})
    image = cache.get("image_models", {})
    recs = cache.get("recommendations", {})
    warnings_list = cache.get("warnings", [])
    queried = cache.get("queried_at", "unknown")

    lines: list[str] = []

    # ── Header ───────────────────────────────────────────────────────
    lines.append("# PPQ Model Library — Film-Making Reference")
    lines.append("")
    lines.append(f"Auto-generated from PPQ API. **Queried**: {queried}")
    lines.append("")
    lines.append("Refresh: `bash ~/.config/opencode/skills/filmmaker/scripts/refresh-model-library.sh [--force]`")
    lines.append("")

    # ── Quick Reference ──────────────────────────────────────────────
    lines.append("## Quick Reference")
    lines.append("")
    lines.append(f"- **Cheapest t2v**: `{recs.get('cheapest_t2v', 'N/A')}` — ${recs.get('cheapest_t2v_price', 0):.4f}")
    lines.append(f"- **Cheapest i2v**: `{recs.get('cheapest_i2v', 'N/A')}` — ${recs.get('cheapest_i2v_price', 0):.4f}")
    lines.append(f"- **Cheapest t2i**: `{recs.get('cheapest_t2i', 'N/A')}` — ${recs.get('cheapest_t2i_price', 0):.4f}")
    lines.append("")

    # ── Recommended Chains ───────────────────────────────────────────
    lines.append("## Recommended t2i → i2v Chains")
    lines.append("")
    lines.append("| Chain | t2i Model | i2v Model | Est. Total/scene | Notes |")
    lines.append("|-------|-----------|-----------|-----------------|-------|")
    for name, chain in RECOMMENDED_CHAINS.items():
        lines.append(f"| **{name}** | `{chain['t2i']}` | `{chain['i2v']}` | ${chain['total_est']:.4f} | {chain['notes']} |")
    lines.append("")

    # ── Video Models Summary ─────────────────────────────────────────
    lines.append("## Video Models (Text-to-Video)")
    lines.append("")
    lines.append("| Model | Tier | Cheapest | Prompt Dialect | Best For |")
    lines.append("|-------|------|----------|----------------|----------|")
    for mid in sorted(video.keys()):
        m = video[mid]
        meta = CURATED_VIDEO.get(mid, {})
        tier = meta.get("tier", "?")
        cheapest = _min_price(m.get("pricing", []))
        dialect = meta.get("dialect", "?")
        best = meta.get("best_for", "")[:40]
        badge = _tier_badge(tier)
        lines.append(f"| `{mid}` | {badge} | ${cheapest:.4f} | {dialect} | {best} |")
    lines.append("")

    # ── Video Model Details ──────────────────────────────────────────
    lines.append("## Video Model Details")
    lines.append("")
    for mid in sorted(video.keys()):
        m = video[mid]
        meta = CURATED_VIDEO.get(mid, {})
        tier = meta.get("tier", "standard")
        lines.append(f"### `{mid}` — {m.get('name', mid)} {_tier_badge(tier)}")
        lines.append("")
        if meta.get("best_for"):
            lines.append(f"**Best for**: {meta['best_for']}")
        if meta.get("prompt_len"):
            lines.append(f"**Prompt length**: {meta['prompt_len']}")
        if meta.get("strengths"):
            lines.append(f"**Strengths**: {'; '.join(meta['strengths'])}")
        lines.append("")

        # Pricing table
        pricing = m.get("pricing", [])
        if pricing:
            lines.append("| Config | Price |")
            lines.append("|--------|-------|")
            lines.append(_format_pricing_table(pricing))
            lines.append("")

        if meta.get("gotchas"):
            lines.append(f"⚠️ **Gotchas**: {'; '.join(meta['gotchas'])}")
            lines.append("")

        issues = m.get("known_issues", [])
        if issues:
            lines.append(f"🚫 **Known issues**: {'; '.join(issues)}")
            lines.append("")
        lines.append("---")
        lines.append("")

    # ── Image-to-Video Models ────────────────────────────────────────
    # Collect i2v models from image cache (they have category containing "image-to-video")
    i2v_models = {k: v for k, v in image.items() if "image-to-video" in v.get("category", "").lower() or "i2v" in k}

    if i2v_models:
        lines.append("## Image-to-Video Models (Dedicated)")
        lines.append("")
        lines.append("| Model | Tier | Cheapest | Dialect | Best For |")
        lines.append("|-------|------|----------|---------|----------|")
        for mid in sorted(i2v_models.keys()):
            m = i2v_models[mid]
            meta = CURATED_I2V.get(mid, {})
            tier = meta.get("tier", "standard")
            cheapest = _min_price(m.get("pricing", []))
            dialect = meta.get("dialect", "?")
            best = meta.get("best_for", "")[:40]
            badge = _tier_badge(tier)
            lines.append(f"| `{mid}` | {badge} | ${cheapest:.4f} | {dialect} | {best} |")
        lines.append("")

        lines.append("### i2v Pricing Details")
        lines.append("")
        for mid in sorted(i2v_models.keys()):
            m = i2v_models[mid]
            meta = CURATED_I2V.get(mid, {})
            tier = meta.get("tier", "standard")
            lines.append(f"**`{mid}`** {_tier_badge(tier)}")
            if meta.get("best_for"):
                lines.append(f"- Best for: {meta['best_for']}")
            pricing = m.get("pricing", [])
            if pricing:
                lines.append(_format_pricing_table(pricing))
            lines.append("")
        lines.append("---")
        lines.append("")

    # ── Image Models (t2i) ───────────────────────────────────────────
    t2i_models = {k: v for k, v in image.items()
                  if "image-to-video" not in v.get("category", "").lower()
                  and "i2v" not in k and "v2v" not in k}

    lines.append("## Image Models (Text-to-Image)")
    lines.append("")
    lines.append("| Model | Tier | Cheapest | Dialect | Best For |")
    lines.append("|-------|------|----------|---------|----------|")
    for mid in sorted(t2i_models.keys()):
        m = t2i_models[mid]
        meta = CURATED_IMAGE.get(mid, {})
        tier = meta.get("tier", "standard")
        cheapest = _min_price(m.get("pricing", []))
        dialect = meta.get("dialect", "?")
        best = meta.get("best_for", "")[:40]
        badge = _tier_badge(tier)
        lines.append(f"| `{mid}` | {badge} | ${cheapest:.4f} | {dialect} | {best} |")
    lines.append("")

    # Image details
    lines.append("### Image Model Details")
    lines.append("")
    for mid in sorted(t2i_models.keys()):
        m = t2i_models[mid]
        meta = CURATED_IMAGE.get(mid, {})
        tier = meta.get("tier", "standard")
        pricing = m.get("pricing", [])

        # Only detail non-utility models (skip upscalers, rembg, etc.)
        if m.get("category", "") in ("upscaler", "background-removal"):
            continue

        lines.append(f"**`{mid}`** {_tier_badge(tier)}")
        if meta.get("best_for"):
            lines.append(f"- Best for: {meta['best_for']}")
        if meta.get("gotchas"):
            lines.append(f"- ⚠️ {'; '.join(meta['gotchas'])}")
        if pricing:
            lines.append(_format_pricing_table(pricing))
        lines.append("")

    # ── Capability Matrix ────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## Video Capability Matrix")
    lines.append("")
    lines.append("| Model | Audio | i2v | Neg. Prompt | Aspect Ratio | Duration(s) |")
    lines.append("|-------|-------|-----|-------------|-------------|-------------|")

    for mid in sorted(video.keys()):
        m = video[mid]
        caps = m.get("accepts_image", False)
        meta = CURATED_VIDEO.get(mid, {})
        has_neg = "✅" if "negative" in str(meta.get("strengths", "")).lower() or mid.startswith(("kling", "pika", "pixverse", "wan")) else "❌"
        has_audio = "✅" if "veo3" in mid else "❌"
        has_i2v = "✅" if caps else "❌"
        has_ar = "✅" if "aspect" in str(meta.get("strengths", "")).lower() or mid not in ("runway-aleph", "haiper-video-v2") else "❌"

        # Get durations from pricing
        durations = set()
        for v in m.get("pricing", []):
            for size in v.get("sizes", {}):
                parts = size.split("_")
                for p in parts:
                    if p.isdigit():
                        durations.add(p)
        dur_str = ", ".join(sorted(durations)) if durations else "default"

        lines.append(f"| `{mid}` | {has_audio} | {has_i2v} | {has_neg} | {has_ar} | {dur_str} |")
    lines.append("")

    # ── Budget Scenarios ─────────────────────────────────────────────
    lines.append("## Budget Scenarios (per project)")
    lines.append("")
    lines.append("| Budget | Scenes | Chain | t2i Cost | i2v Cost | Total | Leftover for rerolls |")
    lines.append("|--------|--------|-------|----------|----------|-------|---------------------|")

    scenarios = [
        (5, 5, "budget"), (5, 5, "standard"), (5, 5, "kling_native"),
        (20, 10, "standard"), (20, 10, "kling_native"), (20, 10, "premium"),
        (50, 15, "standard"), (50, 15, "premium"), (50, 10, "ultra"),
    ]
    for budget, scenes, chain_name in scenarios:
        chain = RECOMMENDED_CHAINS[chain_name]
        # Get actual prices from cache
        t2i_model = chain["t2i"]
        i2v_model = chain["i2v"]
        t2i_price = _min_price(t2i_models.get(t2i_model, {}).get("pricing", [{}])) if t2i_model in t2i_models else chain.get("total_est", 0)
        i2v_price = _min_price(i2v_models.get(i2v_model, {}).get("pricing", [{}])) if i2v_model in i2v_models else chain.get("total_est", 0)
        total = (t2i_price + i2v_price) * scenes
        leftover = budget - total
        marker = "✅" if leftover >= 0 else "❌ over"
        lines.append(f"| ${budget} | {scenes} | {chain_name} | ${t2i_price:.4f} | ${i2v_price:.4f} | ${total:.2f} | ${leftover:.2f} {marker} |")
    lines.append("")

    # ── Warnings ─────────────────────────────────────────────────────
    if warnings_list:
        lines.append("## Active Warnings")
        lines.append("")
        for w in warnings_list:
            lines.append(f"- ⚠️ {w}")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Curate PPQ model cache into markdown reference")
    parser.add_argument("--cache", default=None, help="Path to JSON cache file (stdin if omitted)")
    parser.add_argument("--output", default=None, help="Output .md file path (stdout if omitted)")
    args = parser.parse_args()

    if args.cache:
        with open(args.cache) as f:
            cache = json.load(f)
    else:
        cache = json.load(sys.stdin)

    md = generate_markdown(cache)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(md)
        print(f"✅ Written to {args.output} ({len(md.splitlines())} lines)", file=sys.stderr)
    else:
        print(md)


if __name__ == "__main__":
    main()
