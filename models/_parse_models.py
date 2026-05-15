#!/usr/bin/env python3
"""Parse PPQ API model list into validated cache file. Reads JSON from stdin."""
import json, sys
from datetime import datetime, timezone

raw = json.load(sys.stdin)
cache_file = sys.argv[1] if len(sys.argv) > 1 else None

video_models = {}
image_models = {}
warnings = []

KNOWN_BROKEN = {
    "kling-2.1-standard": ["size_param_underscore_bug — server strips text after '_' in size. UNUSABLE."],
    "kling-2.1-pro": ["size_param_underscore_bug — same bug as kling-2.1-standard. UNUSABLE."],
}

KNOWN_I2V_UNAVAILABLE = {
    "runway-gen4": "Listed as accepts_image=true but i2v returns 'no providers available'.",
    "pixverse-v4.5": "i2v fails with 404 — PPQ signed URLs not accessible to pixverse provider.",
}

for model in raw.get("data", []):
    model_id = model["id"]
    model_type = model.get("type", "")
    model_name = model.get("name", model_id)
    caps = model.get("capabilities", {})
    pricing = model.get("pricing", {})

    if model_type == "video":
        entry = {
            "name": model_name,
            "category": model.get("category", ""),
            "accepts_prompt": caps.get("accepts_prompt", False),
            "accepts_image": caps.get("accepts_image_url", False),
            "quality_options": caps.get("quality_options", []),
            "pricing": [],
            "known_issues": [],
            "recommended": True,
        }
        for variant in pricing.get("variants", []):
            qual = variant.get("quality", "default")
            sizes = {opt["size"]: opt["price"] for opt in variant.get("options", [])}
            entry["pricing"].append({"quality": qual, "sizes": sizes})
        # Fallback: models that use base_price instead of variants
        if not entry["pricing"] and pricing.get("base_price"):
            entry["pricing"].append({"quality": "default", "sizes": {"default": pricing["base_price"]}})
        if model_id in KNOWN_BROKEN:
            entry["known_issues"].extend(KNOWN_BROKEN[model_id])
            entry["recommended"] = False
            warnings.append(f"BROKEN: {model_id} — see known_issues")
        if model_id in KNOWN_I2V_UNAVAILABLE:
            entry["known_issues"].append(f"i2v_unavailable: {KNOWN_I2V_UNAVAILABLE[model_id]}")
            warnings.append(f"i2v UNAVAILABLE: {model_id}")
        video_models[model_id] = entry

    elif model_type == "image":
        entry = {
            "name": model_name,
            "category": model.get("category", ""),
            "accepts_prompt": caps.get("accepts_prompt", False),
            "accepts_image": caps.get("accepts_image_url", False),
            "pricing": [],
            "known_issues": [],
            "recommended": True,
        }
        for variant in pricing.get("variants", []):
            qual = variant.get("quality", "default")
            sizes = {opt["size"]: opt["price"] for opt in variant.get("options", [])}
            entry["pricing"].append({"quality": qual, "sizes": sizes})
        if not entry["pricing"] and pricing.get("base_price"):
            entry["pricing"].append({"quality": "default", "sizes": {"default": pricing["base_price"]}})
        image_models[model_id] = entry

cheapest_t2v = None
cheapest_t2v_price = float("inf")
cheapest_i2v = None
cheapest_i2v_price = float("inf")
cheapest_t2i = None
cheapest_t2i_price = float("inf")

def has_issue(model, keyword):
    return any(keyword in issue.lower() for issue in model.get("known_issues", []))

for mid, m in video_models.items():
    if not m["recommended"]:
        continue
    for p in m["pricing"]:
        for size, price in p["sizes"].items():
            if m["category"] == "text-to-video" and price < cheapest_t2v_price:
                cheapest_t2v_price = price
                cheapest_t2v = mid
            if m["accepts_image"] and not has_issue(m, "i2v_unavailable") and price < cheapest_i2v_price:
                cheapest_i2v_price = price
                cheapest_i2v = mid

# Also check image_models with image-to-video category (dedicated i2v models)
for mid, m in image_models.items():
    if not m["recommended"]:
        continue
    if m["category"] == "image-to-video" and m["accepts_image"]:
        for p in m["pricing"]:
            for size, price in p["sizes"].items():
                if not has_issue(m, "i2v_unavailable") and price < cheapest_i2v_price:
                    cheapest_i2v_price = price
                    cheapest_i2v = mid

for mid, m in image_models.items():
    if m["category"] not in ("text-to-image",):
        continue
    for p in m["pricing"]:
        for size, price in p["sizes"].items():
            if price < cheapest_t2i_price:
                cheapest_t2i_price = price
                cheapest_t2i = mid

cache = {
    "queried_at": datetime.now(timezone.utc).isoformat(),
    "video_models": video_models,
    "image_models": image_models,
    "recommendations": {
        "cheapest_t2v": cheapest_t2v,
        "cheapest_t2v_price": cheapest_t2v_price,
        "cheapest_i2v": cheapest_i2v,
        "cheapest_i2v_price": cheapest_i2v_price,
        "cheapest_t2i": cheapest_t2i,
        "cheapest_t2i_price": cheapest_t2i_price,
    },
    "warnings": warnings,
}

if cache_file:
    import os
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(cache, f, indent=2)
else:
    print(json.dumps(cache, indent=2))

print(f"📊 {len(video_models)} video, {len(image_models)} image models", file=sys.stderr)
print(f"⚠️  {len(warnings)} warnings", file=sys.stderr)
for w in warnings:
    print(f"   ⚠️  {w}", file=sys.stderr)
print(f"💰 Cheapest t2v: {cheapest_t2v} (${cheapest_t2v_price:.4f})", file=sys.stderr)
print(f"💰 Cheapest i2v: {cheapest_i2v} (${cheapest_i2v_price:.4f})", file=sys.stderr)
print(f"💰 Cheapest t2i: {cheapest_t2i} (${cheapest_t2i_price:.4f})", file=sys.stderr)
