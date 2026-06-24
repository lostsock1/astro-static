# astro-static — Tina-first Astro 7 site pipeline for OpenCode

> Multi-agent OpenCode pipeline that researches a brand, extracts design DNA, generates visual assets, builds an Astro 7 + Tailwind v4 site with self-hosted TinaCMS visual editing, and deploys it to a Debian VPS with contract validation at every phase.

## Overview

`astro-static` is an agentic website delivery stack for OpenCode. It uses one primary orchestrator plus specialized subagents to move from a short human brief to a live Astro 7 website with:

- deterministic TinaCMS content modeling before assets or codegen
- editable text, images, backgrounds, navigation, footer, and repeated blocks
- local AI generation for brand/design/content/assets
- local Astro/Tina source generation and admin build
- VPS bootstrap, rsync deploy, SSR restart, and smoke validation

The pipeline is phase-gated, resumable, and fail-closed. Each major phase emits JSON artifacts under `pipeline/`, and `validate-pipeline.py` enforces schemas, state transitions, security invariants, package baselines, and Tina visual-editing coverage.

## Current stack baseline

| Layer | Baseline |
|---|---|
| Site framework | Astro 7 |
| Styling | Tailwind v4 CSS-first theme tokens |
| CMS/editor | Self-hosted TinaCMS with visual editing |
| Runtime | Astro SSR via `@astrojs/node` for Tina routes |
| Content | Astro Content Collections + Tina collections |
| Deployment target | Debian 13 VPS, Caddy, Gitea, systemd SSR service |
| Media generation | PPQ image/video agents with local fallback manifests |
| Validation | 103 regression tests plus phase/schema checks |

Canonical package ranges are documented in `agents/astro-static/references/reference-stack.md`.

## Tina-first architecture

The central contract is `pipeline/01-tina-blueprint.json`. It is generated after the creative brief and before assets/codegen, then drives:

1. Tina collections and templates
2. Astro content schemas and seed content
3. reusable block renderer selection
4. image/video field references for asset generation
5. visual-editing islands and `data-tina-field` markers
6. `pipeline/03-tina-coverage.json`, proving every editable field is wired

This prevents the common failure mode where a generated page looks correct but has hardcoded copy, static media paths, or invisible Tina fields.

### Required Tina artifacts

| Artifact | Purpose |
|---|---|
| `pipeline/01-tina-blueprint.json` | Canonical editable-surface model |
| `pipeline/02-image-shot-list.json` | Image generation plan with `field_ref` mappings |
| `pipeline/02-video-shot-list.json` | Optional video generation plan with `field_ref` mappings |
| `pipeline/02-asset-manifest.json` | Generated assets, defaults, and Tina media metadata |
| `pipeline/03-tina-coverage.json` | Schema/content/renderer/island/marker proof for every field |

## Pipeline phases

Canonical phase IDs are stable and should not be renamed without updating schemas, validator logic, tests, and docs together.

1. `0_bootstrap_launch` — starts VPS setup in the background
2. `1_design_extraction` — extracts reference-site tokens and section patterns when URLs exist
3. `2_research` — produces the creative brief and content strategy
4. `2_5_brief_validation` — human review gate for contradictions or unverifiable claims
5. `2_6_tina_blueprint` — deterministic Tina editable-surface blueprint generation
6. `3_asset_generation` — identity assets, theme CSS, font config, and manifest updates
7. `3_5_image_generation` — field-ref-aware content images and LQIP placeholders
8. `3_6_video_generation` — optional Tina-editable video backgrounds
9. `3_8_hyperframes_hero_optional` — optional local branded intro video
10. `4_1_frontend_codegen` — local Astro 7/Tailwind/Tina source generation
11. `4_2_tinacms_local_build` — local Tina admin SPA build
12. `4_3_build_deploy` — bootstrap join, rsync, remote build, SSR restart, smoke checks
13. `5_publish_result` — final validation and operator handoff

## Agent team

