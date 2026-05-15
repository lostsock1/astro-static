# PPQ Model Library — Film-Making Reference

Auto-generated from PPQ API. **Queried**: 2026-05-13T19:46:01.521661+00:00

Refresh: `bash ~/.config/opencode/skills/filmmaker/scripts/refresh-model-library.sh [--force]`

## Quick Reference

- **Cheapest t2v**: `runway-gen4` — $0.0690
- **Cheapest i2v**: `kling-v1-standard-i2v` — $0.1725
- **Cheapest t2i**: `gpt-image-2` — $0.0115

## Recommended t2i → i2v Chains

| Chain | t2i Model | i2v Model | Est. Total/scene | Notes |
|-------|-----------|-----------|-----------------|-------|
| **budget** | `fast-sdxl` | `haiper-video-v2-i2v` | $0.2444 | Cheapest possible chain. SDXL + Haiper. Preview quality only. |
| **standard** | `nano-banana-2` | `kling-2.5-turbo-i2v` | $0.6095 | Good quality/price. Gemini Flash t2i → Kling Turbo i2v. |
| **kling_native** | `kling-o1-image` | `kling-2.5-turbo-i2v` | $0.5635 | Kling-native chain. Best consistency for Kling video output. |
| **premium** | `nano-banana-pro` | `veo3-fast-i2v` | $1.0235 | Premium chain. Gemini 3 Pro → Veo 3 Fast i2v with audio. |
| **ultra** | `nano-banana-pro` | `veo3-i2v` | $3.7835 | Maximum quality. Gemini 3 Pro → Veo 3 Quality i2v with audio. |

## Video Models (Text-to-Video)

| Model | Tier | Cheapest | Prompt Dialect | Best For |
|-------|------|----------|----------------|----------|
| `grok-imagine-video-t2v` | 🟡 STANDARD | $0.3450 | grok | xAI ecosystem, longer clips at 480p |
| `hailuo-02-pro` | 🟡 STANDARD | $0.5750 | hailuo | MiniMax ecosystem video |
| `hailuo-02-standard` | 🟡 STANDARD | $0.5750 | hailuo | Standard MiniMax video |
| `haiper-video-v2` | 🟢 BUDGET | $0.1840 | haiper | Budget video generation |
| `kling-2.1-master` | 🔴 PREMIUM | $1.4375 | kling | Highest-quality Kling output at 1080p |
| `kling-2.1-pro` | 🟡 STANDARD | $0.2875 | kling | Standard-quality Kling at best value |
| `kling-2.1-standard` | 🟢 BUDGET | $0.1437 | kling | Rough previews, animatics |
| `kling-2.5-turbo` | 🟡 STANDARD | $0.5175 | kling | Quick Kling iterations, balanced quality |
| `kling-3.0` | 🔴 PREMIUM | $1.2880 | kling | Action sequences, physics-heavy scenes |
| `kling-o3-pro` | 🔴 PREMIUM | $1.2880 | kling | Premium Kling shots |
| `kling-o3-standard` | 🟡 STANDARD | $0.9660 | kling | Longer Kling clips (10s, 15s) |
| `kling-v1-standard` | 🟢 BUDGET | $1.7500 | kling | N/A — use newer Kling models |
| `luma-dream-machine` | 🟡 STANDARD | $0.5750 | luma | Luma ecosystem, dreamlike content |
| `minimax-video` | 🟡 STANDARD | $0.5750 | hailuo | N/A — prefer hailuo-02-pro |
| `mochi-v1` | 🟡 STANDARD | $0.4600 | mochi | N/A — legacy |
| `pika-v2.2` | 🟡 STANDARD | $0.5347 | pika | Pika ecosystem, stylized content |
| `pixverse-v4.5` | 🟡 STANDARD | $0.4600 | pixverse | PixVerse ecosystem |
| `runway-aleph` | 🟡 STANDARD | $0.4312 | runway | Runway quality above Gen-4 |
| `runway-gen4` | 🟢 BUDGET | $0.0690 | runway | Budget projects, high-volume generation |
| `seedance-2` | 🔴 PREMIUM | $0.5400 | seedance | Premium ByteDance video, Chinese-market  |
| `seedance-2-fast` | 🟡 STANDARD | $0.4300 | seedance | Seedance quality at better speed/price |
| `seedance-v1-lite` | 🟢 BUDGET | $0.2970 | seedance | Budget Seedance, quick previews |
| `veo3` | 🔴 PREMIUM | $1.1500 | veo | Cinematic establishing shots with ambien |
| `veo3-fast` | 🟡 STANDARD | $0.5750 | veo | Quick iterations, budget-conscious Veo q |
| `wan-t2v` | 🟡 STANDARD | $0.4600 | wan | Wan ecosystem |

## Video Model Details

### `grok-imagine-video-t2v` — Grok Imagine Video (Text-to-Video) 🟡 STANDARD

