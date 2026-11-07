# Astro-Static Pipeline Contract

This is the canonical phase graph and status grammar for the astro-static pipeline. Agent prompts, shell phases, validators, and state files must reference this document instead of maintaining divergent copies.

## Editing mode and completion contract

`admin-blocks` is the new-site default: no collection `ui.router` functions (omit
or use undefined), no frontend metadata loaders, markers or island routes. Render
content directly and edit typed blocks in admin forms. Explicit `overlay` retains
router mappings, `requestWithMetadata`, islands, marker and coverage strictness.
Legacy blueprints missing the mode retain strict overlay validation. Missing
`03-tina-coverage.json` is valid only for admin-blocks; a present file is still
schema-validated. Generate durable `public/admin/login.html` before Phase 4.2 and
publish it as `admin/login.html`; final validation checks both.

Warnings/advisories become a tracked follow-up, not an unconditional halt. Genuine
rights/licensing issues, essential missing media, factual ambiguity and required
approvals halt for review. Preserve explicit Instagram `skip` and no-video choices;
never synthesize business facts. A missing optional video shot-list warning is
suppressed only for explicit `motion_direction.video_backgrounds: false` plus
`3_6_video_generation.status` skipped/not_requested. Missing requested media remains
a failure. Keep all existing phase IDs.

### Machine-enforced usable-editor evidence

New wizard CMS briefs disclose and set `validation_requirements.cms_roundtrip: true`.
The final gate (not codegen/build) then requires real evidence. Legacy briefs without
that explicit requirement remain compatible; never retroactively opt them in on resume.
Missing staging authorization/evidence means **CMS persistence UNVERIFIED** and
human-review for required CMS completion, not a fabricated pass.

1. Use a real browser for login → admin → collection → document's actual form/block
   controls → back. No blank iframe, auth loop or JS exception. Browser CLI usage
   follows current `--help`; no particular browser skill is mandatory.
2. Only an operator explicitly authorizing a **distinct staging origin** may supply
   private `pipeline/cms-staging.json`. Never auto-create it, derive it from production
   metadata or execute production content mutations. Minimal attestation keys:
   `schema_version: "astro-static-cms-staging/v1"`, `environment: "staging"`,
   `authorized_by_operator: true`, `site_url` and `source_revision` as bound below.
3. With `TINA_ADMIN_PASSWORD` injected privately, run the staging gate:

   ```bash
   python3 ~/.config/opencode/astro-static/phases/cms-roundtrip.py --environment staging --allow-write \
     --project-root "$PROJECT_DIR" --site-url "$STAGING_SITE_URL"
   ```

   The phase atomically persists **redacted JSON** as
   `pipeline/cms-roundtrip-report.json`, mode 0600. Never place a password on the CLI or enable shell tracing. Keep the
   gate's recovery backups owner-only and excluded from source sync/push; a failed
   restoration is a blocking review, not another blind write.
   Allow at least **600 seconds** caller timeout for default budgets, or compute
   the larger total for custom budgets. A 120-second timeout may interrupt rollback.
   Timeout is not PASS; preserve MANUAL_REVIEW and recovery data. Hard-killed
   recovery needs operator intervention, not a blind retry.
4. Report schema: `cms-roundtrip-report.schema.json`, version
   `astro-static-cms-roundtrip/v1`, `status: PASS`, `environment: staging`,
    `operator_authorized: true`, `mutation_outcome: "CONFIRMED"`, canonical `origin`, `source_revision` and
   `recovery_path: null`. All eleven nested phase objects must have `status: PASS`:
   preflight, authenticate, baseline, backup, save, persist, live, restore,
   restore_persist, restore_live, source_revision. `evidence` includes original/saved/restored SHA256
    raw-file values (saved differs from original/restored; JSON serialization may
    change raw bytes during restore). Canonical whole-source revision equality
    proves semantic restoration, alongside
   `rebuild_proof: "persisted_settings_and_changed_live_header_html"`.
5. Report `origin` equals attestation `site_url` (canonical staging origin); both
   carry the same `source_revision`. The brief must explicitly approve
   `validation_requirements.cms_source_revision` and `cms_target_site_url` (distinct
   actual target origin). After independently verifying the deployed source/build,
   build-deployer records `deployment: {site_url, source_revision}` in private
   `vps-connection.json`; its site_url is the actual target, not staging. The final
   validator compares all bindings against the current source. No verified mapping
   means UNVERIFIED; never auto-infer one from mismatched origins.
6. Obtain exact content identity (not git HEAD) with the gate's read-only command:

   ```bash
   python3 ~/.config/opencode/astro-static/phases/cms-roundtrip.py --project-root "$PROJECT_DIR" --print-source-revision
   ```

   The gate hashes source/public/Tina files plus root config/manifest/lockfiles,
   normalizes JSON, excludes generated caches, rejects source symlinks, and returns
   `sha256:<64 hex>`. Validator `cms_source_revision(root)` reuses that exact
   implementation. No local-code changes or lockfile regeneration may reuse stale
   evidence. This is source identity, not a claim that a different VPS was built.
