# Plan: Tina-first Astro 7 transformation for astro-static

Created: 2026-06-23
Status: ready for implementation planning/execution in a later session
Target root: `agents/astro-static/` in the OpenCode config repository

## Problem frame

The current `astro-static` pipeline already integrates TinaCMS, but it still treats Tina mostly as a generated CMS layer on top of a generated Astro site. That leaves visual-editing coverage dependent on the frontend-builder remembering to expose every string, image, background, section field, and repeated object through Tina. In practice, generated sites can still contain hardcoded copy, hardcoded media paths, static component defaults, non-editable background images, or sections rendered outside Tina visual-editing islands.

The target architecture is **Tina-first true visual editing**:

> The pipeline must not generate a website and then ask whether enough of it is editable. It must generate a website from an explicit Tina-owned content model, and fail validation if any visible text, image, video, background image, CTA, nav item, footer item, card, testimonial, gallery asset, section setting, or SEO field is not editable or explicitly marked as allowed static UI chrome.

Astro 7 should be adopted as part of this work, but the Astro upgrade is not the primary solution. Astro 7 improves performance and updates compiler/bundler behavior; it does not automatically infer Tina fields. The real solution is content-model-first generation, full field coverage validation, and reusable Tina block renderers.

---

## Research grounding

### TinaCMS Astro visual editing model

Tina's current Astro visual editing flow depends on explicit wiring:

- `tina()` integration injects edit-mode bridge/form payloads.
- Every route data loader must wrap Tina queries with `requestWithMetadata()` so the bridge can identify forms and supply overlay data.
- Editable regions should be wrapped in `TinaIsland` markers.
- The island endpoint `/tina-island/[name]` re-renders regions on editor updates.
- Click-to-edit requires DOM elements to be stamped with `data-tina-field={tinaField(...)}`.

Source: TinaCMS Visual Editing Setup for Astro — `https://tina.io/docs/contextual-editing/astro`.

Tina's Astro setup guide also states that adding Tina to an existing site only wires a demo; existing pages need to copy the visual-editing pattern into their own pages and components. This supports the conclusion that Tina cannot be reliably bolted on after arbitrary Astro code is generated.

Source: TinaCMS Astro setup guide — `https://tina.io/docs/frameworks/astro`.

The release notes for `@tinacms/astro@0.3.0` confirm that static-page visual editing works when editable regions are wrapped in Tina islands and the adapter can serve the island endpoint. They also emphasize bridge serving from `/admin/bridge.js`, primary-form selection, and static/mixed output support.

Source: `@tinacms/astro@0.3.0` release — `https://github.com/tinacms/tinacms/releases/tag/@tinacms%2Fastro@0.3.0`.

### Astro 7 upgrade implications

Astro 7 brings Vite 8, a Rust compiler, changed whitespace/HTML strictness, route caching stabilization, and a newer Markdown pipeline. It improves speed and future compatibility, but it can expose invalid markup and integration assumptions. That makes it a good time to add fixture-backed validation.

Sources:

- Astro 7 blog — `https://astro.build/blog/astro-7/`
- Astro 7 upgrade guide — `https://docs.astro.build/en/guides/upgrade-to/v7/`
- Astro upgrade overview — `https://docs.astro.build/en/upgrade-astro/`

Astro's TinaCMS guide for Astro 7 still describes explicit Tina collection/schema setup and does not remove the need to model fields manually.

Source: Astro v7 TinaCMS guide — `https://v7.docs.astro.build/en/guides/cms/tina-cms/`.

### Current local pipeline state

Current `frontend-builder.md` already contains the right goals: content collections as source of truth, Tina config generation, `requestWithMetadata()`, `tinaField()`, settings-backed header/footer, no hardcoded marketing copy, and editable images/backgrounds. However, this lives mostly as prompt instruction rather than a deterministic intermediate contract and full coverage gate.

Relevant local references:

- `frontend-builder.md` — TinaCMS and editable-surface requirements.
- `orchestrator.md` — Phase 2 research, Phase 2.5 validation, Phase 4.1 frontend codegen.
- `scripts/validate-pipeline.py` — current source scanning for `requestWithMetadata`, `tinaField`, `data-tina-field`, and editable surface checks.
- `scripts/setup-vps.sh` — package matrix and Astro/Tina scaffold.