**Best for**: xAI ecosystem, longer clips at 480p
**Prompt length**: 50-150 words
**Strengths**: 480p and 720p; Up to 15s duration; Resolution control

| Config | Price |
|--------|-------|
  Quality: **standard**
  | `480p 10` | $0.5750 |
  | `480p 15` | $0.8625 |
  | `480p 6` | $0.3450 |
  | `720p 10` | $0.8050 |
  | `720p 15` | $1.2075 |
  | `720p 6` | $0.4830 |
  | `default` | $0.4830 |

⚠️ **Gotchas**: Grok's video model — newer, less battle-tested

---

### `hailuo-02-pro` — MiniMax Hailuo 02 Pro 🟡 STANDARD

**Best for**: MiniMax ecosystem video
**Prompt length**: 50-150 words
**Strengths**: MiniMax's best video model; Image reference support

| Config | Price |
|--------|-------|
  | `default` | $0.5750 |

⚠️ **Gotchas**: Flat pricing — no quality/duration variants

---

### `hailuo-02-standard` — MiniMax Hailuo 02 Standard 🟡 STANDARD

**Best for**: Standard MiniMax video
**Prompt length**: 50-150 words
**Strengths**: Same price as Pro tier; Image reference

| Config | Price |
|--------|-------|
  | `default` | $0.5750 |

⚠️ **Gotchas**: Same price as Pro — prefer hailuo-02-pro

---

### `haiper-video-v2` — Haiper Video V2 🟢 BUDGET

**Best for**: Budget video generation
**Prompt length**: 50-100 words
**Strengths**: Cheap ($0.184); Resolution control

| Config | Price |
|--------|-------|
  | `default` | $0.1840 |

⚠️ **Gotchas**: No aspect ratio control; No image reference

---

### `kling-2.1-master` — Kling 2.1 Master 🔴 PREMIUM

**Best for**: Highest-quality Kling output at 1080p
**Prompt length**: 50-150 words
**Strengths**: 1080p native; Negative prompt; Image-to-video capable

| Config | Price |
|--------|-------|
  Quality: **1080p**
  | `16:9 10` | $1.8400 |
  | `16:9 5` | $1.4375 |
  | `1:1 10` | $1.8400 |
  | `1:1 5` | $1.4375 |
  | `9:16 10` | $1.8400 |
  | `9:16 5` | $1.4375 |

⚠️ **Gotchas**: Expensive — use for hero shots only; Same dialect as all Kling models

---

### `kling-2.1-pro` — Kling 2.6 (was 2.1 Pro) 🟡 STANDARD

**Best for**: Standard-quality Kling at best value
**Prompt length**: 50-150 words
**Strengths**: 1080p at budget price; Negative prompt; t2v + i2v

| Config | Price |
|--------|-------|
  Quality: **1080p**
  | `16:9 10` | $0.5750 |
  | `16:9 5` | $0.2875 |
  | `1:1 10` | $0.5750 |
  | `1:1 5` | $0.2875 |
  | `9:16 10` | $0.5750 |
  | `9:16 5` | $0.2875 |

⚠️ **Gotchas**: Renamed to Kling 2.6 — same model, new branding

🚫 **Known issues**: size_param_underscore_bug — same bug as kling-2.1-standard. UNUSABLE.

---

### `kling-2.1-standard` — Kling 2.6 (was 2.1 Standard) 🟢 BUDGET

**Best for**: Rough previews, animatics
**Prompt length**: 50-150 words
**Strengths**: Cheapest Kling option; 720p

| Config | Price |
|--------|-------|
  Quality: **720p**
  | `16:9 10` | $0.2875 |
  | `16:9 5` | $0.1437 |
  | `1:1 10` | $0.2875 |
  | `1:1 5` | $0.1437 |
  | `9:16 10` | $0.2875 |
  | `9:16 5` | $0.1437 |

⚠️ **Gotchas**: 720p only; KNOWN BUG: size param underscore issue — may be unreliable

🚫 **Known issues**: size_param_underscore_bug — server strips text after '_' in size. UNUSABLE.

---

### `kling-2.5-turbo` — Kling 2.5 Turbo Pro 🟡 STANDARD

**Best for**: Quick Kling iterations, balanced quality/speed
**Prompt length**: 50-150 words
**Strengths**: Fast Kling generation; Negative prompt

| Config | Price |
|--------|-------|
  Quality: **standard**
  | `16:9 10` | $0.5175 |
  | `16:9 5` | $0.5175 |
  | `9:16 10` | $0.5175 |
  | `9:16 5` | $0.5175 |

⚠️ **Gotchas**: 16:9 and 9:16 only (no 1:1)

---

### `kling-3.0` — Kling 3.0 🔴 PREMIUM

**Best for**: Action sequences, physics-heavy scenes
**Prompt length**: 50-150 words
**Strengths**: Physics-strong; Detail-tolerant; Negative prompt support

