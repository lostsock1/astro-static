# PPQ Model Library

Self-contained model catalog and lookup tools for PPQ.AI video and image generation.

## Files

| File | Purpose |
|------|---------|
| `ppq-models.md` | Full PPQ model catalog — all t2v, i2v, t2i models with pricing, capabilities, known issues |
| `model-lookup.sh` | Quick model search by name or capability |
| `refresh-models.sh` | Regenerate `ppq-models.md` from live PPQ API (`--force` to skip cache) |
| `validate-models.sh` | Validate listed models against current PPQ API availability |
| `media-guard.py` | Validate image dimensions match target aspect ratio before i2v submission |
| `_parse_models.py` | Internal: parse PPQ `/v1/models` response |
| `_curate_models.py` | Internal: curate and format model data into markdown |

## Quick Lookup

```bash
# Find all i2v models
bash models/model-lookup.sh i2v

# Find cheapest 1080p i2v
bash models/model-lookup.sh 1080p

# Refresh catalog from PPQ API
bash models/refresh-models.sh --force

# Validate an image before i2v submission
python models/media-guard.py --scene hero --width 1920 --height 1080 --target 16:9
```