---

## Target architecture

```text
brief
  -> research / creative brief
  -> Tina blueprint generation and validation
  -> asset generation tied to Tina field refs
  -> Tina schema + Astro content schema + seeded content
  -> block-renderer Astro site generated from editable content only
  -> Tina coverage manifest
  -> local Tina build
  -> Astro 7 build/deploy/smoke/final validation
```

The central new contract is a deterministic `pipeline/01-tina-blueprint.json` artifact. Frontend-builder should not infer a complete CMS shape directly from prose. It should generate from this blueprint.

The second new contract is `pipeline/03-tina-coverage.json`, proving every editable field declared in the blueprint has schema, content, renderer, island, and field-marker coverage.

---

## Scope

### In scope

- Upgrade generated projects and scripts to Astro 7-compatible package ranges and build assumptions.
- Make TinaCMS the primary content architecture for generated sites.
- Require all visible/editable surfaces to be Tina-owned:
  - text
  - rich text
  - nav/footer/header content
  - CTAs
  - cards/repeated lists
  - images
  - background images
  - video backgrounds/posters
  - gallery items
  - SEO/meta content
  - section ordering and variant settings
- Add deterministic Tina blueprint and coverage artifacts.
- Add reusable block library contracts and renderers.
- Strengthen validation and regression fixtures.
- Preserve existing self-hosted Tina auth/data-layer approach unless implementation research proves it incompatible with Astro 7.

### Out of scope

- Switching from self-hosted Tina to Tina Cloud.
- Replacing TinaCMS with another CMS.
- Building a drag-and-drop visual page builder outside TinaCMS.
- Rewriting VPS provisioning beyond changes needed for Astro 7/Tina runtime compatibility.
- Migrating already-generated client sites unless explicitly requested later.

### Deferred follow-up

- Rich visual block previews inside Tina's sidebar beyond baseline visual editing.
- Per-client custom block authoring UI.
- Live collaborative editing.
- Full migration tooling for old generated sites.

---

## Key technical decisions

### D1. Tina blueprint is canonical before frontend generation

The researcher/normalizer must produce `pipeline/01-tina-blueprint.json` before assets or frontend codegen. Frontend-builder generates from the blueprint, not directly from freeform brief prose.

Rationale: editability must be decidable before UI code exists.

### D2. Use block-based page schemas

Generated pages should use a `sections` object-list/block schema. Each block has a stable `type`, `id`, fields, media fields, variant settings, and Tina renderer mapping.

Rationale: true visual editing needs addable/reorderable sections and stable field refs.

### D3. Use a reusable Tina block library

The pipeline should standardize common blocks instead of inventing arbitrary Astro component structures per site. Visual uniqueness comes from tokens, variants, layout options, assets, and content, not from bypassing the CMS structure.

Rationale: reusable block contracts are testable; arbitrary generated components are not.

### D4. Every editable field gets a stable field ref

Use field refs such as:

```text
settings.siteName
settings.nav[0].label
pages.home.sections.hero-home.headline
pages.home.sections.hero-home.backgroundImage
collections.events.event-001.title
```

Rationale: validators, assets, renderers, and tests need a shared address space.

### D5. Assets target Tina fields

Image/video generation should produce assets for declared Tina media fields, not just arbitrary manifest paths.

Rationale: editable media fields need default values seeded into content and editable overrides in Tina.

### D6. Astro 7 upgrade is done with fixture coverage

Update package ranges and reference docs to Astro 7, but do it alongside fixture sites proving Tina admin, islands, field markers, and visual editing coverage still work.

Rationale: Astro 7's compiler and Vite 8 can expose integration/markup assumptions.

### D7. Static output remains acceptable only with working island endpoint

Continue supporting `output: "static"` with Node adapter if `/tina-island/[name]`, `/api/tina/*`, `/admin/bridge.js`, and `/tina/__generated__/*` are served correctly. If fixtures show repeated pain, switch generated projects to `output: "server"` and adapt Caddy accordingly.

Rationale: Tina supports static visual editing with islands, but the endpoint is still runtime behavior.

---

## Proposed artifacts

### `pipeline/01-tina-blueprint.json`