| Config | Price |
|--------|-------|
  Quality: **standard**
  | `16:9 10` | $2.0700 |
  | `16:9 5` | $1.2880 |
  | `9:16 10` | $2.0700 |
  | `9:16 5` | $1.2880 |

⚠️ **Gotchas**: Always use negative prompt; Specify hand positions when visible

---

### `kling-o3-pro` — Kling O3 Pro 🔴 PREMIUM

**Best for**: Premium Kling shots
**Prompt length**: 50-150 words
**Strengths**: Highest Kling O3 quality

| Config | Price |
|--------|-------|
  | `default` | $1.2880 |

⚠️ **Gotchas**: Flat pricing — no duration/quality variants

---

### `kling-o3-standard` — Kling O3 Standard 🟡 STANDARD

**Best for**: Longer Kling clips (10s, 15s)
**Prompt length**: 50-150 words
**Strengths**: Up to 15s duration; Negative prompt; Image-to-video

| Config | Price |
|--------|-------|
  Quality: **standard**
  | `10` | $1.9320 |
  | `15` | $2.8980 |
  | `5` | $0.9660 |

⚠️ **Gotchas**: Pricey at 15s ($2.898)

---

### `kling-v1-standard` — Kling V1 Standard 🟢 BUDGET

**Best for**: N/A — use newer Kling models
**Prompt length**: 50-150 words
**Strengths**: Legacy Kling model

| Config | Price |
|--------|-------|
  | `default` | $1.7500 |

⚠️ **Gotchas**: LEGACY — prefer kling-2.1-standard or kling-2.5-turbo

---

### `luma-dream-machine` — Luma Dream Machine 🟡 STANDARD

**Best for**: Luma ecosystem, dreamlike content
**Prompt length**: 50-100 words
**Strengths**: Aspect ratio control

| Config | Price |
|--------|-------|
  | `default` | $0.5750 |

⚠️ **Gotchas**: No image reference support

---

### `minimax-video` — MiniMax Video 🟡 STANDARD

**Best for**: N/A — prefer hailuo-02-pro
**Prompt length**: 50-150 words
**Strengths**: Legacy MiniMax video; Image reference

| Config | Price |
|--------|-------|
  | `default` | $0.5750 |

⚠️ **Gotchas**: LEGACY — use hailuo-02-pro instead

---

### `mochi-v1` — Mochi V1 🟡 STANDARD

**Best for**: N/A — legacy
**Prompt length**: 50-100 words
**Strengths**: Genmo's video model

| Config | Price |
|--------|-------|
  | `default` | $0.4600 |

⚠️ **Gotchas**: LEGACY — no longer actively developed

---

### `pika-v2.2` — Pika V2.2 🟡 STANDARD

**Best for**: Pika ecosystem, stylized content
**Prompt length**: 50-100 words
**Strengths**: Negative prompt; Aspect ratio control; Image reference

| Config | Price |
|--------|-------|
  | `default` | $0.5347 |

⚠️ **Gotchas**: Flat pricing — no quality variants

---

### `pixverse-v4.5` — PixVerse V4.5 🟡 STANDARD

**Best for**: PixVerse ecosystem
**Prompt length**: 50-100 words
**Strengths**: Negative prompt; Aspect ratio control; Image reference

| Config | Price |
|--------|-------|
  | `default` | $0.4600 |

⚠️ **Gotchas**: i2v fails with 404 — PPQ signed URLs not accessible to pixverse provider

🚫 **Known issues**: i2v_unavailable: i2v fails with 404 — PPQ signed URLs not accessible to pixverse provider.

---

### `runway-aleph` — Runway Aleph 🟡 STANDARD

**Best for**: Runway quality above Gen-4
**Prompt length**: 30-80 words
**Strengths**: Runway's latest model; 5s/10s options

| Config | Price |
|--------|-------|
  Quality: **standard**
  | `10` | $0.8625 |
  | `5` | $0.4312 |

⚠️ **Gotchas**: No aspect_ratio control; No image reference support

---

### `runway-gen4` — Runway Gen-4 🟢 BUDGET

**Best for**: Budget projects, high-volume generation
**Prompt length**: 30-80 words
**Strengths**: Cheapest video model on PPQ; 720p and 1080p options; Image reference support

| Config | Price |
|--------|-------|
  Quality: **720p**
  | `16:9 10` | $0.1725 |
  | `16:9 5` | $0.0690 |
  | `9:16 10` | $0.1725 |
  | `9:16 5` | $0.0690 |
  Quality: **1080p**
  | `16:9 5` | $0.1725 |
  | `9:16 5` | $0.1725 |

⚠️ **Gotchas**: 720p is extremely cheap ($0.069); 1080p limited to 5s

🚫 **Known issues**: i2v_unavailable: Listed as accepts_image=true but i2v returns 'no providers available'.

---

### `seedance-2` — Seedance 2.0 🔴 PREMIUM

**Best for**: Premium ByteDance video, Chinese-market content
**Prompt length**: Detailed scene descriptions
**Strengths**: 480p/720p resolution control; 4-15s duration; Image reference; High quality

