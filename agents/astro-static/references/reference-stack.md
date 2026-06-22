# Astro 6 + Tailwind v4 + TinaCMS + shadcn/ui — Pipeline Reference

> Reference document — not an agent. Loaded by name from `asset-generator.md`, `frontend-builder.md`, and `design-extractor.md`. Lives under `references/` so it doesn't appear in the agent picker.
>
> **Purpose:** Single source of truth for the astro-static pipeline agents.
> Last verified: 2026-06-19 against npm metadata and official TinaCMS Astro docs.

---

## Canonical Theme Vocabulary

All astro-static agents must use these exact token names. Do not introduce synonyms like `text` for `foreground` or `display` for `heading`.

### Colors
- `--color-primary`
- `--color-primary-light`
- `--color-primary-dark`
- `--color-secondary`
- `--color-secondary-light`
- `--color-secondary-dark`
- `--color-background`
- `--color-surface`
- `--color-foreground`
- `--color-muted`
- `--color-border`
- `--color-accent`

### Fonts
- `--font-heading`
- `--font-body`

Use the matching utilities downstream: `bg-background`, `bg-surface`, `text-foreground`, `text-muted`, `font-heading`, `font-body`.

### Motion
Optional motion tokens may be emitted when the creative brief requests a motion-led hero or when reference extraction finds strong motion language. Use these exact names only:

- `--duration-instant`
- `--duration-fast`
- `--duration-normal`
- `--duration-slow`
- `--ease-out`
- `--ease-in`
- `--ease-in-out`

Do not introduce token synonyms such as `--motion-fast`, `--transition-ease`, or `--duration-base`.

### Motion Engines

Astro-static supports a small set of motion engines. The team must be aware of all of them and choose deliberately:

| Engine | Use For | Default? |
|---|---|---|
| `css-svg` | Decorative hero loops, simple reveals, hover/focus feedback, lightweight ambience | Yes |
| `astro-view-transitions` | Page-to-page transitions and native navigation polish | Optional |
| `motion-one` | Lightweight Web Animations API timelines, simple element reveals, small scroll-linked effects | Optional |
| `gsap-scrolltrigger` | Pinned scroll stories, scrubbed timelines, horizontal scroll sections, multi-stage SVG/product sequences | Optional, only when justified |
| `lottie` | Asset-driven icon loops, brand illustrations, loading/empty-state animations | Optional, asset-gated |
| `three-webgl` | Premium immersive hero backgrounds, particles, 3D product/brand objects | Strict opt-in |
| `lenis` | Smooth scrolling paired with intentional scroll storytelling | Explicit request only |
| `anime-js` | Small SVG/text micro-timelines when GSAP would be too heavy | Usually skip; prefer Motion One or GSAP |

### Video Backgrounds

Video backgrounds are a distinct visual layer — not a motion engine — handled by PPQ.AI `kling-3.0` text-to-video generation. They run as a separate pipeline phase (3.6) and integrate via a native `<video>` element, not a JS animation library.

| Property | Detail |
|---|---|
| Model | `kling-3.0` on PPQ.AI |
| Format | MP4, served from `public/videos/` |
| Duration | 5s (default) or 10s (premium) |
| Aspect ratio | 16:9 (default), 9:16 (mobile hero) |
| Cost | ~$1.29/5s, ~$2.07/10s per clip |
| Trigger | `motion_direction.video_backgrounds: true` in creative brief |
| Phase | 3.6 (after image generation, before frontend build) |
| Agent | `@astro-static/vid-gen` (called by asset-generator) |
| Frontend | `VideoBackground.astro` — native `<video autoplay muted loop playsinline>` |
| Fallback | Native `<video poster>` still image from Phase 3.5, or gradient. Reduced-motion dims/keeps video visible by default. |
| Player deps | None — native `<video>` only. No Plyr, Video.js, etc. |

When video backgrounds are selected:
- Only generate for sections the brief explicitly flags (hero, CTA, section-bg, footer-bg).
- Pair every video with an existing still poster image from `content_images`; never use the MP4 as its own poster.
- Do not render a separate static `<img>` behind a playing video background; it creates a double-exposure look when opacity changes.
- Limit to 2-3 videos per page for bandwidth.
- Include `negative_prompt: "text, watermark, logo, blurry, shaky, fast cuts, flickering"` in all requests.
- Emphasize slow, subtle motion — backgrounds must not distract from content.
- Image-to-video mode is available when `image_url` is provided; use a dedicated verified i2v model from the PPQ model library, not the default t2v model.

GSAP is a capability of the team, not the default. Use it only when the creative brief or extracted `patterns/motion.yaml` calls for timeline control that CSS cannot express cleanly.

Engine selection rules:
- Prefer `css-svg` unless another engine clearly improves comprehension or brand impact.
- Prefer `astro-view-transitions` for page transitions before adding a JS animation library.
- Prefer `motion-one` for lightweight element-level JS motion that does not need ScrollTrigger.
- Prefer `gsap-scrolltrigger` for pinned/scrubbed/complex scroll timelines.
- Prefer `lottie` only when a real animation asset exists or is intentionally generated.
- Use `three-webgl` only for high-value immersive briefs with static image fallback and mobile/reduced-motion fallback.
- Avoid `lenis` unless the user explicitly asks for smooth scrolling; it can harm accessibility and complicate ScrollTrigger/View Transitions lifecycle.
- Avoid `anime-js` unless the requested effect is a narrow SVG/text micro-timeline and neither Motion One nor GSAP is appropriate.

When GSAP is selected:
- Add `gsap` to `package.json` before importing it. Do not assume the starter template includes it.
- Run GSAP only in browser-side Astro scripts or client islands; never in Astro frontmatter.
- Prefer dynamic plugin imports for `ScrollTrigger` and register plugins at runtime.
- Guard with `window.matchMedia('(prefers-reduced-motion: reduce)')` and preserve a strong static composition.
- Disable pinned/scrubbed ScrollTrigger behavior on mobile below `768px` unless the brief explicitly requires it.
- Animate only `transform` and `opacity`; do not animate layout properties.
- Clean up timelines/triggers on navigation or component teardown with `ctx.revert()` and `ScrollTrigger.getAll().forEach(t => t.kill())` when relevant.

When any optional engine is selected, add its dependency only in the phase that implements it, lazy-load browser code, and document why CSS/SVG was insufficient.

## Pipeline Artifact Contracts

These artifacts are shared contracts across the pipeline. Agents may enrich them only when the shape is explicitly documented.

