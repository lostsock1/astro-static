# Astro 5 + Tailwind v4 + shadcn/ui — Pipeline Reference

> Reference document — not an agent. Loaded by name from `asset-generator.md`, `frontend-builder.md`, and `design-extractor.md`. Lives under `references/` so it doesn't appear in the agent picker.
>
> **Purpose:** Single source of truth for the astro-static pipeline agents.
> Last verified: 2026-04-18 against official docs.

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
| Fallback | Poster image from Phase 3.5, or gradient. Reduced-motion hides video. |
| Player deps | None — native `<video>` only. No Plyr, Video.js, etc. |

When video backgrounds are selected:
- Only generate for sections the brief explicitly flags (hero, CTA, section-bg, footer-bg).
- Pair every video with an existing poster image from `content_images`.
- Limit to 2-3 videos per page for bandwidth.
- Include `negative_prompt: "text, watermark, logo, blurry, shaky, fast cuts, flickering"` in all requests.
- Emphasize slow, subtle motion — backgrounds must not distract from content.
- Image-to-video mode is available when `image_url` is provided (uses same kling-3.0 model).

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

## Agent Contract Discipline

Agents must not silently invent new artifact fields or alternate token names. If an artifact shape changes, update the artifact contract, the downstream validation, and this reference file in the same patch.

## 1. Tailwind v4 CSS-First Configuration

### Setup: NO tailwind.config.js

```css
/* src/styles/global.css — the ONLY CSS entry point */
@import "tailwindcss";

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

## 2. Astro 5 Content Collections

### Config Location CHANGED

```
# ❌ OLD (Astro 4)
src/content/config.ts

# ✅ NEW (Astro 5)
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

| Astro 4 | Astro 5 |
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

{/* Responsive layout (Astro 5.10+) */}
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

Content is file-backed under `src/content/<collection>/`. Render with `getCollection()` / `getEntry()` from `astro:content`. Keep this project static-only: do not add CMS admin routes, server-only integrations, or runtime content APIs.

---

## 6. Complete astro.config.mjs

```js
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import mdx from '@astrojs/mdx';
import markdoc from '@astrojs/markdoc';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  output: 'static',
  site: 'https://example.com',
  integrations: [react(), mdx(), markdoc()],
  vite: { plugins: [tailwindcss()] },
  image: {
    layout: 'constrained',
    responsiveStyles: true,
    domains: ['images.unsplash.com'],
  },
});
```

---

## 7. Quick Anti-Pattern Checklist

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
- [ ] `shadow-sm` used as "small shadow" → USE `shadow-xs` (v4 renamed)
- [ ] `rounded-sm` used as "small radius" → USE `rounded-xs` (v4 renamed)
- [ ] `outline-none` → USE `outline-hidden`