| Config | Price |
|--------|-------|
  Quality: **standard**
  | `480p 10` | $1.3500 |
  | `480p 15` | $2.0200 |
  | `480p 4` | $0.5400 |
  | `480p 5` | $0.6700 |
  | `480p 8` | $1.0800 |
  | `720p 10` | $3.0200 |
  | `720p 15` | $4.5400 |
  | `720p 4` | $1.2100 |
  | `720p 5` | $1.5100 |
  | `720p 8` | $2.4200 |
  | `default` | $1.5100 |

⚠️ **Gotchas**: Expensive at 720p 15s ($4.54); Use @ reference syntax for best results

---

### `seedance-2-fast` — Seedance 2.0 Fast 🟡 STANDARD

**Best for**: Seedance quality at better speed/price
**Prompt length**: Detailed scene descriptions
**Strengths**: Same as seedance-2 but ~20% cheaper/faster; 480p/720p; 4-15s

| Config | Price |
|--------|-------|
  Quality: **standard**
  | `480p 10` | $1.0800 |
  | `480p 15` | $1.6100 |
  | `480p 4` | $0.4300 |
  | `480p 5` | $0.5400 |
  | `480p 8` | $0.8600 |
  | `720p 10` | $2.4200 |
  | `720p 15` | $3.6300 |
  | `720p 4` | $0.9700 |
  | `720p 5` | $1.2100 |
  | `720p 8` | $1.9400 |
  | `default` | $1.2100 |

⚠️ **Gotchas**: Slightly lower quality ceiling than seedance-2

---

### `seedance-v1-lite` — Seedance V1 Lite 🟢 BUDGET

**Best for**: Budget Seedance, quick previews
**Prompt length**: 50-100 words
**Strengths**: Cheap Seedance access; Resolution + aspect ratio control

| Config | Price |
|--------|-------|
  | `default` | $0.2970 |

⚠️ **Gotchas**: Lower quality than seedance-2

---

### `veo3` — Veo 3 (Quality) 🔴 PREMIUM

**Best for**: Cinematic establishing shots with ambient audio
**Prompt length**: 100-300 words
**Strengths**: Narrative-heavy detail tolerance (100-300 words); Audio-native generation; Multiple aspect ratios

| Config | Price |
|--------|-------|
  Quality: **standard**
  | `16:9 5` | $2.3000 |
  | `16:9 5 no audio` | $1.1500 |
  | `16:9 8` | $3.6800 |
  | `16:9 8 no audio` | $1.8400 |
  | `1:1 5` | $2.3000 |
  | `1:1 8` | $3.6800 |
  | `9:16 5` | $2.3000 |
  | `9:16 5 no audio` | $1.1500 |
  | `9:16 8` | $3.6800 |
  | `9:16 8 no audio` | $1.8400 |
  | `default` | $3.6800 |

⚠️ **Gotchas**: No negative prompt — use positive exclusion like 'desolate landscape with no buildings'; Describe temporal progression: starts with... then... finally...

---

### `veo3-fast` — Veo 3 (Fast) 🟡 STANDARD

**Best for**: Quick iterations, budget-conscious Veo quality
**Prompt length**: 50-150 words
**Strengths**: Same Veo quality, faster generation; Audio-native; Cheaper than veo3

| Config | Price |
|--------|-------|
  Quality: **standard**
  | `16:9 5` | $0.8625 |
  | `16:9 5 no audio` | $0.5750 |
  | `16:9 8` | $1.3800 |
  | `16:9 8 no audio` | $0.9200 |
  | `1:1 5` | $0.8625 |
  | `1:1 8` | $1.3800 |
  | `9:16 5` | $0.8625 |
  | `9:16 5 no audio` | $0.5750 |
  | `9:16 8` | $1.3800 |
  | `9:16 8 no audio` | $0.9200 |
  | `default` | $1.3800 |

⚠️ **Gotchas**: Same dialect as veo3 but shorter prompts preferred (50-150 words)

---

### `wan-t2v` — Wan (Text-to-Video) 🟡 STANDARD

**Best for**: Wan ecosystem
**Prompt length**: 50-100 words
**Strengths**: Negative prompt; Aspect ratio + image reference

| Config | Price |
|--------|-------|
  | `default` | $0.4600 |

⚠️ **Gotchas**: Flat pricing

---

## Image-to-Video Models (Dedicated)

