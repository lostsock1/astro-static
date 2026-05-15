#!/usr/bin/env python3
"""Small PPQ media validation helpers for the film-making pipeline.

These helpers catch the issues that are expensive to discover after render:
wrong reference-frame aspect ratios, unsupported video durations, and budget
tables based on guessed prices instead of PPQ response costs.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    message: str


TARGET_RATIOS = {
    "16:9": Fraction(16, 9),
    "9:16": Fraction(9, 16),
    "1:1": Fraction(1, 1),
    "4:5": Fraction(4, 5),
}


_CACHE_PATH = Path(os.environ.get(
    "PPQ_MODEL_CACHE",
    str(Path.home() / ".cache" / "opencode" / "ppq-video-models.json"),
))

# Fallback durations used only when the cache is unreachable. Cache is canonical.
_FALLBACK_DURATIONS: dict[str, tuple[int, ...]] = {
    "kling-3.0": (5, 10),
    "ppq/kling-3.0": (5, 10),
}


def _load_supported_durations() -> dict[str, tuple[int, ...]]:
    """Read supported durations from the PPQ cache; fall back if missing."""
    if not _CACHE_PATH.exists():
        return dict(_FALLBACK_DURATIONS)
    try:
        cache = json.loads(_CACHE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return dict(_FALLBACK_DURATIONS)

    out: dict[str, tuple[int, ...]] = {}
    for model_id, info in (cache.get("video_models") or {}).items():
        durations: set[int] = set()
        for pricing_block in info.get("pricing", []) or []:
            for size_key in (pricing_block.get("sizes") or {}).keys():
                # size keys look like "16:9_5" or "9:16_10"
                if "_" in size_key:
                    tail = size_key.rsplit("_", 1)[1]
                    if tail.isdigit():
                        durations.add(int(tail))
        if durations:
            sorted_dur = tuple(sorted(durations))
            out[model_id] = sorted_dur
            # Also expose the un-prefixed alias when the model id is provider-prefixed
            if "/" in model_id:
                out[model_id.split("/", 1)[1]] = sorted_dur
    return out or dict(_FALLBACK_DURATIONS)


SUPPORTED_VIDEO_DURATIONS = _load_supported_durations()


def _ratio_label(width: int, height: int) -> str:
    ratio = Fraction(width, height)
    if ratio == Fraction(1, 1):
        return "1:1"
    if abs(float(ratio) - float(Fraction(16, 9))) <= 0.03:
        return "16:9"
    if abs(float(ratio) - float(Fraction(9, 16))) <= 0.03:
        return "9:16"
    return f"{width}:{height}"


def validate_media_dimensions(
    scene_id: str,
    width: int,
    height: int,
    target_aspect_ratio: str,
    tolerance: float = 0.03,
) -> ValidationResult:
    """Return failure when media aspect ratio will not match the target video."""
    if width <= 0 or height <= 0:
        return ValidationResult(False, f"{scene_id}: invalid media dimensions {width}x{height}")
    if target_aspect_ratio not in TARGET_RATIOS:
        return ValidationResult(False, f"{scene_id}: unsupported target aspect ratio {target_aspect_ratio}")

    actual = width / height
    expected = float(TARGET_RATIOS[target_aspect_ratio])
    if abs(actual - expected) <= tolerance:
        return ValidationResult(True, f"{scene_id}: {width}x{height} matches {target_aspect_ratio}")

    actual_label = _ratio_label(width, height)
    return ValidationResult(
        False,
        f"{scene_id}: reference media is {actual_label} ({width}x{height}), "
        f"but target is {target_aspect_ratio}; re-roll with a landscape-capable "
        "image model or crop/extend before i2v to avoid pillarboxing.",
    )


def supported_video_duration(model: str, requested_seconds: int | float) -> int:
    """Round requested duration up to the nearest duration supported by the model."""
    supported = SUPPORTED_VIDEO_DURATIONS.get(model)
    if not supported:
        return int(round(requested_seconds))
    for duration in supported:
        if requested_seconds <= duration:
            return duration
    return supported[-1]


def total_generation_cost(responses: Iterable[dict[str, Any]]) -> float:
    """Sum actual PPQ costs, falling back to estimated costs for pending jobs."""
    total = 0.0
    for response in responses:
        value = response.get("cost", response.get("estimated_cost", 0.0))
        try:
            total += float(value)
        except (TypeError, ValueError):
            continue
    return round(total, 4)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate PPQ media dimensions and costs.")
    parser.add_argument("--scene", required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--target", default="16:9")
    args = parser.parse_args()

    result = validate_media_dimensions(args.scene, args.width, args.height, args.target)
    print(result.message)
    raise SystemExit(0 if result.ok else 1)