| Agent | Role | Mode |
|---|---|---|
| `orchestrator.md` | Primary coordinator, phase state owner, dispatch, validation, final result publication | primary |
| `researcher.md` | Business/brand/content research and creative brief production | subagent |
| `design-extractor.md` | Reference-site token and section-pattern extraction | subagent |
| `asset-generator.md` | Identity assets, theme CSS, content image/video shot-list coordination | subagent |
| `img-gen.md` | PPQ image-generation worker | subagent |
| `vid-gen.md` | PPQ video-generation worker | subagent |
| `hyperframes-vid-gen.md` | Deterministic local hero intro MP4 generator | subagent |
| `instagram-extractor.md` | Instagram profile/content extraction path | subagent |
| `frontend-builder.md` | Local-only Astro/Tailwind/Tina source generator | subagent |
| `build-deployer.md` | VPS deployment, remote build, SSR restart, smoke/final validation | subagent |
| `auditor.md` | Read-only pipeline/state/configuration audit | subagent |

## Repository layout

This repository is the single source of truth. There are no duplicated copies;
`sync.sh` installs each part into its OpenCode location.

```text
.
├── agents/astro-static/             # canonical source for the agent stack
│   ├── *.md                         # orchestrator and subagent definitions
│   ├── schemas/                     # pipeline artifact schemas
│   ├── references/                  # stack, pipeline, and transformation contracts
│   └── scripts/                     # runtime helpers (validators, setup-vps, phases/)
├── commands/astro-static/           # installable OpenCode slash commands
├── models/                          # PPQ model-lookup toolkit (installed; used by img/vid agents)
├── sync.sh                          # install into / diff against the live OpenCode config
└── README.md
```

`sync.sh` maps the source tree onto the OpenCode install locations:

| Repo source | Installs to |
|---|---|
| `agents/astro-static/` (minus `scripts/`) | `~/.config/opencode/agents/astro-static/` |
| `agents/astro-static/scripts/` | `~/.config/opencode/astro-static/` |
| `models/` | `~/.config/opencode/astro-static/models/` |
| `commands/astro-static/` | `~/.config/opencode/commands/astro-static/` |

The runtime helpers are kept inside `agents/astro-static/scripts/` so the
validator and regression suite resolve their schemas the same way whether run
from this repo or from the installed location.

## Validation and guardrails

The validator rejects unsafe or incomplete generated sites, including:

- missing `pipeline/01-tina-blueprint.json` before assets/codegen
- missing settings/nav/footer editable fields
- unsupported or unconfirmed block types
- incomplete `media_fields` or asset `field_ref` mappings
- missing `pipeline/03-tina-coverage.json` after frontend codegen
- visible text without Tina field markers
- image/background/video paths not backed by Tina/content/manifest fields
- hardcoded service bullets or marketing copy arrays
- invalid Tina auth provider return values
- Tina island route exporting `ALL` instead of `POST`
- SSR deploy checks that incorrectly require `dist/client/index.html`
- generated output, logs, env files, or secrets being pushed to Gitea

Run the regression suite:

```bash
python3 agents/astro-static/scripts/test_regressions.py
```

Expected output for this stack revision:

```text
Ran 103 tests
OK
```

Additional syntax checks used before publishing:

```bash
S=agents/astro-static/scripts
python3 -m py_compile $S/validate-pipeline.py $S/test_regressions.py $S/phases/tina-blueprint.py
bash -n $S/setup-vps.sh
bash -n $S/bg-bootstrap.sh
for p in asset-fallbacks bootstrap-join ppq-auth push-gitea retry smoke tinacms-local-build; do
  bash -n "$S/phases/$p.sh"
done
```

## Installation into local OpenCode config

Install or update the live OpenCode stack from this repo with the sync script:

```bash
./sync.sh install     # copy repo -> the three ~/.config/opencode locations
./sync.sh status      # show any drift between repo and live install
./sync.sh pull        # rescue edits made directly under ~/.config/opencode
```

The authoring loop is: edit here → `./sync.sh install` → test in OpenCode →
`git commit` → `git push`. Override the target with `OPENCODE_CONFIG_DIR=...`.

Do not copy pipeline project secrets, VPS connection files, OpenCode auth files, SSH keys, or PPQ credentials into this repository.

## Editing discipline

- Treat schemas, validators, agent prompts, references, and regression tests as one contract.
- When adding a phase or artifact, update `references/pipeline-contract.md`, schemas, validator logic, tests, and README together.
- Edit only under `agents/astro-static/` and `commands/astro-static/`; run `./sync.sh install` to deploy. Never edit the live `~/.config/opencode` copies directly.
- Keep generated project media editable by carrying `field_ref`, `content_path`, and Tina default metadata through the asset pipeline.
- Never print or commit secrets from `pipeline/vps-connection.json`, bootstrap logs, OpenCode auth, SSH keys, or PPQ credentials.