| Model | Tier | Cheapest | Dialect | Best For |
|-------|------|----------|---------|----------|
| `grok-imagine-video-i2v` | 🟡 STANDARD | $0.3473 | grok | xAI ecosystem i2v |
| `grok-imagine-video-v2v` | 🟡 STANDARD | $0.4140 | ? |  |
| `hailuo-02-fast-i2v` | 🟡 STANDARD | $0.5750 | ? |  |
| `hailuo-02-pro-i2v` | 🟡 STANDARD | $0.5750 | ? |  |
| `hailuo-02-standard-i2v` | 🟡 STANDARD | $0.5750 | ? |  |
| `haiper-video-v2-i2v` | 🟢 BUDGET | $0.2300 | haiper | Budget image-to-video |
| `kling-2.1-master-i2v` | 🔴 PREMIUM | $0.9200 | kling | Premium Kling i2v |
| `kling-2.1-pro-i2v` | 🟡 STANDARD | $0.5625 | kling | Mid-tier Kling i2v |
| `kling-2.5-turbo-i2v` | 🟡 STANDARD | $0.5175 | kling | Standard Kling i2v, best value |
| `kling-o3-pro-i2v` | 🔴 PREMIUM | $1.2880 | kling | Best Kling i2v quality |
| `kling-o3-standard-i2v` | 🟡 STANDARD | $0.9660 | kling | Longer Kling i2v clips |
| `kling-o3-standard-v2v` | 🟡 STANDARD | $1.4490 | ? |  |
| `kling-v1-standard-i2v` | 🟡 STANDARD | $0.1725 | ? |  |
| `luma-dream-machine-i2v` | 🟡 STANDARD | $0.5750 | ? |  |
| `minimax-i2v` | 🟡 STANDARD | $0.5750 | ? |  |
| `pika-i2v` | 🟡 STANDARD | $0.5347 | ? |  |
| `pika-pikaffects` | 🟡 STANDARD | $0.5347 | ? |  |
| `pixverse-i2v` | 🟡 STANDARD | $0.4600 | ? |  |
| `seedance-2-fast-i2v` | 🟡 STANDARD | $0.4300 | seedance | Seedance i2v at better speed/price |
| `seedance-2-i2v` | 🔴 PREMIUM | $0.5400 | seedance | Premium Seedance i2v |
| `veo3-fast-i2v` | 🟡 STANDARD | $0.9200 | veo | Veo quality i2v at better price |
| `veo3-i2v` | 🔴 PREMIUM | $1.8400 | veo | Premium image-to-video with ambient audi |
| `wan-i2v` | 🟡 STANDARD | $0.4600 | ? |  |
| `wan-v2.2-i2v` | 🟡 STANDARD | $0.4600 | ? |  |

### i2v Pricing Details

**`grok-imagine-video-i2v`** 🟡 STANDARD
- Best for: xAI ecosystem i2v
  Quality: **standard**
  | `480p 10` | $0.5773 |
  | `480p 15` | $0.8648 |
  | `480p 6` | $0.3473 |
  | `720p 10` | $0.8073 |
  | `720p 15` | $1.2098 |
  | `720p 6` | $0.4853 |
  | `default` | $0.4853 |

**`grok-imagine-video-v2v`** 🟡 STANDARD
  Quality: **standard**
  | `480p` | $0.4140 |
  | `720p` | $0.5520 |
  | `auto` | $0.4140 |
  | `default` | $0.4140 |

**`hailuo-02-fast-i2v`** 🟡 STANDARD
  | `default` | $0.5750 |

**`hailuo-02-pro-i2v`** 🟡 STANDARD
  | `default` | $0.5750 |

**`hailuo-02-standard-i2v`** 🟡 STANDARD
  | `default` | $0.5750 |

**`haiper-video-v2-i2v`** 🟢 BUDGET
- Best for: Budget image-to-video
  | `default` | $0.2300 |

**`kling-2.1-master-i2v`** 🔴 PREMIUM
- Best for: Premium Kling i2v
  Quality: **1080p**
  | `10` | $1.8400 |
  | `5` | $0.9200 |

**`kling-2.1-pro-i2v`** 🟡 STANDARD
- Best for: Mid-tier Kling i2v
  | `default` | $0.5625 |

**`kling-2.5-turbo-i2v`** 🟡 STANDARD
- Best for: Standard Kling i2v, best value
  Quality: **standard**
  | `10` | $0.5175 |
  | `5` | $0.5175 |

**`kling-o3-pro-i2v`** 🔴 PREMIUM
- Best for: Best Kling i2v quality
  | `default` | $1.2880 |

**`kling-o3-standard-i2v`** 🟡 STANDARD
- Best for: Longer Kling i2v clips
  Quality: **standard**
  | `10` | $1.9320 |
  | `15` | $2.8980 |
  | `5` | $0.9660 |

**`kling-o3-standard-v2v`** 🟡 STANDARD
  Quality: **standard**
  | `10` | $2.8980 |
  | `5` | $1.4490 |

**`kling-v1-standard-i2v`** 🟡 STANDARD
  | `default` | $0.1725 |

**`luma-dream-machine-i2v`** 🟡 STANDARD
  | `default` | $0.5750 |

**`minimax-i2v`** 🟡 STANDARD
  | `default` | $0.5750 |

**`pika-i2v`** 🟡 STANDARD
  | `default` | $0.5347 |

**`pika-pikaffects`** 🟡 STANDARD
  | `default` | $0.5347 |