7. Record redacted `pipeline/cms-browser-evidence.json`: version
   `astro-static-cms-browser/v1`, `status: PASS`, a nonempty `browser` evidence/session
   reference, booleans `authenticated`, `document_form`, `navigation` all true, and
   `origin` equal to the mapped target plus matching `source_revision`.
   Screenshots/logs must exclude passwords, cookies and tokens. An HTTP mock or unit
   test is not real-browser evidence. Do not manufacture this artifact from a build.

Keep `pipeline/.cms-roundtrip-*/recovery.json`, `pipeline/.cms-roundtrip.lock`,
staging metadata and evidence artifacts private and gitignored/excluded from
source sync/push. A retained recovery directory blocks final completion. The
advisory lock file may remain after a clean run; only an active lock blocks.

These checks validate required evidence and binding, not the truthfulness of a
forged report. Only actual observed staging/browser runs may produce PASS artifacts.

## Phase Graph

| Phase ID | Boundary | Required inputs | Required outputs | Notes |
|---|---|---|---|---|
| `0_bootstrap_launch` | local control node → VPS | `pipeline/00-brief.json`, `pipeline/vps-connection.json` when known | `pipeline/bootstrap.pid`, `pipeline/bootstrap.log`, bootstrap result fetched by join | Non-blocking launch; may be skipped when the VPS is already bootstrapped. |
| `1_design_extraction` | local/web | `pipeline/00-brief.json` | `pipeline/00-design-tokens/` when references exist | Skip when no design references are supplied. |
| `2_research` | local/web | `pipeline/00-brief.json` | `pipeline/01-creative-brief.json` | Produces strategy, content model, recommendations, review flags. |
| `2_5_brief_validation` | local | `pipeline/01-creative-brief.json` | `pipeline/HUMAN_REVIEW.md` or validation pass | Halts when product/content blockers need human review. |
| `2_6_tina_blueprint` | local | `pipeline/01-creative-brief.json` | `pipeline/01-tina-blueprint.json` | Deterministic Tina-owned editable content contract. Must pass before asset generation. |
| `3_asset_generation` | local/API | creative brief, design tokens | `pipeline/02-font-config.json`, `pipeline/02-asset-manifest.json` | Owns identity assets and manifest contract. |
| `3_5_image_generation` | local/API | asset manifest, image shot list | renderable content images, LQIP files, generated content image index | Optional per shot list; deterministic placeholders are valid fallbacks. |
| `3_6_video_generation` | local/API | asset manifest, video shot list | generated MP4 backgrounds or explicit skipped/failed manifest entries | Optional; never use MP4 files as poster images. |
| `3_8_hyperframes_hero_optional` | local | creative brief, assets, font config, theme CSS | `public/videos/hero-intro.mp4` when explicitly enabled | Opt-in; recommendation alone does not enable the phase. |
| `4_1_frontend_codegen` | local | all content/assets/contracts | Astro/Tailwind/Tina source tree | Local code generation only; no SSH, rsync, remote build, or deploy. |
| `4_2_tinacms_local_build` | local | generated Tina/Astro source | `admin/`, `tina/__generated__/_schema.json` | Local Tina admin build after codegen. |
| `4_3_build_deploy` | local → VPS/Gitea | source tree, admin artifacts, bootstrap result | deployed site, smoke result, final validation, Gitea source snapshot | Build-deployer owns join, sync, remote build, smoke, validation; orchestrator then publishes the source snapshot via the canonical Gitea push helper. |
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

Blueprint phase scripts may emit: `STATUS:TINA_BLUEPRINT_OK`, `STATUS:TINA_BLUEPRINT_FAILED`, `STATUS:TINA_BLUEPRINT_MISSING_FIELD`, and `STATUS:TINA_BLUEPRINT_UNSUPPORTED_BLOCK`.

## Secret Handling Contract

- `pipeline/vps-connection.json` may contain secrets and must be mode `0600`.
- `pipeline/bootstrap-result.json` may contain secrets and must be mode `0600`.
- `pipeline/installation-summary.md` may contain URLs, credentials, and diagnostics and must be mode `0600`.
- `pipeline/installation.log` must capture the full installation process and must be mode `0600`.
- `pipeline/generation-report.md` is operator-facing (problems, bugs, gaps, inefficiencies) and is redacted — it must not contain secrets.
- `pipeline/RESULT.md`, `pipeline/STATUS.md`, `pipeline/generation-report.md`, logs, and agent summaries must not print passwords, tokens, private keys, or full secret values. Credentials may be surfaced to the operator only in the live session and the `0600` handoff files.