Purpose: canonical editable content model.

Required top-level shape:

```json
{
  "schema_version": "astro-static-tina-blueprint/v1",
  "project_name": "example",
  "settings": {},
  "pages": [],
  "collections": [],
  "blocks": [],
  "media_fields": [],
  "editable_surface_map": []
}
```

Each visible field must identify:

- `field_ref`
- `field_type`
- `owner` (`settings`, `page`, `collection`, `block`)
- `source_default`
- `tina_field_path`
- `content_path`
- `render_intent`
- `required_marker` (`data-tina-field`, `tina-island`, or `static-exempt`)
- optional `static_exemption_reason`

### `pipeline/03-tina-coverage.json`

Purpose: generated proof that the frontend implementation covers the blueprint.

Required per-field proof:

```json
{
  "field_ref": "pages.home.sections.hero-home.headline",
  "declared_in_blueprint": true,
  "tina_schema_path": "tina/config.ts",
  "astro_schema_path": "src/content.config.ts",
  "content_file": "src/content/pages/home.json",
  "renderer_file": "src/components/tina/blocks/HeroBlock.astro",
  "island_name": "hero-home",
  "has_tina_field_marker": true,
  "surface_kind": "text"
}
```

### Generated source structure

```text
src/
  content.config.ts
  content/
    pages/
      home.json
    settings/
      site.json
    collections/
      ...
  lib/
    tina/
      data.ts
      field-map.ts
      islands.ts
      coverage.ts
  components/
    tina/
      PageRenderer.astro
      SectionRenderer.astro
      MediaField.astro
      BackgroundField.astro
      blocks/
        HeroBlock.astro
        FeatureGridBlock.astro
        GalleryBlock.astro
        CtaBlock.astro
        RichTextBlock.astro
```

---

## Implementation units

### U1. Upgrade reference stack and package matrix to Astro 7

**Goal:** Make Astro 7 the generated-project baseline while preserving Tina visual editing runtime requirements.

**Files:**

- `references/reference-stack.md`
- `frontend-builder.md`
- `scripts/setup-vps.sh`
- `scripts/validate-pipeline.py`
- `scripts/test_regressions.py`
- `README.md`

**Approach:**

- Update canonical package ranges to Astro 7 and matching adapters/integrations after checking current compatibility.
- Document Astro 7 breaking-change constraints: Vite 8, Rust compiler strictness, new Markdown behavior, reserved `src/fetch.ts`, stricter invalid HTML handling.
- Ensure generated components avoid invalid nesting and whitespace-sensitive assumptions.
- Keep `@tinacms/astro`, `tinacms`, `@tinacms/cli`, and `@tinacms/datalayer` on current compatible versions.
- Add a compatibility note: Astro 7 does not solve missing editability; Tina field modeling remains required.

**Test scenarios:**

- Regression test verifies canonical dependency ranges include Astro 7.
- Regression test verifies generated scaffold does not create reserved `src/fetch.ts`.
- Regression test verifies reference docs mention Astro 7 strict HTML/invalid nesting risk.
- Fixture build test should later run `astro check` and `astro build` against a generated Tina-first fixture.

**Verification:**

- Package matrix and docs consistently reference Astro 7.
- Existing Astro 6-only instructions are removed or marked legacy.

---

### U2. Add Tina blueprint schema and phase contract

**Goal:** Introduce `pipeline/01-tina-blueprint.json` as the required editable-content contract.

**Files:**

- `schemas/01-tina-blueprint.schema.json`
- `references/pipeline-contract.md`
- `orchestrator.md`
- `scripts/validate-pipeline.py`
- `scripts/test_regressions.py`

**Approach:**

- Add blueprint schema with required `settings`, `pages`, `blocks`, `collections`, `media_fields`, and `editable_surface_map`.
- Add a new phase gate after Phase 2.5 and before Phase 3, or fold it into Phase 2.5 as `2_6_tina_blueprint`.
- Require blueprint validation before asset generation.
- Add STATUS tokens:
  - `TINA_BLUEPRINT_OK`
  - `TINA_BLUEPRINT_FAILED`
  - `TINA_BLUEPRINT_MISSING_FIELD`
  - `TINA_BLUEPRINT_UNSUPPORTED_BLOCK`