- `pipeline/00-brief.json` — intake brief: project identity, goals, references, pages, brand constraints
- `pipeline/00-design-tokens/tokens.json` — extracted reference-site design signals
- `pipeline/00-design-tokens/patterns/motion.yaml` — optional extracted motion signals from reference sites
- `pipeline/01-creative-brief.json` — strategy, review flags, and formal content model
- `pipeline/02-font-config.json` — canonical heading/body font configuration
- `pipeline/02-asset-manifest.json` — generated or provided visual assets (includes `content_images` and `video_backgrounds` arrays)
- `pipeline/02-image-shot-list.json` — derived content image generation tasks (Phase 3.5)
- `pipeline/02-video-shot-list.json` — derived video background generation tasks (Phase 3.6, optional)
- `pipeline/vps-connection.json` — SSH, site, and deploy connection details
- `pipeline/00-pipeline-state.json` — canonical phase status file; phase IDs, status values, retry/invalidation semantics, and STATUS token grammar are defined in `references/pipeline-contract.md`

## Agent Contract Discipline

Agents must not silently invent new artifact fields or alternate token names. If an artifact shape changes, update the artifact contract, the downstream validation, and this reference file in the same patch.

## 1. Tailwind v4 CSS-First Configuration

### Setup: NO tailwind.config.js

```css
/* src/styles/theme.css — preferred Tailwind v4 CSS entry point */
@import "tailwindcss";
@plugin "@tailwindcss/typography";

@theme {
  /* Colors — use oklch() for wide gamut */
  --color-primary: oklch(0.72 0.12 260);
  --color-primary-light: oklch(0.85 0.08 260);
  --color-primary-dark: oklch(0.55 0.15 260);
  --color-secondary: oklch(0.65 0.14 160);
  --color-background: oklch(0.99 0 0);
  --color-surface: oklch(1 0 0);
  --color-foreground: oklch(0.15 0 0);
  --color-muted: oklch(0.96 0 0);
  --color-border: oklch(0.90 0 0);
  --color-accent: oklch(0.70 0.18 50);

  /* Fonts */
  --font-heading: "Playfair Display", serif;
  --font-body: "Inter", system-ui, sans-serif;

  /* Font sizes with line-height */
  --text-xs: 0.75rem;
  --text-sm: 0.875rem;
  --text-base: 1rem;
  --text-base--line-height: 1.5;
  --text-lg: 1.125rem;
  --text-xl: 1.25rem;
  --text-2xl: 1.5rem;
  --text-3xl: 2rem;
  --text-4xl: 2.5rem;
  --text-5xl: 3rem;

  /* Spacing (extend default scale) */
  --spacing-section: 6rem;
  --spacing-section-sm: 4rem;

  /* Border radius */
  --radius-sm: 0.25rem;
  --radius-md: 0.5rem;
  --radius-lg: 1rem;
  --radius-full: 9999px;

  /* Shadows */
  --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
  --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
  --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);

  /* Optional motion tokens */
  --duration-instant: 100ms;
  --duration-fast: 200ms;
  --duration-normal: 300ms;
  --duration-slow: 500ms;
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-in: cubic-bezier(0.7, 0, 0.84, 0);
  --ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);
}
```

`src/styles/global.css` is allowed only as a thin entry wrapper if the scaffold
already uses it; it must import both `tailwindcss` and `./theme.css`, and
`BaseLayout.astro` must import that wrapper. Never put the Tailwind entry CSS in
`public/`, because files there bypass Vite and ship raw `@import`/`@theme`.

OKLCH lightness must be a fraction (`0.72`) or a percentage (`72%`). Extracted
tokens often report `9.4` to mean `9.4%`; normalize to `0.094` or `9.4%`, never
`oklch(9.4 ...)`.

### Vite plugin (NOT @astrojs/tailwind)

```js
// astro.config.mjs
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  vite: {
    plugins: [tailwindcss()],
  },
});
```

### Token → Utility Class Mapping

| `@theme` variable | Generated utilities |
|---|---|
| `--color-primary` | `bg-primary`, `text-primary`, `border-primary`, `ring-primary` |
| `--color-background` | `bg-background` |
| `--color-surface` | `bg-surface` |
| `--color-foreground` | `text-foreground` |
| `--color-muted` | `text-muted`, `bg-muted` |
| `--font-heading` | `font-heading` |
| `--font-body` | `font-body` |
| `--text-xl` | `text-xl` |
| `--spacing-section` | `p-section`, `m-section`, `gap-section` |
| `--radius-lg` | `rounded-lg` |
| `--shadow-md` | `shadow-md` |
| `--duration-normal` | `duration-normal` |
| `--ease-out` | `ease-out` |

### ❌ NEVER DO THIS (Tailwind v3 — WRONG)

```js
// ❌ NO tailwind.config.js
// ❌ NO tailwind.config.ts
// ❌ NO tailwind.config.mjs
module.exports = {
  content: ['./src/**/*.{astro,tsx}'],
  darkMode: 'class',
  theme: { extend: { colors: { brand: '#3b82f6' } } },
};
```

```css
/* ❌ NO @tailwind directives */
@tailwind base;
@tailwind components;
@tailwind utilities;

/* ❌ NO @layer utilities/components for custom classes */
@layer utilities { .my-util { ... } }
/* ✅ USE @utility instead */
@utility my-util { ... }

/* ❌ NO theme() function */
color: theme(colors.red.500);
/* ✅ USE var() */
color: var(--color-red-500);

/* ❌ NO bg-[--my-var] */
/* ✅ USE bg-(--my-var) */

/* ❌ NO !bg-red-500 (important prefix) */
/* ✅ USE bg-red-500! (important suffix) */
```

### Renamed Utilities (v3 → v4)

| v3 (OLD) | v4 (CORRECT) |
|---|---|
| `shadow-sm` | `shadow-xs` |
| `shadow` (default) | `shadow-sm` |
| `rounded-sm` | `rounded-xs` |
| `rounded` (default) | `rounded-sm` |
| `blur-sm` | `blur-xs` |
| `outline-none` | `outline-hidden` |
| `ring` (no width) | `ring-3` |
| `flex-grow` | `grow` |
| `bg-opacity-*` | `bg-*/50` (opacity modifier) |
| `!bg-red-500` | `bg-red-500!` |

### Dark Mode

```css
/* Class-based dark mode in v4 */
@custom-variant dark (&:where(.dark, .dark *));

/* Then use CSS variables for switching */
@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
}

:root {
  --background: oklch(1 0 0);
  --foreground: oklch(0.15 0 0);
}

.dark {
  --background: oklch(0.15 0 0);
  --foreground: oklch(0.98 0 0);
}
```

