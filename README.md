# astro-static — Multi-Agent Static Site Pipeline for OpenCode

> **Multi-agent pipeline for OpenCode that researches brands, extracts design DNA from reference sites, generates visual assets via AI, builds Astro 6 + Tailwind v4 static sites with self-hosted TinaCMS visual editing, and deploys to a Debian 13 VPS — all orchestrated by a single agent.**

## Overview

`astro-static` is an **agentic site generation pipeline** built on the [OpenCode](https://github.com/opencode-ai/opencode) platform. It defines **1 primary orchestrator plus 10 specialized AI subagents** that together take a site from a human-written brief to a live, deployed Astro 6 website with **self-hosted TinaCMS visual editing**.

The pipeline is **phase-gated with human-in-the-loop checkpoints**, **contract-validated at every stage**, and **idempotent at every level** — you can interrupt and resume safely.

### What It Does

1. **Bootstraps a fresh Debian 13 VPS** with Node.js, Bun, Gitea (git server), Caddy (reverse proxy + auto-TLS), TinaCMS SSR service (systemd), and a git-sync watcher for continuous deployment from content changes.
2. **Extracts design tokens** from reference/competitor websites — W3C DTCG JSON, Tailwind v4 `@theme` blocks, CSS/SVG section patterns, and motion signals — using both CSS parsing and computer vision (via kimi-k2.6 multimodal model).
3. **Researches the client business** — brand strategy, competitive landscape, industry trends — and produces a structured creative brief with verified facts, content model definitions, and explicit review flags when source data contradicts the human-provided brief.
4. **Generates visual identity assets** — color palettes (oklch), Google Font pairings, logos, favicon sets, OG images, Tailwind v4 theme CSS — via PPQ.AI `nano-banana-pro` image generation.
5. **Generates content images and optional video backgrounds** — hero images, gallery photos, member portraits, atmospheric looping video backgrounds (via PPQ.AI `kling-3.0`) — with LQIP (Low-Quality Image Placeholder) generation for perceived performance.
6. **Generates a complete Astro 6 site locally** with Tailwind v4 CSS-first theming, Astro Content Collections, shadcn/ui interactive islands, optional motion engines (GSAP ScrollTrigger, Motion One, Lottie, Three.js), and **TinaCMS self-hosted visual editing** — every text node, `<img>`, media path, and background image is admin-editable via click-to-edit `data-tina-field` markers.
7. **Builds and deploys through a dedicated deployer** — joins bootstrap, rsyncs non-secret artifacts, runs `/usr/local/bin/site-build` on the VPS, smoke-tests the built output, pushes to Gitea, and verifies the live site. TinaCMS SSR service auto-restarts on deploy.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                 CONTROL NODE (your machine)          │
│                                                     │
│  ┌──────────────┐    dispatches subagents           │
│  │ Orchestrator │────────────────────┐              │
│  │ (glm-5.2)    │                    │              │
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
│         │  3.8 Hero video ▶│ hyperframes      │     │
│         │  4.1 Codegen ───▶│ frontend-builder │     │
│         │  4.2 Tina local   │ tinacms script   │     │
│         │  4.3 Build deploy▶│ build-deployer   │     │
│         │  Audit/readiness ▶│ auditor          │     │
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
│  └─────────┘  │         │  │   ├── dist/client/ │   │
│               │ /tina*  │  │   ├── dist/server/ │   │
│  git-sync    │ reverse │  │   └── pipeline/    │   │
│  watcher     │ proxy   │  └───────────────────┘   │
│              └─────────┘                           │
│  astro-ssr-<project> (systemd)                     │
│  TinaCMS SSR + GraphQL                             │
└─────────────────────────────────────────────────────┘
```

### Key Design Decisions

- **Control node / VPS separation**: All AI work (research, asset generation, code writing, Tina admin SPA build) happens locally on the control node. Only non-secret build/runtime artifacts are synced to the VPS via rsync over SSH.
- **Non-blocking bootstrap**: VPS setup runs in the background concurrently with Phases 1–4.2, joining only before Phase 4.3 (Build Deploy). This parallelizes ~3–5 minutes of server setup with pure-local work.
- **Phase gate with human-in-the-loop**: Phase 2.5 (Brief Validation) explicitly checks for unverifiable proper nouns, contradictory requirements, and ambiguous references. The pipeline halts until a human resolves flagged issues — preventing wasted downstream asset generation.
- **Contract-driven architecture**: Every phase produces and validates JSON artifacts against JSON schemas. `validate-pipeline.py` runs at startup and phase transitions with **36 regression tests** to catch drift, missing files, schema violations, insecure permissions, unsafe paths, and TinaCMS editability regressions early.
- **TinaCMS self-hosted visual editing**: Every generated site includes a `/admin` visual editor backed by Gitea + SQLite. The pipeline enforces maximum editability: all text nodes must have `data-tina-field`, all `<img>` elements must be Tina-backed or marked `data-static-media`, all media paths must come from Tina/content manifests, and service bullets must live in Tina-backed content — not hardcoded arrays.

## TinaCMS Visual Editing (Self-Hosted)

Every astro-static site includes a fully self-hosted TinaCMS admin at `/admin` with **no TinaCloud dependency** — no `app.tina.io` sign-in, no cloud auth. The pipeline enforces this at build time.

### Architecture

```
Editor browser ──→ /admin/index.html (SPA)
                 → /tina-island/* (SSR visual preview — astro-ssr-<project>)
                 → /api/tina/gql (self-hosted GraphQL — astro-ssr-<project>)
                     │
                     ▼
              TinaCMS datalayer → SQLite (local) → Gitea (git backend)
```

### Enforced Guardrails (36 regression tests)

The pipeline validator rejects sites with:

| Violation | Check |
|-----------|-------|
| `<img>` without `data-tina-field` or `data-static-media` | Every visible image must be admin-editable |
| `contentImages[...]` without Tina image override prop | Background images must accept Tina upload overrides |
| Hardcoded `/images/` or `/videos/` paths | Media paths must be Tina/content/manifest-backed |
| `data-typewriter` text without `data-tina-field` | Click-to-edit markers required on all visible text |
| Hardcoded visible copy in markup | Marketing text must be Tina-backed |
| Hardcoded service bullet arrays | Bullet lists must live in Tina-backed content |
| Tina config without custom `PasswordAuthProvider` | Admin SPA must use password-gated self-hosted auth |
| Tina config without `ui.router` | Collections must map to visual editor routes |
| Data loaders without `requestWithMetadata()` | Visual preview forms require metadata |
| Missing `tina/config.ts`, island route, or API route | All TinaCMS files must be present |

### Canonical Image Pattern: "Tina Override with Asset-Gen Fallback"

```astro
---
import { contentImages } from '@/lib/content-images';
const { bgImage, fields = {} } = Astro.props;
const fallback = contentImages['hero-background'];
const src = bgImage ?? fallback?.src.src;  // Tina upload wins, asset-gen fallback
---
<section>
  {src && (
    <div data-tina-field={fields.bgImage}>
      <img src={src} alt="" data-tina-field={fields.bgImage} />
    </div>
  )}
</section>
```

Editors get a media picker in the Tina admin. If they never upload a replacement, the pipeline-generated default renders.

## Agent Team

| Agent | Model | Role | Mode |
|-------|-------|------|------|
| **orchestrator** | `ppq/z-ai/glm-5.2` | Master coordinator — dispatches subagents, runs phase scripts, validates artifacts, updates state | `primary` |
| **researcher** | `deepseek/deepseek-v4-pro` | Brand strategist — deep research, competitive analysis, creative brief authoring | `subagent` |
| **design-extractor** | `ppq/moonshotai/kimi-k2.6` | Design token extractor — CSS + vision-based extraction from reference sites, outputs W3C DTCG JSON + Tailwind theme | `subagent` |
| **asset-generator** | `deepseek/deepseek-v4-pro` | Visual identity producer — color palettes (oklch), font pairings, logos, favicons, theme CSS, content images, video backgrounds | `subagent` |
| **frontend-builder** | `deepseek/deepseek-v4-pro` | Astro 6 developer — local codegen only for page/component code, Content Collections, TinaCMS wiring, responsive layouts, optional motion engines | `subagent` |
| **build-deployer** | `deepseek/deepseek-v4-pro` | Operational deployer — joins bootstrap, rsyncs artifacts, runs remote `site-build`, smoke-tests, final-validates | `subagent` |
| **img-gen** | `deepseek/deepseek-v4-flash` | Image API worker — calls PPQ.AI `nano-banana-pro`, downloads and validates images | `subagent` |
| **vid-gen** | `deepseek/deepseek-v4-flash` | Video API worker — submits to PPQ.AI `kling-3.0`, polls async, downloads and validates MP4 videos | `subagent` |
| **hyperframes-vid-gen** | `deepseek/deepseek-v4-pro` | Optional zero-cost hero intro renderer — local HyperFrames/Chrome/FFmpeg MP4 generation | `subagent` |
| **instagram-extractor** | `deepseek/deepseek-v4-pro` | Optional Instagram brand/design extractor for profiles, posts, reels, and visual signals | `subagent` |
| **auditor** | `deepseek/deepseek-v4-pro` | Read-only quality inspector — audits pipeline state, artifact contracts, TinaCMS editability, permissions, and recommends next action | `subagent` |

### Permission Model

All agents use **least-privilege permissions**. Key constraints:
- **orchestrator**: Can SSH/rsync/scp (with `ask` gates), runs phase scripts, dispatches subagents. Denies `rm -rf *`.
- **researcher/design-extractor**: Cannot touch VPS (`ssh: deny`, `scp: deny`, `rsync: deny`). Web research only.
- **asset-generator**: Local-only file creation. Delegates all API calls to `img-gen` and `vid-gen` — never calls PPQ directly.
- **frontend-builder**: Writes code locally only. No SSH, rsync, remote build, or deploy ownership.
- **build-deployer**: Owns SSH/rsync, remote `site-build`, smoke checks, and final validation; never fixes source code.
- **img-gen/vid-gen**: Minimal — only `curl` for PPQ API, `mkdir`, file validation.
- **auditor**: Strictly read-only. `edit: deny`, `task: deny`, `skill: deny`. No write-side effects.

## Pipeline Phases

### Phase 0: VPS Bootstrap (Background, Non-Blocking)
- Probes VPS state for existing setup
- Launches `setup-vps.sh` in background (3–5 min for fresh VPS)
- Now provisions **13 phases** including TinaCMS SSR service (systemd), Caddy reverse proxy for `/tina-island/*` and `/api/tina/*`, `/usr/local/bin/site-build` wrapper, `/usr/local/bin/git-sync-watch` auto-rebuild watcher, and sudoers drop-in for project-scoped SSR restart.
- Scaffolds to latest Astro 6 + TinaCMS baseline
- `.gitignore` explicitly documents `public/media/` as tracked for Tina media uploads
- Phases 1–4.2 proceed in parallel/local mode
- Bootstrap Join (blocking) merges VPS config before Phase 4.3

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
- All generated images are **Tina-editable via override props** — editors can replace them from the admin

### Phase 3.6: Video Background Generation (Optional)
- Conditional on `motion_direction.video_backgrounds: true`
- Generates 5s MP4 loops via `kling-3.0` (~$1.29 each)
- Poster images paired from Phase 3.5 content images
- Reduced-motion fallback via CSS
- Video paths stored in **Tina-editable section fields** (`videoSrc`, `posterPath`)

### Phase 3.8: HyperFrames Hero Intro (Opt-In)
- Optional zero-cost branded MP4 intro rendered locally with HyperFrames (HTML + GSAP + headless Chrome + FFmpeg)
- Only runs when explicitly enabled/requested; recommendation alone does not trigger it
- Writes `public/videos/hero-intro.mp4` and updates the asset manifest

### Phase 4.1: Frontend Codegen (Local-Only)
- Dispatches `frontend-builder` with comprehensive design reasoning framework
- Builds all pages, Content Collections, and components locally
- **Wires TinaCMS visual editing**: every `<img>` gets `data-tina-field`, every component with `contentImages[]` gets a Tina image override prop, every visible text node is click-to-edit
- Generates `tina/config.ts` with custom `PasswordAuthProvider`, `ui.router`, and matching content schemas
- Generates `src/lib/tina/islands.ts` for visual preview islands
- Generates `src/lib/tina/data.ts` with `requestWithMetadata()` wrappers
- Emits `STATUS:FRONTEND_CODEGEN_OK`; does not SSH, rsync, or build remotely
- Supports optional motion engines: GSAP/ScrollTrigger, Motion One, Lottie, Three.js

### Phase 4.2: TinaCMS Admin SPA Local Build
- Runs `tinacms build --local --skip-cloud-checks` on the control node because 2GB VPS builds can OOM
- Verifies `admin/index.html`, `admin/login.html`, `admin/bridge.js`, and `tina/__generated__/_schema.json`
- Emits `STATUS:TINACMS_BUILD_OK`; leaves artifacts local for the deployer

### Phase 4.3: Build Deploy
- Dispatches `build-deployer`
- Joins background bootstrap and fetches `/var/lib/site-pipeline/pipeline-result.json` through an owner-only channel
- Rsyncs non-secret source/admin/schema artifacts to the VPS
- Runs `/usr/local/bin/site-build` remotely (install/check/build/copy Tina bridge/restart SSR)
- Smoke tests built output and runs strict final validation

### Phase 5: Deploy
- Commits locally, pushes to Gitea on VPS
- Verifies live site via HTTP 200
- Writes `RESULT.md` with all URLs, design summary, cost estimates

## Tech Stack (Non-Negotiable)

| Layer | Technology |
|-------|-----------|
| **Site framework** | Astro 6 |
| **CSS framework** | Tailwind v4 (CSS-first, `@theme {}` block, no `tailwind.config.js`) |
| **Component library** | shadcn/ui (React islands) |
| **CMS** | TinaCMS (self-hosted, Gitea + SQLite backend, custom PasswordAuthProvider, no TinaCloud) |
| **Content** | Astro Content Collections with Zod schemas, file-backed MDX + JSON |
| **SSR adapter** | `@astrojs/node` (standalone mode for /tina-island/* and /api/tina/* routes) |
| **Images** | Sharp for WebP/AVIF at build, Pillow for pre-processing, pngquant/jpegoptim |
| **LQIP** | 24px base64 WebP CSS backgrounds, ~300-500 bytes per image |
| **Build tool** | Bun (3-5× faster than npm) |
| **Version control** | Gitea on VPS (self-hosted git) |
| **Reverse proxy** | Caddy (auto-TLS, multi-domain, `/tina-island/*` and `/api/tina/*` reverse proxy to SSR) |
| **Deployment** | git-sync watcher (auto-rebuild on push, auto-restart SSR) |
| **Image generation** | PPQ.AI `nano-banana-pro` (4K raster PNG) |
| **Video generation** | PPQ.AI `kling-3.0` (async, 5s MP4) |
| **Serving** | Static files via Caddy + TinaCMS SSR via Node adapter + Gitea for git hosting |
| **VPS OS** | Debian 13 (Trixie) |

## File Structure

```
astro-static/
├── README.md                          # This file
├── agents/astro-static/               # OpenCode agent definitions
│   ├── orchestrator.md                # Master pipeline coordinator
│   ├── researcher.md                  # Brand research & creative brief
│   ├── design-extractor.md            # CSS + vision design extraction
│   ├── asset-generator.md             # Visual identity + content assets
│   ├── frontend-builder.md            # Astro 6 + TinaCMS local codegen
│   ├── build-deployer.md              # Bootstrap join, rsync, remote build, smoke, final validation
│   ├── hyperframes-vid-gen.md         # Optional local hero intro MP4 renderer
│   ├── instagram-extractor.md         # Optional Instagram brand/design extraction
│   ├── img-gen.md                     # PPQ image API worker
│   ├── vid-gen.md                     # PPQ video API worker
│   ├── auditor.md                     # Read-only quality auditor
│   ├── references/                    # Shared knowledge files
│   │   ├── pipeline-contract.md       # Canonical phase graph + STATUS grammar
│   │   ├── reference-stack.md         # Canonical Tailwind v4 + Astro 6 + TinaCMS patterns
│   │   ├── impeccable-tokens.md       # Font selection, oklch palette rules
│   │   └── impeccable-ui.md           # Spatial design, motion, interaction
│   └── schemas/                       # JSON schema files
│       ├── 00-brief.schema.json
│       ├── 01-creative-brief.schema.json
│       ├── 02-asset-manifest.schema.json
│       └── ... (11 schemas total)
├── scripts/                           # Standalone utilities
│   ├── validate-pipeline.py           # Multi-phase pipeline validator (36 guardrails)
│   ├── setup-vps.sh                   # Idempotent Debian 13 bootstrap (13 phases)
│   ├── bg-bootstrap.sh                # Background bootstrap launcher
│   ├── test_regressions.py            # Regression tests (36 tests)
│   └── phases/                        # Deterministic helpers
│       ├── bootstrap-join.sh
│       ├── hyperframes-probe.sh
│       ├── ig-download.sh
│       ├── push-gitea.sh
│       ├── smoke.sh
│       ├── tinacms-local-build.sh
│       ├── asset-fallbacks.sh
│       ├── gen-lqip.py
│       └── retry.sh
└── commands/                          # OpenCode custom slash commands
    ├── new-site.md
    ├── edit-site.md
    └── add-domain.md
```

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

## Pipeline Artifacts

| Artifact | Phase | Producer | Consumer |
|----------|-------|----------|----------|
| `00-brief.json` | Startup | Human + orchestrator | researcher, asset-generator, frontend-builder |
| `vps-connection.json` | Startup | Human + orchestrator | bootstrap join, build-deployer, Gitea publish |
| `00-pipeline-state.json` | All | orchestrator | orchestrator (resume), auditor |
| `pipeline-contract.md` | Static reference | repo | orchestrator, validators, agents |
| `00-design-tokens/` | 1 | design-extractor | researcher, asset-generator |
| `01-creative-brief.json` | 2 | researcher | asset-generator, frontend-builder |
| `02-font-config.json` | 3 | asset-generator | frontend-builder |
| `02-asset-manifest.json` | 3 | asset-generator | frontend-builder, build-deployer, auditor |
| `02-image-shot-list.json` | 3.5 | orchestrator + asset-generator | asset-generator |
| `02-video-shot-list.json` | 3.6 | orchestrator + asset-generator | asset-generator |
| `admin/` | 4.2 | tinacms-local-build | build-deployer, Caddy |
| `tina/__generated__/_schema.json` | 4.2 | tinacms-local-build | build-deployer, Tina admin |
| `STATUS.md` | All | orchestrator | human |
| `HUMAN_REVIEW.md` | 2.5, on failure | orchestrator | human |
| `RESULT.md` | 5 | orchestrator | human |

## STATUS Token Grammar

Every failure emits a machine-parseable line:

```
STATUS:<TOKEN>[ <key>=<value> ...][ <free-form detail>]
```

Key tokens: `CONNECT_OK`, `BOOTSTRAP_OK`, `BRIEF_VALIDATION_FAILED`, `FRONTEND_CODEGEN_OK`, `TINACMS_BUILD_OK`, `BUILD_DEPLOY_OK`, `SITE_LIVE`, `PUSH_OK`, and many more (see orchestrator.md).

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
- **TinaCMS editability** — every visible text, `<img>`, media path, and background image is admin-editable. The pipeline validator enforces this with 36 regression tests.

## Security

- **Secrets**: `vps-connection.json` contains credentials. Never commit to public repos.
- **SSH**: Key-based auth only. Gitea passwords are auto-generated per-project.
- **Permissions**: All agents use least-privilege. Auditor is read-only.
- **API keys**: `PPQ_API_KEY` from environment only, never in artifacts.
- **No external services**: Gitea + Caddy + TinaCMS (self-hosted) on VPS.
- **TinaCMS auth**: custom `PasswordAuthProvider` plus backend session cookie gate — never TinaCloud or `LocalAuthProvider` fallback. Tina/admin secrets are generated server-side and never printed.
- **Git safety**: Force-push disabled. `pull --rebase` before push.

## Cost Estimates

| Component | Cost |
|-----------|------|
| VPS (Debian 13, 1 vCPU, 2 GB RAM recommended) | ~$5-10/month |
| PPQ.AI images (nano-banana-pro) | ~$0.01-0.05 each |
| PPQ.AI video (kling-3.0, 5s) | ~$1.29 each |
| Domain (optional) | ~$10-15/year |

## License

Internal tooling — not for redistribution.
