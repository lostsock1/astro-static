# Impeccable Design Tokens Reference

> Reference document — not an agent. Loaded by name from `asset-generator.md`. Lives under `references/` so it doesn't appear in the agent picker.

**For asset-generator.** This file governs font selection, palette construction, and theme token output. Follow it alongside `reference-stack.md`.

---

## §1 Typography

### Font Selection

**Avoid the invisible defaults**: Inter, Roboto, Open Sans, Lato, Montserrat. They make every project look generic.

**Pick the font from the brief, not from a category preset.** The most common AI typography failure is reaching for the same "tasteful" font for every editorial brief, the same "modern" font for every tech brief. Those reflexes produce monoculture across projects. The right font is one whose physical character matches *this specific* brand, audience, and moment.

A working selection process:

1. Read the brief once. Write down three concrete words for the brand voice. Not "modern" or "elegant" — try "warm and mechanical and opinionated" or "calm and clinical and careful" or "fast and dense and unimpressed."
2. Imagine the font as a physical object the brand could ship: a typewriter ribbon, a hand-lettered shop sign, a 1970s mainframe terminal manual, a fabric label, a museum exhibit caption. Whichever object fits the three words is pointing at the right *kind* of typeface.
3. Browse Google Fonts with that physical object in mind. **Reject the first thing that "looks designy."** That's your trained reflex. Keep looking.
4. Avoid defaults from previous projects. If you find yourself reaching for the same display font, pick something else.

**Anti-reflexes:**
- A technical/utilitarian brief does NOT need a serif "for warmth." Tech tools should look like tech tools.
- An editorial/premium brief does NOT need the same expressive serif everyone is using. Premium can be Swiss-modern, neo-grotesque, monospace, or a quiet humanist sans.
- A children's product does NOT need a rounded display font. Kids' books use real type.
- A "modern" brief does NOT need a geometric sans.

### Pairing Principles

**You often don't need a second font.** One well-chosen family in multiple weights creates cleaner hierarchy than two competing typefaces. Only add a second font when you need genuine contrast (e.g., display headlines + body serif).

When pairing, contrast on multiple axes:
- Serif + Sans (structure contrast)
- Geometric + Humanist (personality contrast)
- Condensed display + Wide body (proportion contrast)

**Never pair fonts that are similar but not identical** (e.g., two geometric sans-serifs). They create visual tension without clear hierarchy.

### Modular Scale

Too many font sizes that are too close together creates muddy hierarchy. Use fewer sizes with more contrast. A 5-size system covers most needs:

| Role | Typical Ratio | Use Case |
|------|---------------|----------|
| xs | 0.75rem | Captions, legal |
| sm | 0.875rem | Secondary UI, metadata |
| base | 1rem | Body text |
| lg | 1.25–1.5rem | Subheadings, lead text |
| xl+ | 2–4rem | Headlines, hero text |

Popular ratios: 1.25 (major third), 1.333 (perfect fourth), 1.5 (perfect fifth). Pick one and commit.

### Font Config Output Rules

When writing `pipeline/02-font-config.json`:
- Use Google Fonts only
- Include realistic weight ranges (not just [400])
- Provide the exact `google_url` with `family=` parameter
- Prefer variable fonts when available (single file, multiple weights)
- Maximum 2 font families per project

### Theme CSS Typography Tokens

In `src/styles/theme.css`, define within `@theme {}`:

```css
--font-heading: "Font Name", serif;
--font-body: "Font Name", sans-serif;
```

Also add a modular size scale and line-heights as CSS custom properties so frontend-builder can use them.

---

## §2 Color & Contrast

### Color Space: OKLCH

**Stop using HSL.** Use OKLCH. It's perceptually uniform — equal steps in lightness *look* equal, unlike HSL where 50% lightness in yellow looks bright while 50% in blue looks dark.

Format: `oklch(lightness chroma hue)` where lightness is 0–100%, chroma is ~0–0.4, hue is 0–360.

**Reduce chroma as you approach white or black** — high chroma at extreme lightness looks garish.

