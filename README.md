# astro-static

A multi-agent pipeline that produces complete, deployable Astro 5 static websites from a client brief. Runs inside [OpenCode](https://opencode.ai) using specialist subagents orchestrated by a primary pipeline controller.

> **Private repo** — internal tooling for the astro-static site generation workflow.

---

## What It Does

Given a client intake brief (business name, goals, reference sites, page requirements), the pipeline:

1. **Bootstraps** a fresh Debian 13 VPS with Gitea, Caddy, Node.js, and Bun
2. **Extracts design tokens** from reference sites (colors, typography, spacing, motion signals)
3. **Researches** the client and competitive landscape to produce a creative brief
4. **Generates visual identity assets** — logo, favicons, OG image, theme CSS, font pairing
5. **Generates content images** — hero backgrounds, gallery photos, team portraits, section backgrounds
6. **Generates video backgrounds** (optional) — short cinematic loops via Kling 3.0
7. **Builds the frontend** — complete Astro 5 project with Tailwind v4, shadcn/ui, Content Collections
8. **Deploys** via Gitea push → Caddy static serving with auto-TLS

The entire flow is resume-safe: if any phase fails or the session restarts, the orchestrator reads the pipeline state file and picks up where it left off.

---

## Repository Structure

```
astro-static/
├── agents/astro-static/          # OpenCode agent configurations
│   ├── orchestrator.md           # Primary agent — coordinates the full pipeline
│   ├── researcher.md             # Brand research + creative brief production
│   ├── design-extractor.md       # Extracts design tokens from reference URLs
│   ├── asset-generator.md        # Generates visual identity + content images
│   ├── frontend-builder.md       # Writes Astro 5 code, syncs to VPS, builds
│   ├── img-gen.md                # Image generation via PPQ.AI (nano-banana-pro)
│   ├── vid-gen.md                # Video generation via PPQ.AI (kling-3.0)
│   ├── auditor.md                # Read-only pipeline health checker
│   ├── schemas/                  # JSON Schemas for pipeline artifacts
│   │   ├── 00-brief.schema.json
│   │   ├── 00-design-tokens.schema.json
│   │   ├── 00-pipeline-state.schema.json
│   │   ├── 01-creative-brief.schema.json
│   │   ├── 02-asset-manifest.schema.json
│   │   ├── 02-font-config.schema.json
│   │   ├── 02-image-shot-list.schema.json
│   │   ├── 02-video-shot-list.schema.json
│   │   ├── bootstrap-result.schema.json
│   │   └── vps-connection.schema.json
│   └── references/               # Shared design/tech reference docs
│       ├── reference-stack.md    # Astro 5 + Tailwind v4 API reference
│       ├── impeccable-ui.md      # UI design rules (spacing, motion, interaction)
│       └── impeccable-tokens.md  # Font/color selection methodology
│
└── scripts/                      # Deterministic shell/Python scripts
    ├── setup-vps.sh              # Idempotent VPS bootstrap (Debian 13)
    ├── validate-pipeline.py      # Multi-phase artifact validation
    ├── bg-bootstrap.sh           # Background VPS bootstrap launcher
    └── phases/
        ├── retry.sh              # Retry-dedupe helpers
        ├── bootstrap-join.sh     # Blocking wait for background bootstrap
        ├── smoke.sh              # Post-build functional checks on dist/
        ├── push-gitea.sh         # Commit + push to Gitea with stall detection
        ├── asset-fallbacks.sh    # Deterministic SVG placeholder fallbacks
        └── gen-lqip.py           # Generates base64 WebP LQIP placeholders
```

---

## Agent Roles

### orchestrator (primary)

The pipeline controller. Dispatches specialist subagents phase-by-phase, manages pipeline state (`pipeline/00-pipeline-state.json`), writes `STATUS.md`, halts for human review on ambiguous briefs, and handles retry logic with deduplication.

**Model:** `zai-coding-plan/glm-5.1` — high-reasoning for orchestration decisions.
**Steps:** 200 — the full pipeline is long-running.

### researcher (subagent)

Deep research into the client's business, competitors, and industry. Produces `pipeline/01-creative-brief.json` with brand personality, color/typography direction, content structure, and a formal content model. Verifies all proper nouns against authoritative sources and flags unverified claims for human review.

**Model:** `deepseek/deepseek-v4-pro`
**Tools:** web search, web fetch, search agents (deepeye, proxy, scrapling, crawlee, instagram)

### design-extractor (subagent)

Fetches reference websites, extracts design tokens (colors, typography, spacing, shadows, motion signals) using both CSS parsing and visual screenshot analysis. Outputs W3C DTCG tokens, Tailwind v4 theme CSS, section pattern YAMLs, and an extraction report with confidence scores.

**Model:** `ppq/moonshotai/kimi-k2.6` — multimodal for visual analysis.
**Tools:** search agents, web fetch

### asset-generator (subagent)

Produces the visual identity: color palette, font pairing, theme CSS, logo (via img-gen), favicons, OG image. Also handles content-image generation (Phase 3.5) and video-background generation (Phase 3.6) by delegating to img-gen and vid-gen respectively.

**Model:** `deepseek/deepseek-v4-pro`
**Tools:** img-gen, vid-gen subagents, bash for Pillow-based processing

### frontend-builder (subagent)

Writes the complete Astro 5 project: pages, components, layouts, Content Collections, theme integration, LQIP image rendering, video background components, optional GSAP/ScrollTrigger sections. Syncs to VPS via rsync, runs `bun install && bun run check && bun run build` remotely.

**Model:** `deepseek/deepseek-v4-pro`
**Tools:** edit, bash (rsync, ssh), glob, grep, Astro docs MCP

### img-gen (subagent, hidden)

Calls PPQ.AI `nano-banana-pro` for image generation. Handles API calls, download, size verification, and retry logic. Always uses the same model — no model switching.

**Model:** `deepseek/deepseek-v4-flash`
**API:** `POST https://api.ppq.ai/v1/images/generations`

### vid-gen (subagent, hidden)

Calls PPQ.AI `kling-3.0` for video generation. Handles async submit → poll → download cycle. 5s MP4 clips at 16:9 by default (~$1.29 per clip).

**Model:** `deepseek/deepseek-v4-flash`
**API:** `POST https://api.ppq.ai/v1/videos`

### auditor (subagent, read-only)

Inspects pipeline state and artifacts without writing anything. Reports missing/malformed files, contract drift, human-review blockers, and recommends the next safe action. Called by the orchestrator before retrying after unclear failures.

**Model:** `deepseek/deepseek-v4-pro`
**Permissions:** read-only — no edit, no bash (except read-only git/jq/validate commands), no subagents.

---

## Pipeline Phases

| Phase | Name | Agent | VPS? | Output |
|-------|------|-------|------|--------|
| 0 | VPS Bootstrap | orchestrator + `setup-vps.sh` | Yes | Gitea, Caddy, Node, Bun on VPS |
| 1 | Design Extraction | design-extractor | No | `pipeline/00-design-tokens/` |
| 2 | Research | researcher | No | `pipeline/01-creative-brief.json` |
| 2.5 | Brief Validation | orchestrator | No | Human review gate (halts if issues) |
| 3 | Asset Generation | asset-generator | No | Theme CSS, logo, favicons, OG image, font config |
| 3.5 | Content Images | asset-generator → img-gen | No | Hero backgrounds, gallery, portraits, LQIPs |
| 3.6 | Video Backgrounds | asset-generator → vid-gen | No | MP4 clips for hero/section backgrounds |
| — | Bootstrap Join | orchestrator + `bootstrap-join.sh` | Yes | Validates VPS, merges connection details |
| 4 | Frontend Build | frontend-builder | Yes | Complete Astro project, built on VPS |
| 5 | Deploy | orchestrator + `push-gitea.sh` | Yes | Live site via Caddy |

Phases 0 and 1–3.6 run concurrently — VPS bootstrap happens in the background while local-only phases (design extraction, research, asset generation) proceed. The Bootstrap Join blocks before Phase 4 when the VPS is actually needed.

---

## Pipeline Artifacts

All artifacts live in the project's `pipeline/` directory:

```
pipeline/
├── 00-brief.json                 # Intake brief (user-provided)
├── 00-pipeline-state.json        # Phase status tracking
├── 00-design-tokens/             # Extracted reference-site tokens
│   ├── tokens.json               # W3C DTCG format
│   ├── tailwind/theme.css        # @theme {} block
│   └── patterns/                 # Section + motion YAMLs
├── 01-creative-brief.json        # Strategy + content model
├── 02-font-config.json           # Heading + body font config
├── 02-asset-manifest.json        # All generated assets + content images + videos
├── 02-image-shot-list.json       # Content image generation tasks
├── 02-video-shot-list.json       # Video background generation tasks
├── vps-connection.json           # SSH + deploy credentials (sensitive)
├── HUMAN_REVIEW.md               # Generated when pipeline halts for review
├── STATUS.md                     # Human-readable pipeline status
├── RESULT.md                     # Final deployment summary
├── bootstrap.pid                 # Background bootstrap process tracking
├── bootstrap.log                 # Bootstrap output log
└── retry.log                     # Retry-deduplication log
```

Every artifact has a corresponding JSON Schema in `agents/astro-static/schemas/`. The `validate-pipeline.py` script checks artifacts at each phase gate.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend framework | Astro 5 (static output) |
| CSS framework | Tailwind v4 (CSS-first `@theme {}`) |
| UI components | shadcn/ui (React islands with `client:*` directives) |
| Content | Astro Content Collections (file-backed, Zod schemas) |
| Image optimization | Sharp (WebP/AVIF at build), Astro `<Image>` component |
| LQIP | Base64 WebP placeholders (24px blurred previews) |
| Video backgrounds | Native `<video autoplay muted loop playsinline>` — no player libraries |
| Optional motion | CSS/SVG (default), Motion One, GSAP + ScrollTrigger (explicit opt-in), Lottie, Three.js |
| VPS | Debian 13, Gitea (git hosting), Caddy (static serving + auto TLS) |
| Runtime | Bun (install, check, build) |
| Image generation | PPQ.AI `nano-banana-pro` |
| Video generation | PPQ.AI `kling-3.0` |
| Design token format | W3C DTCG JSON + oklch() colors |

---

## Key Design Decisions

### Status token grammar

Every failure path emits `STATUS:<UPPER_SNAKE_CASE> [key=value ...]` — a machine-parseable format that downstream tooling keys on. Tokens are enumerated in the orchestrator agent and never renamed.

### Retry deduplication

`phases/retry.sh` tracks error signatures (phase + SHA256 of status line) and halts after seeing the same error twice — prevents a stuck subagent from burning through the retry budget.

### Human-in-the-loop at Phase 2.5

Before any expensive asset generation, the orchestrator cross-checks the creative brief against the original intake. If the researcher flagged unverified names, contradictory requirements, or ambiguous references, the pipeline halts and writes `HUMAN_REVIEW.md` with specific issues and options.

### Deterministic fallbacks

If image or video generation fails, `phases/asset-fallbacks.sh` writes valid SVG placeholder assets and marks them in the manifest — never 0-byte files, never broken builds.

### Website-agnostic

The orchestrator never infers business type, owner, site purpose, or reference domain from prior runs. Each pipeline starts fresh from the current brief.

---

## Requirements

- **OpenCode** with the astro-static agents installed under `~/.config/opencode/agents/astro-static/`
- **PPQ.AI API key** (`PPQ_API_KEY` env var) for image/video generation
- **VPS** running Debian 13 (Trixie) with SSH access
- **Python 3.10+** with Pillow for local image processing
- **Bun** on the VPS (installed by `setup-vps.sh`)

---

## Quick Start

1. Install the agent configs: copy `agents/astro-static/` to `~/.config/opencode/agents/astro-static/`
2. Install the scripts: copy `scripts/` to `~/.config/opencode/astro-static/`
3. Set `PPQ_API_KEY` in your environment
4. Create a project directory under `/Users/djesys/SITES/<project-name>/`
5. Write `pipeline/00-brief.json` with your intake brief
6. Run OpenCode and select the `astro-static/orchestrator` agent
7. Provide the VPS connection details when prompted

The orchestrator handles everything from there — bootstrap through deploy.

---

## License

Internal tooling — not for redistribution.