**`pixverse-i2v`** 🟡 STANDARD
  | `default` | $0.4600 |

**`seedance-2-fast-i2v`** 🟡 STANDARD
- Best for: Seedance i2v at better speed/price
  Quality: **standard**
  | `480p 10` | $1.0800 |
  | `480p 15` | $1.6100 |
  | `480p 4` | $0.4300 |
  | `480p 5` | $0.5400 |
  | `480p 8` | $0.8600 |
  | `720p 10` | $2.4200 |
  | `720p 15` | $3.6300 |
  | `720p 4` | $0.9700 |
  | `720p 5` | $1.2100 |
  | `720p 8` | $1.9400 |
  | `default` | $1.2100 |

**`seedance-2-i2v`** 🔴 PREMIUM
- Best for: Premium Seedance i2v
  Quality: **standard**
  | `480p 10` | $1.3500 |
  | `480p 15` | $2.0200 |
  | `480p 4` | $0.5400 |
  | `480p 5` | $0.6700 |
  | `480p 8` | $1.0800 |
  | `720p 10` | $3.0200 |
  | `720p 15` | $4.5400 |
  | `720p 4` | $1.2100 |
  | `720p 5` | $1.5100 |
  | `720p 8` | $2.4200 |
  | `default` | $1.5100 |

**`veo3-fast-i2v`** 🟡 STANDARD
- Best for: Veo quality i2v at better price
  Quality: **standard**
  | `16:9` | $1.3800 |
  | `16:9 no audio` | $0.9200 |
  | `9:16` | $1.3800 |
  | `9:16 no audio` | $0.9200 |
  | `default` | $1.3800 |

**`veo3-i2v`** 🔴 PREMIUM
- Best for: Premium image-to-video with ambient audio
  Quality: **standard**
  | `16:9` | $3.6800 |
  | `16:9 no audio` | $1.8400 |
  | `9:16` | $3.6800 |
  | `9:16 no audio` | $1.8400 |
  | `default` | $3.6800 |

**`wan-i2v`** 🟡 STANDARD
  | `default` | $0.4600 |

**`wan-v2.2-i2v`** 🟡 STANDARD
  | `default` | $0.4600 |

---

## Image Models (Text-to-Image)

| Model | Tier | Cheapest | Dialect | Best For |
|-------|------|----------|---------|----------|
| `aura-sr` | 🟡 STANDARD | $0.0021 | ? |  |
| `clarity-upscaler` | 🟡 STANDARD | $0.0021 | ? |  |
| `fast-sdxl` | 🟢 BUDGET | $0.0144 | sdxl | Quick previews, animatics, budget refere |
| `flux-2-flex` | 🟢 BUDGET | $0.0805 | flux | Budget Flux quality |
| `flux-2-pro` | 🟡 STANDARD | $0.0287 | flux | Flux-quality generation at competitive p |
| `flux-2-pro-i2i` | 🟡 STANDARD | $0.0287 | flux | Editing existing images with Flux qualit |
| `flux-kontext-max` | 🟡 STANDARD | $0.0575 | ? |  |
| `flux-kontext-pro` | 🟡 STANDARD | $0.0287 | flux | Contextual image editing |
| `flux-pro` | 🟡 STANDARD | $0.0907 | ? |  |
| `gpt-image-1` | 🟡 STANDARD | $0.0230 | gpt-image | Compatibility with GPT-4o image workflow |
| `gpt-image-1.5` | 🟡 STANDARD | $0.0230 | gpt-image | Mid-tier image generation |
| `gpt-image-2` | 🟡 STANDARD | $0.0115 | gpt-image | General-purpose image generation, best q |
| `grok-imagine` | 🟡 STANDARD | $0.0330 | grok | xAI ecosystem image generation |
| `grok-imagine-edit` | 🟡 STANDARD | $0.0330 | ? |  |
| `imagen3` | 🟡 STANDARD | $0.0460 | imagen | Reliable Google-quality images |
| `imagen4-preview` | 🟡 STANDARD | $0.0575 | imagen | Google-quality image generation |
| `kling-o1-image` | 🟡 STANDARD | $0.0460 | kling | Kling ecosystem reference frames for Kli |
| `nano-banana-2` | 🟡 STANDARD | $0.0690 | gemini | Good quality at reasonable price, resolu |
| `nano-banana-2-edit` | 🟡 STANDARD | $0.0690 | ? |  |
| `nano-banana-pro` | 🔴 PREMIUM | $0.1035 | gemini | Premium Google-quality images |
| `qwen-image` | 🟡 STANDARD | $0.0460 | qwen | Qwen ecosystem images |
| `qwen-image-i2i` | 🟡 STANDARD | $0.0460 | ? |  |
| `recraft-v3` | 🟡 STANDARD | $0.0460 | recraft | Vector-style imagery, design-focused |
| `recraft-v3-svg` | 🟡 STANDARD | $0.0920 | ? |  |
| `rembg` | 🟡 STANDARD | $0.0021 | ? |  |
| `seedream-4.5` | 🟡 STANDARD | $0.0460 | seedream | ByteDance ecosystem, stylized images |
| `seedream-4.5-edit` | 🟡 STANDARD | $0.0660 | ? |  |
| `topaz-upscale` | 🟡 STANDARD | $0.0413 | ? |  |