### Tinted Neutrals

**Pure gray is dead.** Add a tiny chroma value (0.005–0.015) to all neutrals, hued toward the brand color. The chroma is small enough not to read as "tinted" consciously, but creates subconscious cohesion.

The hue you tint toward must come from THIS project's brand color — not from a "warm = friendly, cool = tech" formula.

**Avoid** always tinting toward warm orange or cool blue. Those are the two laziest defaults.

### Palette Structure

A complete system needs:

| Role | Purpose | Output |
|------|---------|--------|
| **Primary** | Brand, CTAs, key actions | 1 color, 3–5 shades |
| **Neutral** | Text, backgrounds, borders | 9–11 shade scale |
| **Semantic** | Success, error, warning, info | 4 colors, 2–3 shades each |
| **Surface** | Cards, modals, overlays | 2–3 elevation levels |

**Skip secondary/tertiary unless needed.** Most sites work with one accent color.

### The 60-30-10 Rule

- **60%**: Neutral backgrounds, white space, base surfaces
- **30%**: Secondary — text, borders, inactive states
- **10%**: Accent — CTAs, highlights, focus states

The common mistake: using the accent color everywhere because it's "the brand color." Accent colors work *because* they're rare.

### WCAG Contrast Requirements

| Content Type | AA Minimum | AAA Target |
|--------------|------------|------------|
| Body text | 4.5:1 | 7:1 |
| Large text (18px+ or 14px bold) | 3:1 | 4.5:1 |
| UI components, icons | 3:1 | 4.5:1 |

**Placeholder text still needs 4.5:1.** That light gray placeholder fails WCAG.

### Dangerous Combinations

- Light gray text on white (#1 accessibility fail)
- Gray text on colored backgrounds — use a darker shade of the bg color instead
- Red on green (or vice versa) — 8% of men can't distinguish
- Yellow on white (almost always fails)
- Thin light text on images (unpredictable contrast)

### Never Use Pure Black

`#000` doesn't exist in nature. Even chroma 0.005–0.01 is enough to feel natural.

### Dark Mode Palette

Dark mode is NOT inverted light mode:
- Never pure black — use dark gray (oklch 12–18%)
- Depth comes from surface lightness, not shadow
- Build a 3-step surface scale where higher = lighter (15%/20%/25%)
- Same hue and chroma as brand, only vary lightness
- Reduce font weight slightly (350 → 400 becomes 300 → 350)

### Alpha Is A Design Smell

Heavy use of transparency usually means an incomplete palette. Define explicit colors instead. Exception: focus rings and interactive states.

### Theme CSS Color Tokens

In `src/styles/theme.css`, define within `@theme {}`:

```css
--color-primary: oklch(...);
--color-primary-light: oklch(...);
--color-primary-dark: oklch(...);
--color-background: oklch(...);
--color-surface: oklch(...);
--color-foreground: oklch(...);
--color-muted: oklch(...);
--color-border: oklch(...);
--color-accent: oklch(...);
```

All values in `oklch()`. No hex, no rgb, no hsl. Neutrals must carry tinted chroma.

---

## §3 Anti-Pattern Checklist

Before outputting `src/styles/theme.css` and `pipeline/02-font-config.json`, verify:

- [ ] Font is not Inter, Roboto, Open Sans, Lato, or Montserrat (unless brief explicitly requests)
- [ ] At most 2 font families
- [ ] Font pairing has genuine contrast (not two similar sans-serifs)
- [ ] All colors in `oklch()` — zero hex, rgb, or hsl values
- [ ] Neutrals have tinted chroma (not `oklch(X% 0 Y)`)
- [ ] No pure black (`#000` or `oklch(0% 0 0)`) in palette
- [ ] Primary text on background meets WCAG AA 4.5:1
- [ ] Muted text on background meets WCAG AA 3:1
- [ ] No more than one primary accent color (skip secondary unless brief demands)
- [ ] Dark mode surfaces defined (if brief includes dark mode)
