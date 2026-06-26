# Decoupled Blocks — reference architecture for editable static sites

**Status:** Proven prototype (2026-06-25), headless-verified end-to-end. This is the
**target** pattern for the planned editing migration — it is **NOT yet** what the live
pipeline scaffolds. As of `astro-static@e22e0a9`, `setup-vps.sh` + `frontend-builder.md`
still generate the SSR + in-page-overlay (`tina-island` / `data-tina-field`) pattern.
This folder is the known-good destination the pipeline should converge onto.

---

## Why this exists

TinaCMS **in-page visual editing** ("click the headline on the live page → edit it") is
**React-first and experimental on Astro**. On a real generated site it failed structurally:

- the static page rendered **0** `data-tina-field` markers (the build-time Tina query
  fails — `/api/tina/gql` has no origin during prerender), and
- the runtime fix-up route `POST /tina-island/page` returned **404**.

So click-to-edit could never work, and the validator only checked for the *strings* in
source — it shipped a site where editing was 100% broken at runtime.

## The pattern: decouple the editor from the output

> **The published site never imports Tina. Tina only powers the admin. They meet at
> the markdown files in git.**

1. **Astro reads the content directly** (`getEntry` / content collections) — no Tina
   client, no `requestWithMetadata`, no `TinaIsland`, no `data-tina-field`. Because the
   build never runs a CMS query, it **cannot fail** on one, and the output carries **zero
   editing runtime**.
2. **Content is a `blocks` list** — typed sections in markdown frontmatter
   (`_template: hero`, `features`, `cta`, …).
3. **Each `_template` maps to an Astro component** via a registry in the page
   (`src/pages/index.astro`). Add a section type = one component + one registry entry +
   one Tina template.
4. **Tina's admin is the only editing surface** — a page collection whose object-list
   `blocks` field has `templates` mirroring the components. Editors **add / reorder /
   edit / delete** sections (the "fully customizable" surface). Saving writes markdown →
   git → rebuild.

No overlay, no island route, no `data-tina-field`. The reliable half of Tina (the admin
forms + blocks) does the work; the fragile half (in-page overlay) is gone.

## Measured proof (this prototype, headless-verified)

| Metric | Result |
|---|---|
| Published `dist/index.html` | **4,987 bytes**, **0** `<script>`, **0** JS files (CSS inlined) |
| Stack | Astro **7.0.3** (`output: static`) + TinaCMS **3.9.3**, React 18 (admin only) |
| Edit loop | edit Hero heading in admin → git `home.md` → `astro build` → static HTML reflects it |
| Add-a-section | visual block picker → fill → save → `home.md` 3→4 blocks → rebuild includes it, **still 0 JS** |
| Editing UX | admin shows add `+` / drag-reorder / pencil-edit / trash-delete on the Sections list |

## The parity contract (what the migration's validator should enforce)

Replace the old `03-tina-coverage` / `data-tina-field` coverage gate with **blocks parity**:

- every Astro block component (`src/components/blocks/<T>.astro`) has a **matching Tina
  template** `<T>` (same name; fields ⊇ the props the component reads), and a **registry
  entry** mapping `_template: <T>` → the component;
- seed content blocks validate against their templates;
- the built page ships **~0 client JS** (leanness gate);
- **no** `tina-island`, `data-tina-field`, `requestWithMetadata`, or `TinaIsland` in
  generated source.

## Run it

Astro 7's `astro dev` **daemonizes** (and auto-daemonizes when piped), which breaks the
`tinacms dev -c "astro dev"` wrapper (the wrapper exits when its child returns). Run the
two servers **separately**:

```bash
npm install
# 1. Tina GraphQL backend (:4001) + builds the admin to public/admin
npx tinacms dev -c "tail -f /dev/null" &
# 2. Astro serves the site + /admin
npx astro dev --port 3200
# → site:  http://localhost:3200/        admin: http://localhost:3200/admin
```

Production build (lean static):

```bash
npx astro build      # → dist/ : static HTML, 0 client JS
npx astro preview --port 3300
```

## Files

```
tina/config.ts                     Tina schema: page collection + object-list `blocks` (templates)
content/pages/home.md              Seed content as a blocks list (the editable source of truth)
src/content.config.ts              Astro content collection (glob loader over content/pages)
src/pages/index.astro              Reads markdown, maps _template → block component (the registry)
src/components/blocks/*.astro      One Astro component per block type (zero client JS)
src/layouts/BaseLayout.astro       HTML shell + global stylesheet
src/styles/global.css              Inlined, lean, designed styles
```