### Image Model Details

**`aura-sr`** 🟡 STANDARD
  | `default` | $0.0021 |

**`clarity-upscaler`** 🟡 STANDARD
  | `default` | $0.0021 |

**`fast-sdxl`** 🟢 BUDGET
- Best for: Quick previews, animatics, budget reference frames
- ⚠️ SDXL quality ceiling — not for final output
  | `default` | $0.0144 |

**`flux-2-flex`** 🟢 BUDGET
- Best for: Budget Flux quality
- ⚠️ Higher base price than flux-2-pro for some sizes
  Quality: **1k**
  | `default` | $0.0805 |
  Quality: **2k**
  | `default` | $0.1380 |

**`flux-2-pro`** 🟡 STANDARD
- Best for: Flux-quality generation at competitive price
- ⚠️ Pro version — use flux-2-flex for budget
  Quality: **1k**
  | `default` | $0.0287 |
  Quality: **2k**
  | `default` | $0.0403 |

**`flux-2-pro-i2i`** 🟡 STANDARD
- Best for: Editing existing images with Flux quality
- ⚠️ Requires source image_url
  Quality: **1k**
  | `default` | $0.0287 |
  Quality: **2k**
  | `default` | $0.0403 |

**`flux-kontext-max`** 🟡 STANDARD
  | `default` | $0.0575 |

**`flux-kontext-pro`** 🟡 STANDARD
- Best for: Contextual image editing
- ⚠️ Different from flux-2-pro — purpose-built for context
  | `default` | $0.0287 |

**`flux-pro`** 🟡 STANDARD
  | `default` | $0.0907 |

**`gpt-image-1`** 🟡 STANDARD
- Best for: Compatibility with GPT-4o image workflows
- ⚠️ Prefer gpt-image-2 for new projects
  Quality: **low**
  | `default` | $0.0230 |
  Quality: **medium**
  | `default` | $0.0805 |
  Quality: **high**
  | `default` | $0.2185 |

**`gpt-image-1.5`** 🟡 STANDARD
- Best for: Mid-tier image generation
- ⚠️ Overlapping pricing with gpt-image-2
  Quality: **low**
  | `default` | $0.0230 |
  Quality: **medium**
  | `default` | $0.0586 |
  Quality: **high**
  | `default` | $0.2300 |

**`gpt-image-2`** 🟡 STANDARD
- Best for: General-purpose image generation, best quality/price ratio
- ⚠️ Quality tiers affect pricing significantly
  Quality: **low**
  | `default` | $0.0115 |
  Quality: **medium**
  | `default` | $0.0690 |
  Quality: **high**
  | `default` | $0.2530 |

**`grok-imagine`** 🟡 STANDARD
- Best for: xAI ecosystem image generation
- ⚠️ Edit variant available (grok-imagine-edit)
  | `default` | $0.0330 |

**`grok-imagine-edit`** 🟡 STANDARD
  | `default` | $0.0330 |

**`imagen3`** 🟡 STANDARD
- Best for: Reliable Google-quality images
- ⚠️ Prefer imagen4-preview for new projects
  | `default` | $0.0460 |

**`imagen4-preview`** 🟡 STANDARD
- Best for: Google-quality image generation
- ⚠️ Preview — pricing may change
  | `default` | $0.0575 |

**`kling-o1-image`** 🟡 STANDARD
- Best for: Kling ecosystem reference frames for Kling video
- ⚠️ Good t2i→i2v chain pairing with Kling video models
  | `default` | $0.0460 |

**`nano-banana-2`** 🟡 STANDARD
- Best for: Good quality at reasonable price, resolution control
- ⚠️ Edit variant available (nano-banana-2-edit)
  Quality: **standard**
  | `1K` | $0.0920 |
  | `2K` | $0.1380 |
  | `4K` | $0.1840 |
  | `512x512` | $0.0690 |
  | `default` | $0.0920 |

**`nano-banana-2-edit`** 🟡 STANDARD
  Quality: **standard**
  | `1K` | $0.0920 |
  | `2K` | $0.1380 |
  | `4K` | $0.1840 |
  | `512x512` | $0.0690 |
  | `default` | $0.0920 |

**`nano-banana-pro`** 🔴 PREMIUM
- Best for: Premium Google-quality images
- ⚠️ PPQ branded as 'Nano Banana Pro'
  Quality: **standard**
  | `default` | $0.1035 |
  Quality: **4k**
  | `default` | $0.1380 |

**`qwen-image`** 🟡 STANDARD
- Best for: Qwen ecosystem images
- ⚠️ Both t2i and i2i at same price
  | `default` | $0.0460 |

