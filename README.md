# astro-static — Multi-Agent Static Site Pipeline for OpenCode

> **Multi-agent pipeline for OpenCode that researches brands, extracts design DNA from reference sites, generates visual assets via AI, builds Astro 5 + Tailwind v4 static sites, and deploys them to a Debian 13 VPS — all orchestrated by a single agent.**

---

## Overview

`astro-static` is an **agentic site generation pipeline** built on the [OpenCode](https://github.com/opencode-ai/opencode) platform. It defines **8 specialized AI subagents**, coordinated by a deterministic orchestrator, that together take a site from a human-written brief to a live, deployed Astro 5 website. The system has been used to generate multiple sites but has not been systematically benchmarked or hardened for arbitrary input.

The pipeline is **phase-gated with human-in-the-loop checkpoints**, **contract-validated at every stage**, and **idempotent at every level** — you can interrupt and resume safely.

### What It Does

1. **Bootstraps a fresh Debian 13 VPS** with Node.js, Bun, Gitea (git server), Caddy (reverse proxy + auto-TLS), and a git-sync watcher for continuous deployment from content changes.
2. **Extracts design tokens** from reference/competitor websites — W3C DTCG JSON, Tailwind v4 `@theme` blocks, CSS/SVG section patterns, and motion signals — using both CSS parsing and computer vision (via kimi-k2.6 multimodal model).
3. **Researches the client business** — brand strategy, competitive landscape, industry trends — and produces a structured creative brief with verified facts, content model definitions, and explicit review flags when source data contradicts the human-provided brief.
4. **Generates visual identity assets** — color palettes (oklch), Google Font pairings, logos, favicon sets, OG images, Tailwind v4 theme CSS — via PPQ.AI `nano-banana-pro` image generation.
5. **Generates content images and optional video backgrounds** — hero images, gallery photos, member portraits, atmospheric looping video backgrounds (via PPQ.AI `kling-3.0`) — with LQIP (Low-Quality Image Placeholder) generation for perceived performance.
6. **Builds a complete Astro 5 site** with Tailwind v4 CSS-first theming, Astro Content Collections, shadcn/ui interactive islands, and optional motion engines (GSAP ScrollTrigger, Motion One, Lottie, Three.js).
7. **Deploys to the VPS** — rsyncs, builds via Bun, smoke-tests, pushes to Gitea, and verifies the live site.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                 CONTROL NODE (your machine)          │
│                                                     │
│  ┌──────────────┐    dispatches subagents           │
│  │ Orchestrator │────────────────────┐              │
│  │ (glm-5.1)    │                    │              │
│  └──────┬───────┘                    │              │
│         │                            ▼              │
│         │ Phases:          ┌──────────────────┐     │
│         │  0. Bootstrap ──▶│  Subagent Team   │     │
│         │  1. Design Extr  │                  │     │
│         │  2. Research ───▶│ researcher       │     │
│         │  2.5 Validation  │ design-extractor │     │
│         │  3. Assets ─────▶│ asset-generator  │     │
│         │  3.5 Images ────▶│   img-gen        │     │
│         │  3.6 Videos ────▶│   vid-gen        │     │
│         │  4. Build ──────▶│ frontend-builder │     │
│         │  5. Deploy        │ auditor          │     │
│         │                   └──────────────────┘     │
│         │                                            │
│  Local: /Users/<you>/SITES/<project>/                │
│         └── pipeline/  (checkpoint artifacts)        │
│                                                     │
└──────────────────┬──────────────────────────────────┘
                   │ SSH
                   ▼
┌─────────────────────────────────────────────────────┐
│              TARGET VPS (Debian 13)                  │
│                                                     │
│  ┌─────────┐  ┌─────────┐  ┌───────────────────┐   │
│  │  Gitea  │  │  Caddy  │  │ /var/www/sites/    │   │
│  │ git     │  │ HTTPS   │  │   <project>/       │   │
│  │ server  │  │ +TLS    │  │   ├── src/         │   │
│  └─────────┘  └─────────┘  │   ├── dist/        │   │
│                             │   └── pipeline/    │   │
│  git-sync watcher           └───────────────────┘   │
│  (auto-rebuild on push)                              │
└─────────────────────────────────────────────────────┘
```

### Key Design Decisions

- **Control node / VPS separation**: All AI work (research, asset generation, code writing) happens locally on the control node. Only the build/runtime artifacts are synced to the VPS via rsync over SSH.
- **Non-blocking bootstrap**: VPS setup runs in the background concurrently with Phases 1–3.6, joining only before Phase 4 (Build). This parallelizes ~3–5 minutes of server setup with pure-local work.
- **Phase gate with human-in-the-loop**: Phase 2.5 (Brief Validation) explicitly checks for unverifiable proper nouns, contradictory requirements, and ambiguous references. The pipeline halts until a human resolves flagged issues — preventing wasted downstream asset generation.
- **Contract-driven architecture**: Every phase produces and validates JSON artifacts against JSON schemas. `validate-pipeline.py` runs at startup and phase transitions to catch drift, missing files, and schema violations early.

---

## Agent Team

| Agent | Model | Role | Mode |
|-------|-------|------|------|
| **orchestrator** | `zai-coding-plan/glm-5.1` | Master coordinator — dispatches subagents, runs phase scripts, validates artifacts, updates state | `primary` |
| **researcher** | `deepseek/deepseek-v4-pro` | Brand strategist — deep research, competitive analysis, creative brief authoring | `subagent` |
| **design-extractor** | `ppq/moonshotai/kimi-k2.6` | Design token extractor — CSS + vision-based extraction from reference sites, outputs W3C DTCG JSON + Tailwind theme | `subagent` |
| **asset-generator** | `deepseek/deepseek-v4-pro` | Visual identity producer — color palettes (oklch), font pairings, logos, favicons, theme CSS, content images, video backgrounds | `subagent` |
| **frontend-builder** | `deepseek/deepseek-v4-pro` | Astro 5 developer — writes all page/component code, Content Collections, responsive layouts, optional GSAP/motion engines, syncs and builds on VPS | `subagent` |
| **img-gen** | `deepseek/deepseek-v4-flash` | Image API worker — calls PPQ.AI `nano-banana-pro`, downloads and validates images | `subagent` |
| **vid-gen** | `deepseek/deepseek-v4-flash` | Video API worker — submits to PPQ.AI `kling-3.0`, polls async, downloads and validates MP4 videos | `subagent` |
| **auditor** | `deepseek/deepseek-v4-pro` | Read-only quality inspector — audits pipeline state, artifact contracts, permissions, and recommends next action | `subagent` |

### Permission Model

All agents use **least-privilege permissions**. Key constraints:
- **orchestrator**: Can SSH/rsync/scp (with `ask` gates), runs phase scripts, dispatches subagents. Denies `rm -rf *`.
- **researcher/design-extractor**: Cannot touch VPS (`ssh: deny`, `scp: deny`, `rsync: deny`). Web research only.
- **asset-generator**: Local-only file creation. Delegates all API calls to `img-gen` and `vid-gen` — never calls PPQ directly.
- **frontend-builder**: Writes code locally, rsyncs on `ask`, builds on VPS via `bun`.
- **img-gen/vid-gen**: Minimal — only `curl` for PPQ API, `mkdir`, file validation.
- **auditor**: Strictly read-only. `edit: deny`, `task: deny`, `skill: deny`. No write-side effects.

---

## Pipeline Phases

### Phase 0: VPS Bootstrap (Background, Non-Blocking)
- Probes VPS state for existing setup
- Launches `setup-vps.sh` in background (3–5 min for fresh VPS)
- Phases 1–3.6 proceed in parallel
- Bootstrap Join (blocking) merges VPS config before Phase 4

### Phase 1: Design Extraction (Conditional)
- Only runs if `00-brief.json` contains reference/competitor URLs
- Dispatches `design-extractor` for CSS + vision extraction
- Outputs: `pipeline/00-design-tokens/` (tokens.json, Tailwind theme.css, section patterns, motion signals)

### Phase 2: Research
- Dispatches `researcher` with search agents (deepeye, worker, proxy, scrapling, crawlee, instagram)
- Produces `pipeline/01-creative-brief.json` (~150-300 lines JSON)
- Includes `content_model`, `color_direction`, `typography_direction`, `motion_direction`
- Verification gate: flags unverified proper nouns, contradictory requirements

### Phase 2.5: Brief Validation Gate (Human-in-the-Loop)
- Scans `review_flags` for blocking issues
- Cross-checks brief against original `00-brief.json`
- If issues found → writes `HUMAN_REVIEW.md`, sets `needs_human_review: true`, HALTS
- Pipeline cannot proceed until a human resolves flagged items

### Phase 3: Asset Generation
- Dispatches `asset-generator` for identity assets
- Outputs: `02-font-config.json`, `02-asset-manifest.json`, `src/styles/theme.css`, logos, favicons, OG image
- WCAG AA contrast validation (≥4.5:1 for text)

### Phase 3.5: Content Image Generation
- Derives image shot list from creative brief's `content_structure`
- Generates hero backgrounds, gallery images, member portraits, section backgrounds
- Produces LQIP (24px base64 WebP) for every image
- Writes typed import index (`src/lib/content-images.ts`) for build-time safety

### Phase 3.6: Video Background Generation (Optional)
- Conditional on `motion_direction.video_backgrounds: true`
- Generates 5s MP4 loops via `kling-3.0` (~$1.29 each)
- Poster images paired from Phase 3.5 content images
- Reduced-motion fallback via CSS

### Phase 4: Frontend Build
- Syncs all local assets to VPS
- Dispatches `frontend-builder` with comprehensive design reasoning framework
- Builds all pages, Content Collections, components
- Runs `astro check` + `astro build` via Bun
- Smoke tests (6 checks: stylesheets, theme tokens, nav links, template rendering, titles)
- Supports optional motion engines: GSAP/ScrollTrigger, Motion One, Lottie, Three.js

### Phase 5: Deploy
- Commits locally, pushes to Gitea on VPS
- Verifies live site via HTTP 200
- Writes `RESULT.md` with all URLs, design summary, cost estimates

---

## Tech Stack (Non-Negotiable)

| Layer | Technology |
|-------|-----------|
| **Site framework** | Astro 5 |
| **CSS framework** | Tailwind v4 (CSS-first, `@theme {}` block, no `tailwind.config.js`) |
| **Component library** | shadcn/ui (React islands) |
| **Content** | Astro Content Collections with Zod schemas, file-backed MDX |
| **Images** | Sharp for WebP/AVIF at build, Pillow for pre-processing, pngquant/jpegoptim |
| **LQIP** | 24px base64 WebP CSS backgrounds, ~300-500 bytes per image |
| **Build tool** | Bun (3-5× faster than npm) |
| **Version control** | Gitea on VPS (self-hosted git) |
| **Reverse proxy** | Caddy (auto-TLS, multi-domain) |
| **Deployment** | git-sync watcher (auto-rebuild on push) |
| **Image generation** | PPQ.AI `nano-banana-pro` (4K raster PNG) |
| **Video generation** | PPQ.AI `kling-3.0` (async, 5s MP4) |
| **Serving** | Static files via Caddy, Gitea for git hosting |
| **VPS OS** | Debian 13 (Trixie) |

---

## File Structure

```
astro-static/
├── README.md                          # This file
├── agents/astro-static/               # OpenCode agent definitions
│   ├── orchestrator.md                # Master pipeline coordinator
│   ├── researcher.md                  # Brand research & creative brief
│   ├── design-extractor.md            # CSS + vision design extraction
│   ├── asset-generator.md             # Visual identity + content assets
│   ├── frontend-builder.md            # Astro 5 site builder
│   ├── img-gen.md                     # PPQ image API worker
│   ├── vid-gen.md                     # PPQ video API worker
│   ├── auditor.md                     # Read-only quality auditor
│   ├── references/                    # Shared knowledge files
│   │   ├── reference-stack.md         # Canonical Tailwind v4 + Astro 5 syntax
│   │   ├── impeccable-tokens.md       # Font selection, oklch palette rules
│   │   └── impeccable-ui.md           # Spatial design, motion, interaction
│   └── schemas/                       # JSON schema files
│       ├── 00-brief.schema.json
│       ├── 01-creative-brief.schema.json
│       ├── 02-asset-manifest.schema.json
│       └── ... (10 schemas total)
├── scripts/                           # Standalone utilities
│   ├── validate-pipeline.py           # Multi-phase pipeline validator
│   ├── setup-vps.sh                   # Idempotent Debian 13 bootstrap
│   ├── bg-bootstrap.sh                # Background bootstrap launcher
│   ├── test_regressions.py            # Regression tests
│   └── phases/                        # Deterministic helpers
│       ├── bootstrap-join.sh
│       ├── push-gitea.sh
│       ├── smoke.sh
│       ├── asset-fallbacks.sh
│       ├── gen-lqip.py
│       └── retry.sh
└── commands/                          # OpenCode custom slash commands
    ├── new-site.md
    ├── edit-site.md
    └── add-domain.md
```

---

## Installation

### Prerequisites

- **OpenCode** installed and configured
- A **Debian 13 VPS** (fresh or existing) reachable via SSH with key authentication
- **PPQ.AI API key** set as `PPQ_API_KEY` environment variable
- **Python 3.12+** with `jsonschema` and `Pillow` libraries
- **jq** for JSON processing in bash scripts

### Agent Installation

```bash
# Global agents (available in all projects)
cp agents/astro-static/*.md ~/.config/opencode/agents/astro-static/
cp agents/astro-static/references/*.md ~/.config/opencode/agents/astro-static/references/
cp agents/astro-static/schemas/*.json ~/.config/opencode/agents/astro-static/schemas/

# Scripts
cp scripts/*.sh scripts/*.py ~/.config/opencode/astro-static/
cp scripts/phases/* ~/.config/opencode/astro-static/phases/
chmod +x ~/.config/opencode/astro-static/phases/*.sh
chmod +x ~/.config/opencode/astro-static/*.sh

# Commands
cp commands/*.md ~/.config/opencode/commands/astro-static/
```

### Python Dependencies

```bash
pip install jsonschema Pillow
# Optional: for SVG logo conversion
pip install cairosvg
# or: apt install librsvg2-bin
```

---

## Usage

### Starting a New Site

```
/new-site I need a website for a boutique coffee roaster in Portland.
They want a moody, atmospheric brand.
```

The orchestrator asks for missing details group by group: VPS connection, project identity, brief seed, reference URLs.

### Editing an Existing Site

```
/edit-site Change the hero section to be full-screen video instead of static image.
```

### Attaching a Domain

```
/add-domain Set the domain to example.com for my coffee site.
```

### Resuming a Halted Pipeline

Re-run the orchestrator — it reads `pipeline/00-pipeline-state.json` and resumes from the first incomplete phase.

### Audit Mode (Read-Only)

```
@astro-static/auditor Check the pipeline state for my-coffee-site.
```

---

## Pipeline Artifacts

| Artifact | Phase | Producer | Consumer |
|----------|-------|----------|----------|
| `00-brief.json` | Startup | Human + orchestrator | researcher, asset-generator, frontend-builder |
| `vps-connection.json` | Startup | Human + orchestrator | all phases, frontend-builder, deploy |
| `00-pipeline-state.json` | All | orchestrator | orchestrator (resume), auditor |
| `00-design-tokens/` | 1 | design-extractor | researcher, asset-generator |
| `01-creative-brief.json` | 2 | researcher | asset-generator, frontend-builder |
| `02-font-config.json` | 3 | asset-generator | frontend-builder |
| `02-asset-manifest.json` | 3 | asset-generator | frontend-builder, auditor |
| `02-image-shot-list.json` | 3.5 | orchestrator + asset-generator | asset-generator |
| `02-video-shot-list.json` | 3.6 | orchestrator + asset-generator | asset-generator |
| `STATUS.md` | All | orchestrator | human |
| `HUMAN_REVIEW.md` | 2.5, on failure | orchestrator | human |
| `RESULT.md` | 5 | orchestrator | human |

---

## STATUS Token Grammar

Every failure emits a machine-parseable line:

```
STATUS:<TOKEN>[ <key>=<value> ...][ <free-form detail>]
```

Key tokens: `CONNECT_OK`, `BOOTSTRAP_OK`, `BRIEF_VALIDATION_FAILED`, `CONTENT_IMAGES_OK`, `BUILD_OK`, `SITE_LIVE`, `PUSH_OK`, and many more (see orchestrator.md §STATUS token grammar for the full table).

---

## Motion Engine Support

| Engine | Use Case | Dependency |
|--------|----------|-----------|
| **CSS/SVG** | Default — gradients, inline SVG, pseudo-elements | Built-in |
| **Astro View Transitions** | Page-level route transitions | Built-in |
| **Motion One** | Lightweight Web Animations API effects | `motion` |
| **GSAP + ScrollTrigger** | Pinned scroll, scrubbed timelines, horizontal scroll | `gsap` |
| **Lottie** | After Effects animation assets | `lottie-web` |
| **Three.js** | Premium immersive 3D backgrounds | `three` |
| **Lenis** | Smooth scrolling | `@studio-freight/lenis` |

All engines are **dependency-gated**, **reduced-motion guarded**, and **mobile-safe**.

---

## Design Quality Guarantees

- **WCAG AA contrast** (≥4.5:1 text/background, ≥3:1 muted/background)
- **No generic font defaults** (Inter, Roboto, Montserrat are banned)
- **oklch() color format** — perceptually uniform, accessible
- **4pt spacing system** — all layout uses 4pt multiples
- **Squint test** — visual hierarchy clear even when blurred
- **8 interactive states** — default, hover, focus, active, disabled, loading, error, success
- **≥44px touch targets** — mobile accessibility
- **prefers-reduced-motion** — every animation has a fallback
- **Semantic HTML** — `<header>`, `<main>`, `<nav>`, `<section>`, `<article>`

---

## Security

- **Secrets**: `vps-connection.json` contains credentials. Never commit to public repos.
- **SSH**: Key-based auth only. Gitea passwords are auto-generated per-project.
- **Permissions**: All agents use least-privilege. Auditor is read-only.
- **API keys**: `PPQ_API_KEY` from environment only, never in artifacts.
- **No external services**: Gitea + Caddy self-hosted on VPS.
- **Git safety**: Force-push disabled. `pull --rebase` before push.

---

## Cost Estimates

| Component | Cost |
|-----------|------|
| VPS (Debian 13, 1 vCPU, 1 GB RAM) | ~$5-7/month |
| PPQ.AI images (nano-banana-pro) | ~$0.01-0.05 each |
| PPQ.AI video (kling-3.0, 5s) | ~$1.29 each |
| Domain (optional) | ~$10-15/year |

---

## License

Internal tooling — not for redistribution.