**Test scenarios:**

- Valid blueprint with settings, one page, one hero block, text field, image field passes.
- Blueprint missing settings-backed nav/footer fails.
- Blueprint with visible field but no field ref fails.
- Blueprint with media field but no surface/render intent fails.
- Blueprint with static exemption but missing reason fails.

**Verification:**

- `validate-pipeline.py --phase research` or new blueprint phase rejects incomplete editability contracts before frontend-builder runs.

---

### U3. Add deterministic Tina blueprint generator

**Goal:** Convert creative briefs into a normalized Tina blueprint before code generation.

**Files:**

- `scripts/phases/tina-blueprint.py`
- `scripts/test_regressions.py`
- `orchestrator.md`
- `researcher.md`

**Approach:**

- Implement a deterministic script with modes:
  - `generate`
  - `validate`
  - `summarize`
- Read `pipeline/01-creative-brief.json` and optional design tokens/assets.
- Normalize page sections into supported block types.
- Convert visible text/media requirements into field refs.
- Generate settings fields for global chrome.
- Fail when a section cannot be mapped to a known block type unless it is explicitly marked as custom with a complete field contract.

**Test scenarios:**

- Creative brief with hero/features/gallery/CTA produces matching block list.
- Repeated feature cards become object-list fields, not hardcoded arrays.
- Header/footer/nav are always generated under settings.
- Unknown section type fails with actionable error.
- Background image requirement becomes an editable media field, not a static style.

**Verification:**

- The script emits `STATUS:TINA_BLUEPRINT_OK` and writes a schema-valid blueprint.

---

### U4. Upgrade researcher output to CMS-native content planning

**Goal:** Make research produce content that can feed the blueprint without guesswork.

**Files:**

- `researcher.md`
- `schemas/01-creative-brief.schema.json`
- `scripts/test_regressions.py`

**Approach:**

- Require `content_model` to include settings, pages, page sections, collection types, media requirements, and editable/static classification.
- Require every planned page section to name intended block type candidates.
- Require media fields for all images/backgrounds/videos that are visible content.
- Require static exemptions only for true UI controls/decorative chrome.

**Test scenarios:**

- Creative brief schema rejects page sections without editable fields.
- Creative brief schema rejects image/background intent without media field description.
- Creative brief schema accepts explicit UI static text only with reason.
- Regression prompt test confirms researcher instructions prohibit treating Tina as post-generation patching.

**Verification:**

- Research output gives enough structure for `tina-blueprint.py` to run without freeform inference.

---

### U5. Define the Tina block library

**Goal:** Create reusable, editable block contracts that generated sites are built from.

**Files:**

- `references/tina-block-library.md`
- `schemas/01-tina-blueprint.schema.json`
- `frontend-builder.md`
- `references/reference-stack.md`
- `scripts/test_regressions.py`

**Initial block types:**

- `hero`
- `splitFeature`
- `featureGrid`
- `cardGrid`
- `gallery`
- `testimonial`
- `cta`
- `faq`
- `contact`
- `richText`
- `mediaFeature`
- `eventSchedule`
- `teamGrid`

**Every block contract defines:**

- Tina field definitions.
- Astro/Zod schema shape.
- Required seed content.
- Required renderer component.
- Required `TinaIsland` behavior.
- Required field markers.
- Editable media/background fields.
- Variant/style fields.

**Test scenarios:**

- Each block has a documented schema, renderer, and coverage contract.
- Each block with an image/background/video has an editable media field.
- Each repeated item field is an object-list field, not a hardcoded source array.
- Block library docs include enough examples for frontend-builder to generate consistently.

**Verification:**

- New fixtures can be built solely from documented block types.

---

### U6. Refactor frontend-builder to generate Tina-first source

**Goal:** Make frontend-builder generate schema/content/renderers from the blueprint, not from ad hoc design decisions.

**Files:**

- `frontend-builder.md`
- `references/reference-stack.md`
- `scripts/validate-pipeline.py`
- `scripts/test_regressions.py`

**Approach:**

Frontend-builder order must become:

1. Read and validate `pipeline/01-tina-blueprint.json`.
2. Generate `tina/config.ts`.
3. Generate `src/content.config.ts`.
4. Seed settings and page content files.
5. Generate Tina data loaders with `requestWithMetadata(..., { priority: 'primary' })` for page docs.
6. Generate field-map helpers for nested block/object fields.
7. Generate block renderers.
8. Generate page renderer and route pages.
9. Generate island registry and endpoint.
10. Generate coverage manifest.
11. Run validation.

**Rules:**

- No visible marketing copy in component defaults.
- No visible strings passed as literal component props.
- No local arrays for cards/testimonials/events unless the array comes from content.
- No hardcoded `src`, `poster`, `background-image`, or Tailwind `bg-[url(...)]` for content media.
- All visible text has `data-tina-field` unless static-exempt.
- All editable regions are wrapped for island refresh.

**Test scenarios:**

- Generated hero headline is editable and has field marker.
- Generated background image comes from content media field and has coverage proof.
- Generated nav/footer come from settings content.
- Repeated feature cards are Tina object-list fields.
- Generated source has no hardcoded marketing copy patterns.
- Generated page uses `requestWithMetadata` directly in its data path, not merely via unused import.

**Verification:**

- A generated fixture site passes final validation and coverage validation.

---

### U7. Add field-map and coverage generation conventions

**Goal:** Give generated components a reliable way to map nested Tina fields to DOM markers.

**Files:**

- `references/reference-stack.md`
- `frontend-builder.md`
- `scripts/validate-pipeline.py`
- `schemas/03-tina-coverage.schema.json`
- `scripts/test_regressions.py`

**Approach:**

- Standardize a generated `src/lib/tina/field-map.ts` helper for nested block/list fields.
- Standardize `src/lib/tina/coverage.ts` or direct `pipeline/03-tina-coverage.json` generation.
- Each block renderer must register coverage for each field it renders.
- Backgrounds need explicit wrappers such as `BackgroundField.astro`, because CSS backgrounds are not naturally clickable/editable.

**Test scenarios:**

- Nested list field marker points to the specific item field.
- Background image wrapper exposes a clickable overlay/field marker.
- Coverage manifest fails if renderer file omits a declared field.
- Coverage manifest fails if renderer references a field not declared in blueprint.

**Verification:**

- Coverage manifest gives a field-by-field proof trail from blueprint to renderer.

---

### U8. Make asset generation field-ref aware

**Goal:** Tie generated images/videos to Tina media fields from the start.

**Files:**

- `asset-generator.md`
- `img-gen.md`
- `vid-gen.md`
- `schemas/02-asset-manifest.schema.json`
- `schemas/02-image-shot-list.schema.json`
- `schemas/02-video-shot-list.schema.json`
- `scripts/phases/asset-fallbacks.sh`
- `scripts/validate-pipeline.py`
- `scripts/test_regressions.py`

**Approach:**

- Image/video shot lists include `field_ref` and `content_path`.
- Asset manifest records both generated file path and Tina default value.
- Generated media under `public/images` or `public/videos` is seeded into matching content fields.
- Renderers always use content field first and generated fallback only if content value is absent.
- Background images and video posters are editable fields, not CSS constants.

**Test scenarios:**

- Hero background image shot maps to `pages.home.sections.hero.backgroundImage`.
- Gallery image shot maps to a gallery object-list image field.
- Video background maps to editable video/poster fields.
- Fallback placeholders still seed Tina fields and coverage refs.
- Validator rejects content media visible in renderer without a matching field ref.

**Verification:**

- Generated site can change hero image/background via Tina without code changes.

---

### U9. Strengthen validator to enforce true visual editing coverage

**Goal:** Change validation from heuristic source scanning to contract coverage.

**Files:**

- `scripts/validate-pipeline.py`
- `schemas/03-tina-coverage.schema.json`
- `scripts/test_regressions.py`

**Approach:**

Add validation stages:

- Blueprint completeness.
- Tina schema/content/schema parity.
- Renderer coverage.
- Hardcoded visible copy detection.
- Hardcoded media/background detection.
- Island endpoint/registry coverage.
- Static exemption audit.

**Validator failures:**

- `TINA_FIELD_UNRENDERED`
- `VISIBLE_COPY_NOT_TINA_BACKED`
- `VISIBLE_MEDIA_NOT_TINA_BACKED`
- `BACKGROUND_NOT_TINA_BACKED`
- `TINA_ISLAND_MISSING`
- `TINA_COVERAGE_MISSING`
- `STATIC_EXEMPTION_INVALID`