---

## 2. Astro 6 Content Collections

### Config Location CHANGED

```
# ❌ OLD (Astro 4)
src/content/config.ts

# ✅ CURRENT (Astro 6)
src/content.config.ts
```

### Collection Definition

```ts
// src/content.config.ts
import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const blog = defineCollection({
  // REQUIRED: explicit loader (replaces type:'content')
  loader: glob({ pattern: '**/*.{md,mdx}', base: './src/content/blog' }),
  schema: ({ image }) => z.object({
    title: z.string().max(70),
    description: z.string().max(160),
    pubDate: z.coerce.date(),
    heroImage: image().optional(),
    draft: z.boolean().default(false),
  }),
});

export const collections = { blog };
```

### Querying + Rendering

```astro
---
import { getCollection, render } from 'astro:content';

// getCollection unchanged
const posts = await getCollection('blog', ({ data }) => !data.draft);

// BREAKING: entry.slug → entry.id
// BREAKING: entry.render() → render(entry) (standalone import)
const { Content } = await render(entry);
---

{posts.map(post => (
  <a href={`/blog/${post.id}`}>
    <h2>{post.data.title}</h2>
  </a>
))}
```

### Migration Cheat Sheet

| Legacy Astro | Astro 6 |
|---|---|
| `src/content/config.ts` | `src/content.config.ts` |
| `type: 'content'` | `loader: glob({ pattern: '**/*.md', base: './src/content/blog' })` |
| `entry.slug` | `entry.id` |
| `entry.render()` | `import { render } from 'astro:content'; render(entry)` |
| `import { z } from 'astro:content'` | `import { z } from 'astro:content'` + `import { glob } from 'astro/loaders'` |
| `output: 'hybrid'` | `output: 'static'` (merged) |
| `Astro.glob()` | `getCollection()` |

---

## 3. Astro Image Component

```astro
---
import { Image, Picture } from 'astro:assets';
import heroImage from '../assets/hero.png';
---

{/* Local image — auto-optimized (ALWAYS use this) */}
<Image src={heroImage} alt="Hero" width={800} height={600} />

{/* Responsive layout (Astro 6+) */}
<Image src={heroImage} alt="Hero" layout="constrained" width={800} height={600} />

{/* Full-width hero */}
<Image src={heroImage} alt="Hero" layout="full-width" priority />

{/* Multiple formats */}
<Picture src={heroImage} alt="Hero" formats={['avif', 'webp']} />

{/* Remote image (requires domains config) */}
<Image src="https://example.com/img.jpg" alt="Remote" width={600} height={400} />
```

**⚠️ NEVER use `<img>` — always use `<Image>` from `astro:assets`**

---

## 4. Islands / Client Directives

```astro
---
import { Button } from '@/components/ui/button';
import ContactForm from '@/components/ContactForm';
---

{/* Hydrate immediately — critical above-fold */}
<Button client:load>Click</Button>

{/* Hydrate on idle — non-critical interactive */}
<ContactForm client:idle />

{/* Hydrate on idle with timeout */}
<ContactForm client:idle={{ timeout: 500 }} />

{/* Hydrate when scrolled into view */}
<Comments client:visible />

{/* Client-only, no SSR */}
<ThreeScene client:only="react" />
```

**⚠️ Astro `<Image>` CANNOT be used inside React components — pass URL as string prop.**

---

## 5. Astro Content Collections

### Collection config

```ts
// src/content.config.ts
import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const posts = defineCollection({
  loader: glob({ pattern: '**/*.mdx', base: './src/content/posts' }),
  schema: z.object({
    title: z.string(),
    pubDate: z.coerce.date(),
  }),
});

export const collections = { posts };
```

Content is file-backed under `src/content/<collection>/`. Render with `getCollection()` / `getEntry()` from `astro:content`. Public pages stay statically prerendered. TinaCMS adds only editor/admin surfaces: generated `admin/` (at project root, NOT inside `dist/`), `/tina-island/*` on-demand visual-editing routes, and `/api/tina/*` self-hosted GraphQL backend routes.

---

## 6. TinaCMS Static Visual Editing

Generated astro-static sites use TinaCMS as the CMS path:

