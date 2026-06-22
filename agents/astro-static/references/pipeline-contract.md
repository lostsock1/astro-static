# Astro-Static Pipeline Contract

This is the canonical phase graph and status grammar for the astro-static pipeline. Agent prompts, shell phases, validators, and state files must reference this document instead of maintaining divergent copies.

## Phase Graph

| Phase ID | Boundary | Required inputs | Required outputs | Notes |
|---|---|---|---|---|
| `0_bootstrap_launch` | local control node → VPS | `pipeline/00-brief.json`, `pipeline/vps-connection.json` when known | `pipeline/bootstrap.pid`, `pipeline/bootstrap.log`, bootstrap result fetched by join | Non-blocking launch; may be skipped when the VPS is already bootstrapped. |
| `1_design_extraction` | local/web | `pipeline/00-brief.json` | `pipeline/00-design-tokens/` when references exist | Skip when no design references are supplied. |
| `2_research` | local/web | `pipeline/00-brief.json` | `pipeline/01-creative-brief.json` | Produces strategy, content model, recommendations, review flags. |
| `2_5_brief_validation` | local | `pipeline/01-creative-brief.json` | `pipeline/HUMAN_REVIEW.md` or validation pass | Halts when product/content blockers need human review. |
| `3_asset_generation` | local/API | creative brief, design tokens | `pipeline/02-font-config.json`, `pipeline/02-asset-manifest.json` | Owns identity assets and manifest contract. |
| `3_5_image_generation` | local/API | asset manifest, image shot list | renderable content images, LQIP files, generated content image index | Optional per shot list; deterministic placeholders are valid fallbacks. |
| `3_6_video_generation` | local/API | asset manifest, video shot list | generated MP4 backgrounds or explicit skipped/failed manifest entries | Optional; never use MP4 files as poster images. |
| `3_8_hyperframes_hero_optional` | local | creative brief, assets, font config, theme CSS | `public/videos/hero-intro.mp4` when explicitly enabled | Opt-in; recommendation alone does not enable the phase. |
| `4_1_frontend_codegen` | local | all content/assets/contracts | Astro/Tailwind/Tina source tree | Local code generation only; no SSH, rsync, remote build, or deploy. |
| `4_2_tinacms_local_build` | local | generated Tina/Astro source | `admin/`, `tina/__generated__/_schema.json` | Local Tina admin build after codegen. |
| `4_3_build_deploy` | local → VPS | source tree, admin artifacts, bootstrap result | deployed site, smoke result, final validation | Build-deployer owns join, sync, remote build, smoke, validation. |
| `5_publish_result` | local | final validation, deployment metadata | `pipeline/RESULT.md`, final `pipeline/STATUS.md` | Must redact secrets; credentials stay in `pipeline/vps-connection.json` with owner-only permissions. |

## Phase Status Values

Each phase status is one of:

- `pending`
- `in_progress`
- `launched`
- `completed`
- `skipped`
- `stale`
- `invalidated`
- `failed`
- `halted_for_review`

## Retry and Invalidation Rules

- Mark exactly one phase `in_progress` immediately before running it.
- Phase `0_bootstrap_launch` may use `launched` while background bootstrap is running.
- Edit-site flows must mark changed and downstream-dependent phases as `invalidated` or `stale`, recording `invalidated_by`, `invalidated_at`, and `rerun_from`.
- Retry limits belong to the orchestrator, but must not rename phase IDs.

## STATUS Token Grammar

Machine-readable script and agent output uses:

```text
STATUS:<TOKEN>[ <key>=<value> ...][ <human detail>]
```

- No space is allowed after `STATUS:`.
- `<TOKEN>` is uppercase snake case matching `^[A-Z_][A-Z0-9_]*$`.
- Non-blocking warnings still use `STATUS:<TOKEN>` with a token such as `GITEA_TCP_PROBE_WARNING`; do not emit `WARN:<TOKEN>` inside the status token.

## Secret Handling Contract

- `pipeline/vps-connection.json` may contain secrets and must be mode `0600`.
- `pipeline/bootstrap-result.json` may contain secrets and must be mode `0600`.
- `pipeline/installation-summary.md` may contain URLs, credentials, and diagnostics and must be mode `0600`.
- `pipeline/installation.log` must capture the full installation process and must be mode `0600`.
- `pipeline/RESULT.md`, `pipeline/STATUS.md`, logs, and agent summaries must not print passwords, tokens, private keys, or full secret values.