**`qwen-image-i2i`** 🟡 STANDARD
  | `default` | $0.0460 |

**`recraft-v3`** 🟡 STANDARD
- Best for: Vector-style imagery, design-focused
- ⚠️ SVG variant costs 2x (recraft-v3-svg)
  | `default` | $0.0460 |

**`recraft-v3-svg`** 🟡 STANDARD
  | `default` | $0.0920 |

**`rembg`** 🟡 STANDARD
  | `default` | $0.0021 |

**`seedream-4.5`** 🟡 STANDARD
- Best for: ByteDance ecosystem, stylized images
- ⚠️ Edit variant available (seedream-4.5-edit)
  | `default` | $0.0460 |

**`seedream-4.5-edit`** 🟡 STANDARD
  | `default` | $0.0660 |

**`topaz-upscale`** 🟡 STANDARD
  | `default` | $0.0413 |

---

## Video Capability Matrix

| Model | Audio | i2v | Neg. Prompt | Aspect Ratio | Duration(s) |
|-------|-------|-----|-------------|-------------|-------------|
| `grok-imagine-video-t2v` | ❌ | ✅ | ❌ | ✅ | 10, 15, 6 |
| `hailuo-02-pro` | ❌ | ✅ | ❌ | ✅ | default |
| `hailuo-02-standard` | ❌ | ✅ | ❌ | ✅ | default |
| `haiper-video-v2` | ❌ | ❌ | ❌ | ❌ | default |
| `kling-2.1-master` | ❌ | ✅ | ✅ | ✅ | 10, 5 |
| `kling-2.1-pro` | ❌ | ✅ | ✅ | ✅ | 10, 5 |
| `kling-2.1-standard` | ❌ | ✅ | ✅ | ✅ | 10, 5 |
| `kling-2.5-turbo` | ❌ | ✅ | ✅ | ✅ | 10, 5 |
| `kling-3.0` | ❌ | ✅ | ✅ | ✅ | 10, 5 |
| `kling-o3-pro` | ❌ | ✅ | ✅ | ✅ | default |
| `kling-o3-standard` | ❌ | ✅ | ✅ | ✅ | 10, 15, 5 |
| `kling-v1-standard` | ❌ | ✅ | ✅ | ✅ | default |
| `luma-dream-machine` | ❌ | ❌ | ❌ | ✅ | default |
| `minimax-video` | ❌ | ✅ | ❌ | ✅ | default |
| `mochi-v1` | ❌ | ❌ | ❌ | ✅ | default |
| `pika-v2.2` | ❌ | ✅ | ✅ | ✅ | default |
| `pixverse-v4.5` | ❌ | ✅ | ✅ | ✅ | default |
| `runway-aleph` | ❌ | ❌ | ❌ | ❌ | 10, 5 |
| `runway-gen4` | ❌ | ✅ | ❌ | ✅ | 10, 5 |
| `seedance-2` | ❌ | ✅ | ❌ | ✅ | 10, 15, 4, 5, 8 |
| `seedance-2-fast` | ❌ | ✅ | ❌ | ✅ | 10, 15, 4, 5, 8 |
| `seedance-v1-lite` | ❌ | ✅ | ❌ | ✅ | default |
| `veo3` | ✅ | ✅ | ❌ | ✅ | 5, 8 |
| `veo3-fast` | ✅ | ❌ | ❌ | ✅ | 5, 8 |
| `wan-t2v` | ❌ | ✅ | ✅ | ✅ | default |

## Budget Scenarios (per project)

| Budget | Scenes | Chain | t2i Cost | i2v Cost | Total | Leftover for rerolls |
|--------|--------|-------|----------|----------|-------|---------------------|
| $5 | 5 | budget | $0.0144 | $0.2300 | $1.22 | $3.78 ✅ |
| $5 | 5 | standard | $0.0690 | $0.5175 | $2.93 | $2.07 ✅ |
| $5 | 5 | kling_native | $0.0460 | $0.5175 | $2.82 | $2.18 ✅ |
| $20 | 10 | standard | $0.0690 | $0.5175 | $5.87 | $14.13 ✅ |
| $20 | 10 | kling_native | $0.0460 | $0.5175 | $5.63 | $14.37 ✅ |
| $20 | 10 | premium | $0.1035 | $0.9200 | $10.24 | $9.76 ✅ |
| $50 | 15 | standard | $0.0690 | $0.5175 | $8.80 | $41.20 ✅ |
| $50 | 15 | premium | $0.1035 | $0.9200 | $15.35 | $34.65 ✅ |
| $50 | 10 | ultra | $0.1035 | $1.8400 | $19.43 | $30.57 ✅ |

## Active Warnings

- ⚠️ BROKEN: kling-2.1-pro — see known_issues
- ⚠️ BROKEN: kling-2.1-standard — see known_issues
- ⚠️ i2v UNAVAILABLE: runway-gen4
- ⚠️ i2v UNAVAILABLE: pixverse-v4.5