**Test scenarios:**

- Fixture with hardcoded headline fails.
- Fixture with hardcoded background image fails.
- Fixture with image field but no `data-tina-field` fails.
- Fixture with field marker but missing `TinaIsland` fails.
- Fixture with static UI control and valid exemption passes.
- Fixture with bare `data-static-copy` fails.

**Verification:**

- Final validation cannot pass unless all editable surfaces are covered.

---

### U10. Update Tina local build and deploy assumptions for Astro 7

**Goal:** Ensure local Tina admin build, remote Astro 7 build, Caddy routing, and smoke checks still work.

**Files:**

- `scripts/phases/tinacms-local-build.sh`
- `scripts/phases/smoke.sh`
- `scripts/setup-vps.sh`
- `build-deployer.md`
- `orchestrator.md`
- `scripts/test_regressions.py`

**Approach:**

- Verify `tinacms build --local --skip-cloud-checks` output paths for current Tina versions.
- Verify `/admin/bridge.js` handling remains correct.
- Verify Caddy serves `/admin/*`, `/tina/__generated__/*`, `/tina-island/*`, and `/api/tina/*` correctly.
- Update smoke checks to assert visual-editing runtime prerequisites:
  - admin exists
  - bridge exists
  - schema exists
  - island endpoint route exists
  - page contains Tina island markers when editable blocks exist
  - no broken field payload assumptions

**Test scenarios:**

- Smoke fixture with missing bridge fails.
- Smoke fixture with missing island route fails.
- Smoke fixture with no Tina island markers on editable page fails.
- Astro 7 fixture still serves admin and live page.

**Verification:**

- Build-deploy reports success only after Tina runtime prerequisites are proven.

---

### U11. Add golden Tina-first fixtures

**Goal:** Preserve behavior across future prompt/script changes.

**Files:**

- `scripts/fixtures/tina-first/landing/`
- `scripts/fixtures/tina-first/gallery/`
- `scripts/fixtures/tina-first/multipage/`
- `scripts/fixtures/tina-first/collections/`
- `scripts/fixtures/tina-first/media-backgrounds/`
- `scripts/test_regressions.py`

**Fixture coverage:**

1. Landing: hero, feature grid, CTA.
2. Gallery: images and background images.
3. Multipage: nav/footer/settings and per-page metadata.
4. Collections: events/team/posts.
5. Media backgrounds: background image, video, poster, fallback.

**Test scenarios:**

- Each fixture validates blueprint.
- Each fixture validates coverage manifest.
- Each fixture has no hardcoded visible marketing copy.
- Each fixture has no hardcoded content media paths.
- Each fixture has Tina schema/content/renderer parity.
- Negative fixtures prove validator catches broken editability.

**Verification:**

- Regression suite fails quickly if future agents generate non-editable fields.

---

### U12. Update orchestration and status grammar

**Goal:** Make the new phases resumable and diagnosable.

**Files:**

- `orchestrator.md`
- `references/pipeline-contract.md`
- `schemas/00-pipeline-state.schema.json`
- `scripts/test_regressions.py`

**Approach:**

- Add phase `2_6_tina_blueprint` or explicitly include blueprint in Phase 2.5.
- Add phase status notes for coverage validation after frontend generation.
- Add all new `STATUS:<TOKEN>` values to canonical grammar.
- Ensure edit-site flows invalidate blueprint/assets/frontend when content model changes.

**Test scenarios:**

- Pipeline state schema includes new blueprint phase if added.
- Orchestrator phase headings match canonical order.
- All emitted `STATUS:` tokens are listed in the orchestrator grammar.
- Edit-site contract marks blueprint and downstream phases stale on content-model changes.

**Verification:**

- Resume behavior has a clear checkpoint before expensive asset/codegen work.

---

### U13. Update agent permissions and responsibilities around Tina-first flow

**Goal:** Keep responsibilities narrow as the pipeline gains more contracts.

**Files:**

- `orchestrator.md`
- `researcher.md`
- `asset-generator.md`
- `frontend-builder.md`
- `auditor.md`
- `build-deployer.md`
- `README.md`

