# astro-static agent stack

This directory contains the OpenCode agent team for the `astro-static` pipeline:
a local-control-node workflow that generates, deploys, and validates Astro 6 / Tailwind v4 / TinaCMS sites on Debian VPS targets.

## Scope

`astro-static` is for full website delivery, not general app development. It owns:

- VPS bootstrap and join handoff
- brand/design research and reference extraction
- identity assets, content images, PPQ videos, and optional HyperFrames hero video
- local Astro/Tailwind/Tina source generation
- local TinaCMS admin SPA build
- remote sync, remote `site-build`, SSR restart, smoke tests, and final validation

Runtime shell helpers and validators live outside this agents repo at:

```text
/Users/djesys/.config/opencode/astro-static/
```

Those helpers are part of the global astro-static stack even though this repository tracks the agent prompts, references, and schemas.

## Agent roles

| File | Role |
|---|---|
| `orchestrator.md` | Primary pipeline coordinator; owns phase state, dispatch, gates, and final result publication. |
| `researcher.md` | Business/brand/content research and creative brief production. |
| `design-extractor.md` | Reference-site token and section-pattern extraction. |
| `asset-generator.md` | Logo, favicons, OG image, theme CSS, font config, content-image and video-shot manifest updates. |
| `img-gen.md` | PPQ image-generation subagent using the shared PPQ credential resolver. |
| `vid-gen.md` | PPQ video-generation subagent for background MP4s. |
| `hyperframes-vid-gen.md` | Deterministic HTML/GSAP/headless-Chrome branded intro video generator. |
| `instagram-extractor.md` | Instagram brand/source extraction path for visual and content signals. |
| `frontend-builder.md` | Local-only Astro/Tailwind/Tina source generator. Never deploys. |
| `build-deployer.md` | Deployment owner: bootstrap join, rsync, remote build, smoke, final validation. |
| `auditor.md` | Read-only pipeline/state/configuration auditor. |

## Canonical references

- `references/reference-stack.md` — Astro 6, Tailwind v4, TinaCMS, SSR, visual editing, image/video, and design-system contract.
- `references/pipeline-contract.md` — phase IDs, status values, retry/invalidation rules, `STATUS:<TOKEN>` grammar, and secret-handling contract.
- `schemas/*.schema.json` — pipeline artifact schemas used by `validate-pipeline.py`.

## Pipeline phase graph

The canonical phase IDs are:

1. `0_bootstrap_launch`
2. `1_design_extraction`
3. `2_research`
4. `2_5_brief_validation`
5. `3_asset_generation`
6. `3_5_image_generation`
7. `3_6_video_generation`
8. `3_8_hyperframes_hero_optional`
9. `4_1_frontend_codegen`
10. `4_2_tinacms_local_build`
11. `4_3_build_deploy`
12. `5_publish_result`

Do not rename phases in prompts, schemas, state files, or scripts. Update `references/pipeline-contract.md`, schemas, validators, and tests together when the phase graph changes.

## Current hardening contracts

The stack is hardened around failures found in live pipeline runs:

- **TinaCMS auth:** `PasswordAuthProvider.getUser()` must return `false` when unauthorized or a user object with `name`/`email` when authorized. Returning boolean `true` crashes Tina with `Cannot read properties of undefined (reading 'name')`.
- **Tina island route:** `src/pages/tina-island/[name].ts` must export `POST` via `experimental_createIslandRoute`; `ALL` is rejected.
- **Tina admin build:** `admin/` and `tina/__generated__/` are built locally in Phase 4.2 and must be published; `admin/.gitignore` is rejected.
- **SSR deployment:** `dist/server/entry.mjs` is valid output for TinaCMS projects. Build/deploy/smoke must not require `dist/client/index.html` when SSR exists.
- **Smoke tests:** SSR smoke fetches live `SITE_URL` and checks local `dist/client` assets.
- **PPQ credentials:** image/video generation resolves credentials through the global `ppq-auth.sh` helper, checking OpenCode auth/config after `PPQ_API_KEY`.
- **Gitea safety:** generated output, credentials, logs, and pipeline secrets must stay out of pushed source repos.
- **Secret handling:** pipeline credentials stay owner-only and are never printed in agent summaries.

## Verification

Run the regression suite from anywhere:

```bash
python3 /Users/djesys/.config/opencode/astro-static/test_regressions.py
```

Run shell syntax checks for the global support scripts:

```bash
bash -n /Users/djesys/.config/opencode/astro-static/setup-vps.sh
bash -n /Users/djesys/.config/opencode/astro-static/phases/smoke.sh
bash -n /Users/djesys/.config/opencode/astro-static/phases/push-gitea.sh
bash -n /Users/djesys/.config/opencode/astro-static/phases/tinacms-local-build.sh
bash -n /Users/djesys/.config/opencode/astro-static/phases/ppq-auth.sh
```

Expected regression output at this stack revision:

```text
Ran 46 tests
OK
```

## Editing discipline

- Keep agent prompts, references, schemas, validators, and shell helpers synchronized.
- Stage only `astro-static/**` when publishing astro-static changes from the shared `all-agents` repo.
- Do not include unrelated local changes from other agent families.
- Do not print or commit secrets from `pipeline/vps-connection.json`, bootstrap outputs, OpenCode auth, SSH keys, or PPQ credentials.