- `@tinacms/astro` provides React-free visual editing for Astro.
- Keep `output: "static"` for public pages.
- Use `@astrojs/node` standalone adapter for on-demand editor routes.
- `tina/config.ts` mirrors `src/content.config.ts` collection names and fields.
- `tina/config.ts` must use a custom `PasswordAuthProvider` (extending `AbstractAuthProvider` from `tinacms`) — NOT `LocalAuthProvider`. `LocalAuthProvider` only sets a localStorage flag and does not interact with the backend session. The custom provider's `authenticate()` redirects to `/admin/login.html`, `getUser()` probes `/api/tina/auth-check` (GET → 200/401), `getToken()` returns `{ id_token: "" }`, and `logout()` calls `/api/tina/logout` then redirects to login. This ensures the admin SPA redirects unauthenticated users to the login page.
- Every page/section collection must define `ui.router` so document clicks open the live visual editor route, not just the form editor.
- Every Tina data loader must wrap generated client queries in `requestWithMetadata()`.
- Every visible editable DOM node must carry `data-tina-field={tinaField(source, 'fieldName')}`. This is what enables click-to-edit outlines/focus in the preview.
- For maximum Wix-like editing, model pages as ordered blocks/sections so editors can add, remove, and reorder components within the supported design system. Tina does component/block editing, not freeform canvas dragging.
- Use `@tinacms/astro/TinaIsland.astro` to wrap editable regions.
- Keep `export const prerender = false` on `src/pages/tina-island/[name].ts` and `src/pages/api/tina/[...routes].ts`.
- Self-host production saves through `@tinacms/datalayer` with `MemoryLevel` (pure JS, no native bindings — Bun can't load `better-sqlite3`), `FilesystemBridge` for file I/O, and a `gitProvider` that writes through the filesystem bridge. Content is indexed in-memory on server start (~1s for small sites).
- `tinacms build` generates `admin/index.html` and `tina/__generated__/`; do not hand-author generated admin files. **The admin SPA is built locally on the control node (Phase 4.2), NOT on the VPS** — the 2GB VM OOM-kills esbuild. The `admin/` directory is published by build-deployer and served by Caddy from `${SITE_DIR}/admin/`.
- `tina/config.ts` build config MUST be `{ outputFolder: "admin", publicFolder: "." }` so the admin SPA lands at project root, not inside `dist/client/` (which `astro build` wipes).
- TinaCMS collection `path` values MUST match Astro Content Collection `base` paths exactly (e.g., both `src/content/pages`, not singular/plural mismatched).

Latest compatible baseline as of 2026-06-19: `astro@^6.4.8`, `@astrojs/node@^10.1.4`, `@astrojs/mdx@^6.0.3`, `@astrojs/react@^5.0.7`, `@astrojs/sitemap@^3.7.3`, `@tinacms/astro@^0.5.0`, `tinacms@^3.9.3`, `@tinacms/cli@^2.5.1`, `@tinacms/datalayer@^2.0.25`, `memory-level@^1.0.0`, `tailwindcss@^4.3.1`, `@tailwindcss/vite@^4.3.1`.

---

## 7. Complete astro.config.mjs

```js
import { defineConfig } from 'astro/config';
import node from '@astrojs/node';
import react from '@astrojs/react';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import tina from '@tinacms/astro/integration';
import { tinaAdminDevRedirect } from '@tinacms/astro/vite';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  output: 'static',
  adapter: node({ mode: 'standalone' }),
  site: 'https://example.com',
  integrations: [react(), mdx(), tina(), sitemap()],
  vite: {
    plugins: [tailwindcss(), tinaAdminDevRedirect()],
    ssr: { noExternal: ['@tinacms/astro', '@tinacms/bridge'] },
  },
  image: {
    layout: 'constrained',
    responsiveStyles: true,
    domains: ['images.unsplash.com'],
  },
});
```

## 8. Complete tina/config.ts auth baseline

Every generated Tina config must include a custom password auth provider and visual-editor router entries:

```ts
import { AbstractAuthProvider, defineConfig } from 'tinacms';

/**
 * Custom auth provider for self-hosted TinaCMS with password backend.
 * - authenticate(): redirects to /admin/login.html
 * - getUser(): probes /api/tina/auth-check for session cookie validity
 * - getToken(): returns empty token (real auth is HttpOnly cookie, same-origin)
 * - logout(): calls /api/tina/logout, redirects to login
 */
class PasswordAuthProvider extends AbstractAuthProvider {
  async authenticate() {
    if (window.location.pathname !== '/admin/login.html') {
      window.location.href = '/admin/login.html';
    }
    return { access_token: 'LOCAL', id_token: 'LOCAL', refresh_token: 'LOCAL' };
  }
  async getUser() {
    try {
      const res = await fetch('/api/tina/auth-check', { method: 'GET' });
      return res.ok;
    } catch { return false; }
  }
  async getToken() { return { id_token: '' }; }
  async logout() {
    try { await fetch('/api/tina/logout', { method: 'POST' }); } catch {}
    window.location.href = '/admin/login.html';
  }
}

const routeForDocument = (document?: { lang?: string }) => {
  if (document?.lang === 'es') return '/es';
  if (document?.lang === 'en') return '/en';
  return '/';
};

export default defineConfig({
  clientId: null,
  token: null,
  authProvider: new PasswordAuthProvider(),
  contentApiUrlOverride: '/api/tina/gql',
  build: { outputFolder: 'admin', publicFolder: '.' },
  schema: {
    collections: [{
      name: 'sections',
      path: 'src/content/sections',
      ui: { router: ({ document }) => routeForDocument(document) },
      fields: [],
    }],
  },
});
```

Without `authProvider`, Tina falls back to TinaCloud sign-in (`https://app.tina.io/signin?...`). That is a pipeline failure. With `LocalAuthProvider`, the admin SPA thinks the user is always logged in (localStorage flag), but mutations fail with 401 — use `PasswordAuthProvider` instead.

The backend `/api/tina/[...routes].ts` MUST expose three extra routes:
- `login` (POST `{"password":"..."}` → sets `tina_admin_session` HttpOnly cookie)
- `logout` (POST → clears cookie)
- `auth-check` (GET → 200 if session valid, 401 if not)

### TinaCMS Island Route (critical)

`src/pages/tina-island/[name].ts` MUST export a `POST` handler using `experimental_createIslandRoute`. Without this, the bridge's `primeIslands()` fetch returns 404 and the edit panel never populates with form fields.

```typescript
// src/pages/tina-island/[name].ts
import { experimental_createIslandRoute } from "@tinacms/astro/experimental";
import { requestWithMetadata } from "@tinacms/astro";
import Hero from "@/components/sections/Hero.astro";

export const prerender = false;

// The Tina client uses a relative URL (/api/tina/gql) which fails during SSR.
// Construct the query result manually with the correct query string and variables.
// The admin SPA fetches actual data via GraphQL separately — the island just
// needs to register the form with the correct query/variables for matching.
const PAGE_QUERY = `query page($relativePath: String!) {
  page(relativePath: $relativePath) {
    id title description heroTitle heroSubtitle
    featuresHeading featuresSubheading
    features { title description icon }
    ctaHeading ctaBody ctaButtonText ctaButtonNote
    footerText footerNote
  }
}`;

const islands = {
  page: {
    fetch: async (_request: Request, params: URLSearchParams) => {
      const relativePath = params.get("relativePath") || "welcome.md";
      return requestWithMetadata(
        { data: { page: {} }, query: PAGE_QUERY, variables: { relativePath } },
        { priority: "primary" as const }
      );
    },
    component: Hero as any,
    propsFromData: (data: any) => ({
      title: data?.data?.page?.heroTitle ?? "",
      subtitle: data?.data?.page?.heroSubtitle ?? "",
    }),
    wrapper: { tag: "main", className: "flex-1" },
  },
};

export const POST = experimental_createIslandRoute(islands);
```

**Key points:**
- The `fetch` function must return a `requestWithMetadata()` result with the correct `query` and `variables` — the admin SPA uses these to match the form to the document.
- Do NOT use the Tina client's HTTP fetch inside `fetch` — it uses a relative URL that fails during SSR.
- The `component` is any Astro component that will be rendered inside the island wrapper.
- `propsFromData` maps the Tina data to component props.
- The route must be `export const prerender = false` (SSR only).

### Complete Page Example — Static Visual Editing

This is the canonical pattern for a statically-rendered page backed by a TinaCMS content collection. Every generated page MUST follow this structure — hardcoded content without collection queries produces a site where the TinaCMS admin shows "form fields will appear here" and nothing is editable.

```astro
---
// src/pages/index.astro — canonical Tina-editable static page
import { getEntry } from 'astro:content';
import { TinaIsland } from '@tinacms/astro/TinaIsland.astro';
import { requestWithMetadata, tinaField } from '@tinacms/astro';
import { client } from '@/tina/__generated__/client';
import BaseLayout from '@/layouts/BaseLayout.astro';
import Hero from '@/components/sections/Hero.astro';

// 1. Fetch the content collection entry (Astro Content Collections API)
const entry = await getEntry('page', 'welcome');

// 2. Fetch the same document via the Tina client (for visual editing metadata)
const tinaData = await client.requestWithMetadata(
  (c) => c.page({ relativePath: 'welcome.md' }),
  { priority: 'primary' }
);

// 3. Pass tinaField() metadata to components for click-to-edit
const titleField = tinaField(tinaData.data.page, 'title');
const descField = tinaField(tinaData.data.page, 'description');
---

<BaseLayout title={entry.data.title} description={entry.data.description}>
  <TinaIsland
    name="page"
    wrapper={{ tag: 'main', className: 'flex-1' }}
    params={{ relativePath: 'welcome.md' }}
  >
    <Hero
      title={entry.data.title}
      subtitle={entry.data.description}
      titleField={titleField}
      descField={descField}
    />
  </TinaIsland>
</BaseLayout>
```

**Component with `data-tina-field`:**
```astro
---
// src/components/sections/Hero.astro
interface Props {
  title: string;
  subtitle: string;
  titleField?: string;   // from tinaField()
  descField?: string;    // from tinaField()
}
const { title, subtitle, titleField, descField } = Astro.props;
---
<section class="hero">
  <h1 data-tina-field={titleField}>{title}</h1>
  <p data-tina-field={descField}>{subtitle}</p>
</section>
```

**Why both `getEntry()` and `client.requestWithMetadata()`?**
- `getEntry()` provides the content for SSR/static rendering (Astro Content Collections).
- `client.requestWithMetadata()` registers the document with TinaCMS so the admin can map form fields to DOM elements. Without it, the edit panel stays empty.
- The `priority: 'primary'` option tells the admin to open this document's form on page load.

**For `getStaticPaths` pages (dynamic routes):**
```astro
---
// src/pages/[slug].astro
import { getCollection } from 'astro:content';
import { client } from '@/tina/__generated__/client';

export async function getStaticPaths() {
  const pages = await getCollection('page');
  return pages.map((page) => ({
    params: { slug: page.id },
    props: { page },
  }));
}

const { page } = Astro.props;
const tinaData = await client.requestWithMetadata(
  (c) => c.page({ relativePath: `${page.id}.md` }),
  { priority: 'primary' }
);
---
```

**Key rules:**
1. Every page that renders content-collection data MUST call `client.requestWithMetadata()` — this is what makes the admin edit panel populate.
2. Every visible editable text/media node MUST carry `data-tina-field={tinaField(...)}`.
3. Wrap editable regions in `<TinaIsland>` so the admin bridge script loads in the iframe.
4. `requestWithMetadata` is a no-op outside the admin iframe (static builds) — it only activates when the page is viewed inside the TinaCMS admin preview.
5. The `client` import comes from `tina/__generated__/client` (generated by `tinacms build` in Phase 4.2).

---

## 9. Block-Based Page Schemas (Complex Sites)

For any site with more than one page layout, or where editors need to add/remove/reorder sections, model pages as **ordered block lists**. This is the core pattern for Wix-like editing in TinaCMS.

### Tina config (tina/config.ts)

```ts
import { AbstractAuthProvider, defineConfig } from 'tinacms';

class PasswordAuthProvider extends AbstractAuthProvider {
  async authenticate() {
    if (window.location.pathname !== '/admin/login.html') {
      window.location.href = '/admin/login.html';
    }
    return { access_token: 'LOCAL', id_token: 'LOCAL', refresh_token: 'LOCAL' };
  }
  async getUser() {
    try { return (await fetch('/api/tina/auth-check')).ok; } catch { return false; }
  }
  async getToken() { return { id_token: '' }; }
  async logout() {
    try { await fetch('/api/tina/logout', { method: 'POST' }); } catch {}
    window.location.href = '/admin/login.html';
  }
}

// --- Block templates ---
// Each block is a reusable section type. Editors add/reorder/remove these
// on any page. The `templates` array defines which blocks are available.
const heroBlock = {
  name: 'hero',
  label: 'Hero Section',
  ui: { previewSrc: '', defaultItem: { title: 'New Hero', subtitle: '' } },
  fields: [
    { name: 'title', type: 'string', required: true },
    { name: 'subtitle', type: 'string', ui: { component: 'textarea' } },
    { name: 'backgroundImage', type: 'image' },
    { name: 'ctaText', type: 'string' },
    { name: 'ctaHref', type: 'string' },
  ],
};

const featuresBlock = {
  name: 'features',
  label: 'Features Grid',
  fields: [
    { name: 'heading', type: 'string' },
    { name: 'subheading', type: 'string' },
    {
      name: 'items',
      type: 'object',
      list: true,
      ui: { itemProps: (item: { title?: string }) => ({ label: item?.title }) },
      fields: [
        { name: 'title', type: 'string', required: true },
        { name: 'description', type: 'string', ui: { component: 'textarea' } },
        { name: 'icon', type: 'string' },
      ],
    },
  ],
};

const galleryBlock = {
  name: 'gallery',
  label: 'Gallery',
  fields: [
    { name: 'heading', type: 'string' },
    {
      name: 'images',
      type: 'object',
      list: true,
      fields: [
        { name: 'image', type: 'image', required: true },
        { name: 'caption', type: 'string' },
      ],
    },
  ],
};

const ctaBlock = {
  name: 'cta',
  label: 'Call to Action',
  fields: [
    { name: 'heading', type: 'string', required: true },
    { name: 'body', type: 'string', ui: { component: 'textarea' } },
    { name: 'buttonText', type: 'string' },
    { name: 'buttonHref', type: 'string' },
  ],
};

const testimonialsBlock = {
  name: 'testimonials',
  label: 'Testimonials',
  fields: [
    { name: 'heading', type: 'string' },
    {
      name: 'items',
      type: 'object',
      list: true,
      fields: [
        { name: 'quote', type: 'string', ui: { component: 'textarea' }, required: true },
        { name: 'author', type: 'string', required: true },
        { name: 'role', type: 'string' },
        { name: 'avatar', type: 'image' },
      ],
    },
  ],
};

const contentBlock = {
  name: 'content',
  label: 'Rich Text',
  fields: [
    { name: 'heading', type: 'string' },
    { name: 'body', type: 'rich-text' },
  ],
};

export const blockTemplates = [
  heroBlock,
  featuresBlock,
  galleryBlock,
  testimonialsBlock,
  ctaBlock,
  contentBlock,
];

export default defineConfig({
  clientId: null,
  token: null,
  authProvider: new PasswordAuthProvider(),
  contentApiUrlOverride: '/api/tina/gql',
  build: { outputFolder: 'admin', publicFolder: '.' },
  schema: {
    collections: [
      // --- Pages: block-based, one entry per route ---
      {
        name: 'page',
        label: 'Pages',
        path: 'src/content/pages',
        ui: { router: ({ document }) => `/${document._sys.filename === 'index' ? '' : document._sys.filename}` },
        fields: [
          { name: 'title', type: 'string', required: true },
          { name: 'description', type: 'string' },
          {
            name: 'blocks',
            label: 'Page Sections',
            type: 'object',
            list: true,
            templates: blockTemplates,
          },
        ],
      },
      // --- Blog posts: separate collection with its own schema ---
      {
        name: 'post',
        label: 'Blog Posts',
        path: 'src/content/posts',
        ui: { router: ({ document }) => `/blog/${document._sys.filename}` },
        fields: [
          { name: 'title', type: 'string', required: true },
          { name: 'description', type: 'string', required: true },
          { name: 'publishDate', type: 'datetime', required: true },
          { name: 'author', type: 'string' },
          { name: 'image', type: 'image' },
          { name: 'body', type: 'rich-text' },
          { name: 'draft', type: 'boolean' },
        ],
      },
      // --- Team members: referenced by pages or independent ---
      {
        name: 'member',
        label: 'Team Members',
        path: 'src/content/members',
        ui: { router: ({ document }) => `/team/${document._sys.filename}` },
        fields: [
          { name: 'name', type: 'string', required: true },
          { name: 'role', type: 'string' },
          { name: 'bio', type: 'string', ui: { component: 'textarea' } },
          { name: 'photo', type: 'image' },
          { name: 'email', type: 'string' },
        ],
      },
      // --- Global site settings: singleton, not routed ---
      {
        name: 'settings',
        label: 'Site Settings',
        path: 'src/content/settings',
        format: 'json',
        ui: { router: () => '/' },
        fields: [
          { name: 'siteName', type: 'string', required: true },
          { name: 'tagline', type: 'string' },
          {
            name: 'nav',
            type: 'object',
            list: true,
            label: 'Navigation Menu',
            fields: [
              { name: 'label', type: 'string', required: true },
              { name: 'href', type: 'string', required: true },
            ],
          },
          {
            name: 'footerLinks',
            type: 'object',
            list: true,
            fields: [
              { name: 'label', type: 'string', required: true },
              { name: 'href', type: 'string', required: true },
            ],
          },
          { name: 'socialTwitter', type: 'string' },
          { name: 'socialInstagram', type: 'string' },
          { name: 'socialLinkedIn', type: 'string' },
          { name: 'contactEmail', type: 'string' },
          { name: 'copyrightText', type: 'string' },
        ],
      },
    ],
  },
});
```

### Astro content schema (src/content.config.ts)

Mirror the Tina schema in Zod. Use discriminated unions for block types:

```ts
import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

// Block discriminant union — matches tina/config.ts templates
const blockSchema = z.discriminatedUnion('_template', [
  z.object({
    _template: z.literal('hero'),
    title: z.string(),
    subtitle: z.string().optional(),
    backgroundImage: z.string().optional(),
    ctaText: z.string().optional(),
    ctaHref: z.string().optional(),
  }),
  z.object({
    _template: z.literal('features'),
    heading: z.string().optional(),
    subheading: z.string().optional(),
    items: z.array(z.object({
      title: z.string(),
      description: z.string().optional(),
      icon: z.string().optional(),
    })).optional(),
  }),
  z.object({
    _template: z.literal('gallery'),
    heading: z.string().optional(),
    images: z.array(z.object({
      image: z.string(),
      caption: z.string().optional(),
    })).optional(),
  }),
  z.object({
    _template: z.literal('testimonials'),
    heading: z.string().optional(),
    items: z.array(z.object({
      quote: z.string(),
      author: z.string(),
      role: z.string().optional(),
      avatar: z.string().optional(),
    })).optional(),
  }),
  z.object({
    _template: z.literal('cta'),
    heading: z.string(),
    body: z.string().optional(),
    buttonText: z.string().optional(),
    buttonHref: z.string().optional(),
  }),
  z.object({
    _template: z.literal('content'),
    heading: z.string().optional(),
    body: z.any().optional(),
  }),
]);

const pages = defineCollection({
  loader: glob({ pattern: '**/*.{md,mdx,json}', base: './src/content/pages' }),
  schema: z.object({
    title: z.string(),
    description: z.string().optional(),
    blocks: z.array(blockSchema).optional(),
  }),
});

const posts = defineCollection({
  loader: glob({ pattern: '**/*.{md,mdx}', base: './src/content/posts' }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    publishDate: z.coerce.date(),
    author: z.string().optional(),
    image: z.string().optional(),
    body: z.any().optional(),
    draft: z.boolean().optional(),
  }),
});

const members = defineCollection({
  loader: glob({ pattern: '**/*.{md,mdx}', base: './src/content/members' }),
  schema: z.object({
    name: z.string(),
    role: z.string().optional(),
    bio: z.string().optional(),
    photo: z.string().optional(),
    email: z.string().optional(),
  }),
});

const settings = defineCollection({
  loader: glob({ pattern: '*.json', base: './src/content/settings' }),
  schema: z.object({
    siteName: z.string(),
    tagline: z.string().optional(),
    nav: z.array(z.object({ label: z.string(), href: z.string() })).optional(),
    footerLinks: z.array(z.object({ label: z.string(), href: z.string() })).optional(),
    socialTwitter: z.string().optional(),
    socialInstagram: z.string().optional(),
    socialLinkedIn: z.string().optional(),
    contactEmail: z.string().optional(),
    copyrightText: z.string().optional(),
  }),
});

export const collections = { pages, posts, members, settings };
```

### Block renderer component (src/components/BlockRenderer.astro)

A single component that maps block `_template` to the right section component:

```astro
---
import Hero from './sections/Hero.astro';
import Features from './sections/Features.astro';
import Gallery from './sections/Gallery.astro';
import Testimonials from './sections/Testimonials.astro';
import CTA from './sections/CTA.astro';
import RichText from './sections/RichText.astro';

interface Props {
  block: { _template: string; [key: string]: any };
  tinaField?: (source: any, field?: string, index?: number) => string;
  index?: number;
}

const { block, tinaField: tf, index = 0 } = Astro.props;
const blockField = tf ? (field?: string) => tf(block, field, index) : undefined;
---

{block._template === 'hero' && (
  <Hero
    title={block.title}
    subtitle={block.subtitle}
    backgroundImage={block.backgroundImage}
    ctaText={block.ctaText}
    ctaHref={block.ctaHref}
    titleField={blockField?.('title')}
    subtitleField={blockField?.('subtitle')}
  />
)}
{block._template === 'features' && (
  <Features
    heading={block.heading}
    subheading={block.subheading}
    features={block.items ?? []}
    headingField={blockField?.('heading')}
    featuresField={blockField?.('items')}
  />
)}
{block._template === 'gallery' && (
  <Gallery heading={block.heading} images={block.images ?? []} />
)}
{block._template === 'testimonials' && (
  <Testimonials heading={block.heading} items={block.items ?? []} />
)}
{block._template === 'cta' && (
  <CTA heading={block.heading} body={block.body} buttonText={block.buttonText} buttonHref={block.buttonHref} />
)}
{block._template === 'content' && (
  <RichText heading={block.heading} body={block.body} />
)}
```

### Dynamic page route (src/pages/[...slug].astro)

One route handles ALL pages. Each page entry's `blocks` array is rendered by BlockRenderer:

```astro
---
import { getCollection } from 'astro:content';
import TinaIsland from '@tinacms/astro/TinaIsland.astro';
import { requestWithMetadata, tinaField } from '@tinacms/astro';
import { client } from '../../tina/__generated__/client';
import BaseLayout from '../layouts/BaseLayout.astro';
import BlockRenderer from '../components/BlockRenderer.astro';
import { getEntry } from 'astro:content';

export async function getStaticPaths() {
  const pages = await getCollection('pages');
  return pages.map((page) => ({
    params: { slug: page.id === 'index' ? undefined : page.id },
    props: { page },
  }));
}

const { page } = Astro.props;
const data = page.data;

// Fetch the same document via Tina client for visual editing metadata
const tinaResult = await requestWithMetadata(
  (client as any).queries.page({ relativePath: `${page.id}.md` }),
  { priority: 'primary' }
);
const tinaPage = (tinaResult.data as any)?.page;
const blocksField = tinaPage ? tinaField(tinaPage, 'blocks') : undefined;
---

<BaseLayout title={data.title} description={data.description}>
  <TinaIsland
    name="page"
    wrapper={{ tag: 'main', className: 'flex-1' }}
    params={{ relativePath: `${page.id}.md` }}
  >
    {data.blocks?.map((block, i) => (
      <BlockRenderer block={block} tinaField={tinaField} index={i} />
    ))}
  </TinaIsland>
</BaseLayout>
```

### Settings: loading global config

```astro
---
// In BaseLayout.astro or any component that needs site settings
import { getEntry } from 'astro:content';
const settings = await getEntry('settings', 'site');
const nav = settings?.data.nav ?? [];
const footerLinks = settings?.data.footerLinks ?? [];
---
```

### Reference fields (linking between collections)

TinaCMS supports `type: 'reference'` to link entries across collections:

```ts
// In tina/config.ts, inside a block or collection fields:
{
  name: 'featuredMember',
  type: 'reference',
  collections: ['member'],  // points to the member collection
  label: 'Featured Team Member',
}
```

For a list of references:
```ts
{
  name: 'team',
  type: 'reference',
  collections: ['member'],
  list: true,
  label: 'Team Members',
}
```

In Astro, resolve the reference by fetching the referenced entry:
```astro
---
const memberEntry = await getEntry('members', data.featuredMember);
---
```

### Content entry format for block-based pages

A page entry (`src/content/pages/index.md`) with blocks looks like:

```yaml
---
title: "Home"
description: "Welcome to our site"
blocks:
  - _template: hero
    title: "Building Beautiful Sites"
    subtitle: "From concept to launch, we handle every detail."
    ctaText: "Get Started"
    ctaHref: "/contact"
  - _template: features
    heading: "What We Do"
    items:
      - title: "Design"
        description: "Pixel-perfect, brand-driven design."
        icon: "palette"
      - title: "Development"
        description: "Fast, accessible, SEO-optimized code."
        icon: "code"
  - _template: cta
    heading: "Ready to start?"
    body: "Let's build something great together."
    buttonText: "Contact Us"
    buttonHref: "/contact"
---
```

### Key rules for complex sites

1. **Every collection has `ui.router`** — so clicking a document in the admin opens the right page in the preview iframe.
2. **Block `_template` field** — TinaCMS auto-adds `_template` to discriminated block objects. The Astro Zod schema must use `z.discriminatedUnion('_template', [...])` to match.
3. **Settings collection uses `format: 'json'`** — singleton-style config doesn't need markdown body. Use `*.json` and `glob({ pattern: '*.json' })` in the loader.
4. **One `[...slug].astro` route** handles all pages — no need for separate `about.astro`, `contact.astro` files. Each page is a content entry.
5. **Reference fields** create foreign-key-like links between collections. Always provide `collections: ['name']` to constrain which collections can be referenced.
6. **Image fields** in blocks use `type: 'image'` in Tina and `z.string()` in Zod. The value is a file path relative to `publicFolder`.
7. **Rich-text fields** use `type: 'rich-text'` in Tina and `z.any()` in Zod (the value is a rich-text AST object).

---

## 10. Quick Anti-Pattern Checklist

Before submitting code, verify NONE of these exist:

- [ ] `tailwind.config.js` / `.ts` / `.mjs` → DELETE, use `@theme {}`
- [ ] `@tailwind base/components/utilities` → REPLACE with `@import "tailwindcss"`
- [ ] `theme.extend` → REPLACE with `@theme {}` block
- [ ] `@layer utilities { }` → REPLACE with `@utility name { }`
- [ ] `theme(colors.x)` → REPLACE with `var(--color-x)`
- [ ] `bg-[--var]` → REPLACE with `bg-(--var)`
- [ ] `!bg-red-500` → REPLACE with `bg-red-500!`
- [ ] `entry.slug` → REPLACE with `entry.id`
- [ ] `entry.render()` → REPLACE with `render(entry)` (import from `astro:content`)
- [ ] `src/content/config.ts` → MOVE to `src/content.config.ts`
- [ ] `type: 'content'` → REPLACE with `loader: glob({...})`
- [ ] `<img>` → REPLACE with `<Image>` from `astro:assets`
- [ ] `@astrojs/tailwind` → REPLACE with `@tailwindcss/vite`
- [ ] `output: 'hybrid'` → REPLACE with `output: 'static'`
- [ ] Tina config without `authProvider: new PasswordAuthProvider()` → ADD it; never use `LocalAuthProvider` or allow TinaCloud sign-in fallback
- [ ] Tina collections without `ui.router` → ADD route mapping so content opens the visual editor
- [ ] Tina-rendered text/media without `data-tina-field` → ADD `tinaField()` markers to visible editable HTML elements
- [ ] Tina data queries not wrapped in `requestWithMetadata()` → WRAP them or visual preview cannot map forms/fields
- [ ] `<img>` without `data-tina-field` or `data-static-media` → ADD Tina image field wiring or mark decorative
- [ ] `contentImages[...]` without a Tina image override prop → ADD `bgImage`/`image` prop that resolves Tina-first
- [ ] `.astro` frontmatter closed with `?>` or `</script>` → REPLACE with `---`
- [ ] `oklch(9.4 0.01 140)` style lightness → REPLACE with `oklch(9.4% 0.01 140)` or `oklch(0.094 0.01 140)`
- [ ] `<video poster="/videos/foo.mp4">` → REPLACE poster with still `.webp`/`.png`/`.jpg`
- [ ] `<img class="video-bg__poster">` under a video background → DELETE and use native `<video poster>` only
- [ ] `.video-bg__video { display: none }` under reduced-motion → DIM or freeze, do not hide requested clips by default
- [ ] `shadow-sm` used as "small shadow" → USE `shadow-xs` (v4 renamed)
- [ ] `rounded-sm` used as "small radius" → USE `rounded-xs` (v4 renamed)
- [ ] `outline-none` → USE `outline-hidden`

---

## 10. Tina-Editable Images — Canonical Pattern

Every image surface in a Tina-enabled astro-static site MUST be admin-editable. The pipeline validator (`validate-pipeline.py`) enforces this at build time. The pattern reconciles the Phase 3.5 asset-generator (optimized local images with LQIP) with Tina media editing.

### The "Tina Override with Asset-Gen Fallback" Pattern

```
Tina image field (editor upload)  ──wins──>  <img src={tinaPath} data-tina-field={...} />
        │
        └── empty? ──fallback──>  contentImages['asset-gen-id'].src
```

Editors get a media picker in the Tina admin. If they never upload a replacement, the pipeline-generated default renders. Both paths produce a working site.

### Schema (tina/config.ts + content.config.ts)

Every visual collection (sections, cards, gallery, team, products, hero) MUST include image fields:

```typescript
// tina/config.ts
fields: [
  { name: 'title', type: 'string', required: true },
  { name: 'image', label: 'Image', type: 'image' },
  { name: 'imageAlt', label: 'Image Alt Text', type: 'string' },
]

// src/content.config.ts — mirror with Astro image() helper
schema: ({ image }) => z.object({
  title: z.string(),
  image: image().optional(),
  imageAlt: z.string().optional(),
})
```

Tina `type: 'image'` fields render a media picker in the admin that uploads to the Git-backed media store. The value is a string path (e.g. `/media/hero-v2.webp`).

### Component Pattern

```astro
---
import { contentImages } from '@/lib/content-images';

interface Props {
  bgImage?: string;                    // Tina-uploaded override
  fields?: { bgImage?: string };       // tinaField() metadata for click-to-edit
}
const { bgImage, fields = {} } = Astro.props;

// Resolve: Tina field wins, asset-gen default is the fallback
const fallback = contentImages['hero-background'];
const src = bgImage ?? fallback?.src.src;
---

<section class="relative overflow-hidden">
  {src && (
    <div data-tina-field={fields.bgImage}>
      <img src={src} alt="" data-tina-field={fields.bgImage} class="absolute inset-0 w-full h-full object-cover" />
    </div>
  )}
  <div class="absolute inset-0 bg-gradient-to-b from-background/80 to-background/90 z-[1]"></div>
  <div class="relative z-[2]">
    <!-- content -->
  </div>
</section>
```

### Island Data Wiring

Pass the Tina image value AND its field metadata through `propsFromData`:

```typescript
// src/lib/tina/islands.ts
hero: {
  fetch: fetchHome,
  component: Hero,
  wrapper,
  propsFromData: (data, params) => {
    const hero = sectionById(home(data), 'hero');
    return {
      bgImage: hero?.image,                      // string path from Tina
      fields: {
        bgImage: editableField(hero, 'image'),   // tinaField() for click-to-edit
      },
    };
  },
},
```

### Static Page Wiring

On statically-rendered pages (TinaIsland children), pass the section's `image` field:

```astro
---
const heroSection = section('hero')?.data;
---
<TinaIsland name="hero" wrapper={islands.hero.wrapper} params={{ lang }}>
  <Hero bgImage={heroSection?.image} />
</TinaIsland>
```

### Per-Card Background Images

For repeating components (service cards, gallery items, product cards), each item carries its own image field:

```astro
---
interface Card {
  title: string;
  body: string;
  bgImage?: string;               // per-card Tina image
  fields?: { bgImage?: string };
}
---
{cards.map((card) => (
  <div class="relative overflow-hidden">
    {card.bgImage && (
      <img src={card.bgImage} alt="" data-tina-field={card.fields?.bgImage}
           class="absolute inset-0 w-full h-full object-cover opacity-25" />
    )}
    <!-- card content -->
  </div>
))}
```

### Exempting Decorative Images

Icons, avatar fallbacks, and purely decorative SVGs that should never be editor-replaced use `data-static-media`:

```astro
<img src="/icon-arrow.svg" alt="" data-static-media />
```

The validator exempts these from the `data-tina-field` requirement.

### What the Validator Catches

| Pattern | Error message |
|---------|---------------|
| `<img>` without `data-tina-field` or `data-static-media` | `img element missing data-tina-field; wire it to a Tina image field or mark data-static-media if decorative` |
| `contentImages[...]` without Tina override prop | `contentImages[] usage found without Tina image field override; add an optional image/bgImage prop, resolve Tina-first (tinaField ?? contentImages[...]), and render data-tina-field on the <img>` |
| Hardcoded `/images/...` or `/videos/...` paths | `hardcoded media path must be Tina/content/manifest-backed` |

### Media Store Configuration

Tina media uploads commit files to the Git repository via the Gitea provider. The default upload path is `public/media/`. Ensure `.gitignore` does NOT exclude `public/media/`. Note: `build.publicFolder` in `tina/config.ts` is set to `"."` (project root) so the admin SPA lands at `./admin/` — this is NOT the media upload folder. Media uploads go to `public/media/` regardless of `publicFolder` (Tina's media path is configured via the media store, not `build.publicFolder`).