**Approach:**

- Researcher owns content intent and CMS-native content model.
- Blueprint script owns deterministic normalization.
- Asset-generator owns field-ref media defaults.
- Frontend-builder owns schema/content/renderers/coverage.
- Validator owns coverage enforcement.
- Auditor reports missing editability but never patches.
- Narrow broad `task` and `skill` permissions where practical.

**Test scenarios:**

- Frontmatter audit test confirms agents with skills use explicit deny-by-default skill permissions.
- Prompt regression test confirms frontend-builder cannot proceed without blueprint.
- Prompt regression test confirms asset-generator reads field refs.

**Verification:**

- Agent boundaries are clear enough for future sessions to modify one layer without breaking all others.

---

## Rollout strategy

### Stage 1: Contracts only

Implement U1-U3 and U12 first. This creates the blueprint contract without changing all codegen behavior immediately.

Exit criteria:

- Blueprint schema exists.
- Blueprint generator works on simple creative briefs.
- Orchestrator knows the new gate.
- Tests cover valid and invalid blueprints.

### Stage 2: Tina-first codegen

Implement U4-U7. Frontend-builder starts generating from the blueprint and emits coverage.

Exit criteria:

- Landing fixture has full editable text/image/background coverage.
- Validator rejects hardcoded visible copy/media.

### Stage 3: Asset field mapping

Implement U8. Generated media becomes Tina-editable by default.

Exit criteria:

- Generated hero/gallery/background assets can be changed through Tina content fields.
- Placeholder fallback still maps to editable fields.

### Stage 4: Runtime/deploy hardening

Implement U9-U11. Astro 7/Tina fixture build and smoke coverage proves runtime behavior.

Exit criteria:

- Golden fixtures pass validation.
- Negative fixtures fail for the expected reasons.
- Smoke checks cover admin, bridge, schema, islands, and field markers.

### Stage 5: Permission/docs cleanup

Implement U13 and update README/reference docs.

Exit criteria:

- Later sessions have a clear mental model and agent permissions align with responsibility boundaries.

---

## Risk analysis

### Risk: Tina's Astro APIs change while upgrading packages

Mitigation:

- Pin tested package ranges.
- Keep a compatibility fixture.
- Update docs from official Tina source before implementation.

### Risk: Block library reduces design flexibility

Mitigation:

- Blocks support style variants, layout variants, theme tokens, and free rich-text/media fields.
- Allow custom blocks only when a complete field contract is declared in the blueprint.

### Risk: CSS background images are hard to click/edit

Mitigation:

- Render background media through a standard `BackgroundField.astro` wrapper with an edit marker overlay.
- Require coverage entries for background fields.

### Risk: Validator becomes too strict for legitimate UI chrome

Mitigation:

- Keep explicit static exemptions with reason values.
- Exempt only non-marketing UI controls, decorative icons, and accessibility labels where appropriate.

### Risk: Astro 7 compiler strictness breaks generated markup

Mitigation:

- Add fixture builds early.
- Document invalid nesting constraints in `reference-stack.md`.
- Prefer simple, valid Astro component structure.

### Risk: Static output plus runtime Tina endpoints remains fragile

Mitigation:

- Fixture-test static + island endpoint behavior.
- If repeated failures occur, switch generated projects to `output: "server"` and update Caddy/build expectations.

---

## Success criteria

- A generated site cannot pass final validation if any visible content element is not Tina-editable or explicitly static-exempt.
- Text, images, background images, video backgrounds/posters, repeated cards, nav/footer, and CTAs are editable through Tina.
- Generated code contains no hardcoded marketing copy or content media paths.
- Tina visual editing works on generated Astro 7 fixtures.
- The pipeline exposes clear artifacts for debugging: blueprint, asset manifest with field refs, coverage manifest, status tokens.
- Future design variation remains possible through tokens, block variants, and content, without sacrificing editability.

---

## Suggested first later-session prompt

```text
Continue from references/tina-first-astro7-transformation-plan.md. Start with U1-U3 only: Astro 7 package/reference update, Tina blueprint schema, and deterministic blueprint generator. Do not refactor frontend-builder yet. Add regression tests for the new blueprint contract.
```
