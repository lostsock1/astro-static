# Impeccable UI Implementation Reference

> Reference document — not an agent. Loaded by name from `frontend-builder.md`. Lives under `references/` so it doesn't appear in the agent picker.

**For frontend-builder.** This file governs layout, motion, interaction, responsiveness, and content writing. Follow it alongside `reference-stack.md`.

---

## §1 Spatial Design

### Spacing System

**Use 4pt base**: 4, 8, 12, 16, 24, 32, 48, 64, 96px. The 8pt system is too coarse — you'll frequently need 12px.

Name tokens semantically (`--space-sm`, `--space-lg`), not by value. Use `gap` instead of margins for sibling spacing — eliminates margin collapse.

### Grid Systems

Use `repeat(auto-fit, minmax(280px, 1fr))` for responsive grids without breakpoints. For complex layouts, use named grid areas and redefine at breakpoints.

### Visual Hierarchy

**The Squint Test**: If you blur your eyes, can you still identify the most important element? Second most important? Clear groupings? If everything looks the same weight blurred, you have a hierarchy problem.

Combine multiple dimensions — don't rely on size alone:

| Tool | Strong Hierarchy | Weak Hierarchy |
|------|------------------|----------------|
| Size | 3:1 ratio or more | <2:1 ratio |
| Weight | Bold vs Regular | Medium vs Regular |
| Color | High contrast | Similar tones |
| Position | Top/left (primary) | Bottom/right |
| Space | Surrounded by white space | Crowded |

**The best hierarchy uses 2–3 dimensions at once.**

### Cards

Cards are overused. Use them only when content is truly distinct and actionable, items need visual comparison in a grid, or content needs clear interaction boundaries. **Never nest cards inside cards** — use spacing, typography, and subtle dividers.

### Container Queries

Viewport queries are for page layouts. **Container queries are for components:**

```css
.card-container {
  container-type: inline-size;
}
@container (min-width: 400px) {
  .card { grid-template-columns: 120px 1fr; }
}
```

### Optical Adjustments

Text at `margin-left: 0` looks indented due to letterform whitespace — use negative margin (`-0.05em`) to optically align. Play icons shift right, arrows shift toward their direction.

### Touch Targets

Buttons need 44px minimum touch targets. Use padding or pseudo-elements to expand tap area beyond visual size.

### Depth & Elevation

Semantic z-index scale: `dropdown (100) → sticky (200) → modal-backdrop (300) → modal (400) → toast (500) → tooltip (600)`. Shadows should be subtle — if you can clearly see it, it's too strong.

---

## §2 Motion Design

### Duration: The 100/300/500 Rule

| Duration | Use Case | Examples |
|----------|----------|----------|
| 100–150ms | Instant feedback | Button press, toggle, color change |
| 200–300ms | State changes | Menu open, tooltip, hover |
| 300–500ms | Layout changes | Accordion, modal, drawer |
| 500–800ms | Entrance animations | Page load, hero reveals |

**Exit animations are faster than entrances** — use ~75% of enter duration.

### Easing Curves

**Don't use `ease`.** Use:

| Curve | Use For | CSS |
|-------|---------|-----|
| ease-out | Elements entering | `cubic-bezier(0.16, 1, 0.3, 1)` |
| ease-in | Elements leaving | `cubic-bezier(0.7, 0, 0.84, 0)` |
| ease-in-out | State toggles | `cubic-bezier(0.65, 0, 0.35, 1)` |

For micro-interactions, use exponential curves:
```css
--ease-out-quart: cubic-bezier(0.25, 1, 0.5, 1);
--ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
```

**Avoid bounce and elastic curves.** They feel tacky. Real objects decelerate smoothly.

### The Only Two Properties You Should Animate

**transform** and **opacity** only. Everything else causes layout recalculation. For height animations, use `grid-template-rows: 0fr → 1fr`.

### Staggered Animations

```css
animation-delay: calc(var(--i, 0) * 50ms);
```
Cap total stagger time — 10 items at 50ms = 500ms max.

### Reduced Motion (Mandatory)

Vestibular disorders affect ~35% of adults over 40. **This is not optional:**

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

Preserve functional animations (progress bars, loading spinners) — just without spatial movement.

### Motion Tokens

Define in theme or global CSS:
```css
--duration-instant: 100ms;
--duration-fast: 200ms;
--duration-normal: 300ms;
--duration-slow: 500ms;
--ease-out: cubic-bezier(0.16, 1, 0.3, 1);
--ease-in: cubic-bezier(0.7, 0, 0.84, 0);
```

### Decorative Loop Motion / Motion Hero Anatomy

Use a motion-led hero only when the creative brief explicitly requests it through `motion_direction.use_motion_hero: true` or when reference-site motion is a clear differentiator. Motion must clarify the brand idea; never add generic floating blobs just because animation is possible.

For a polished CSS/SVG-first motion hero:
- **Composition:** full-bleed or contained 16:9 visual field beside/behind the hero copy; keep headline, CTA, and navigation readable above all decorative layers.
- **Layers:** 3-5 decorative layers maximum (gradient wash, masked SVG path, product/brand motif, small particles, foreground highlight). More layers usually look noisy and hurt performance.
- **Loop duration:** decorative loops should be slow (`8s-24s`) and subtle. UI feedback still follows the 100/300/500 rule.
- **Properties:** animate only `transform` and `opacity`. For SVG, animate transforms on groups rather than path geometry.
- **Amplitude:** translate ≤ 24px, rotate ≤ 6deg, scale within `0.96-1.04` unless the concept demands stronger motion.
- **Phase offsets:** stagger loop delays so layers do not pulse in sync.
- **Accessibility:** under `prefers-reduced-motion: reduce`, freeze decorative movement and keep a strong static composition.
- **Performance:** avoid canvas/video unless required by the brief. Prefer CSS gradients, inline SVG, masks, and pseudo-elements.

Do not output standalone Open Design artifacts, `DESIGN.md`, or isolated `index.html` compositions. In astro-static, motion work becomes Astro components and CSS under `src/`.

### GSAP / ScrollTrigger Capability

The astro-static team can use GSAP, but only for motion that benefits from a real timeline engine: pinned scroll narratives, scrubbed timelines, horizontal scroll hijacks, multi-stage SVG/product reveals, or reference-site motion that is clearly ScrollTrigger-like. Do not use GSAP for simple hover states, decorative drifting blobs, or one-off fade-ins.

When GSAP is used:
- Keep content semantic and readable without JavaScript.
- Add the dependency intentionally; do not rely on the base starter.
- Run in client-side scripts/islands only, never server frontmatter.
- Respect reduced motion before creating timelines.
- Use `gsap.context()` where practical and clean up timelines/triggers before Astro route swaps or island teardown.
- Disable pinning and heavy scrubbed timelines on coarse pointers or screens below `768px` unless the brief explicitly asks for them.
- Follow the same property rule as CSS motion: `transform` and `opacity` only.

### Optional Motion Engine Fit

Use the lightest engine that meets the need:

| Engine | Use | Avoid When |
|---|---|---|
| Astro View Transitions | Page transitions, shared-navigation polish | Component-level animation is enough |
| Motion One | Lightweight Web Animations API reveals, small timelines, non-React interactions | You need pinning, scrubbed scroll, or complex sequencing |
| Lottie / dotLottie | Asset-driven icon loops, small brand illustrations, loading/empty states | There is no real animation asset or no pause/reduced-motion policy |
| Three.js / WebGL | Premium immersive hero visuals, particles, 3D product objects | The site is content-heavy, conservative, or performance-sensitive |
| Lenis | Explicitly requested smooth-scroll experiences | Default sites; accessibility-sensitive sites; unknown scroll requirements |
| Anime.js | Narrow SVG/text micro-timelines | GSAP or Motion One is already present |

Never stack motion libraries in one component. A section gets one motion engine plus CSS states. All optional engines need reduced-motion behavior, mobile policy, and lazy loading.

---

## §3 Interaction Design

### The Eight Interactive States

Every interactive element needs these designed:

| State | Visual Treatment |
|-------|------------------|
| Default | Base styling |
| Hover | Subtle lift, color shift (pointer only, not touch) |
| Focus | Visible ring via `:focus-visible` |
| Active | Pressed in, darker |
| Disabled | Reduced opacity, no pointer |
| Loading | Spinner, skeleton |
| Error | Red border, icon, message |
| Success | Green check, confirmation |

**Hover ≠ Focus.** Keyboard users never see hover states.

### Focus Rings

**Never `outline: none` without replacement.** Use `:focus-visible`:

```css
button:focus { outline: none; }
button:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}
```

Ring design: high contrast (3:1 min), 2–3px thick, offset from element.

### Forms

- Placeholders aren't labels — always use visible `<label>` elements
- Validate on blur, not every keystroke (exception: password strength)
- Place errors below fields with `aria-describedby`

### Loading States

**Skeleton screens > spinners** — they preview content shape and feel faster.

### Modals

Use native `<dialog>` with `.showModal()` for automatic focus trap and Escape-to-close. When modal is open, mark background with `inert`:

```html
<main inert><!-- can't be focused --></main>
<dialog open><!-- focus stays here --></dialog>
```

### Popover API

For tooltips and dropdowns:
```html
<button popovertarget="menu">Open menu</button>
<div id="menu" popover><!-- light-dismiss, top layer --></div>
```

### Dropdown Positioning

**Never** `position: absolute` inside `overflow: hidden` — the dropdown gets clipped. Use `position: fixed`, the Popover API (top layer), or CSS Anchor Positioning instead.

### Destructive Actions

**Undo > Confirm dialogs.** Users click through confirmations mindlessly. Remove from UI immediately, show undo toast, actually delete after expiry.

### Keyboard Navigation

For tab groups and menus, use roving tabindex — one item has `tabindex="0"`, others `tabindex="-1"`, arrow keys move between them. Tab key moves to next component.

Provide skip links for keyboard users to jump past navigation.

---

## §4 Responsive Design

### Mobile-First

Start with base styles for mobile, use `min-width` queries to layer complexity. Never desktop-first.

### Breakpoints

Content-driven — let content tell you where to break. The frontend-builder template uses 640/768/1024/1280px. Use `clamp()` for fluid values without breakpoints.

### Detect Input Method, Not Just Screen Size

```css
@media (pointer: fine) { /* mouse/trackpad — compact targets */ }
@media (pointer: coarse) { /* touch — larger targets */ }
@media (hover: hover) { /* safe to use hover effects */ }
@media (hover: none) { /* no hover — use active instead */ }
```

**Don't rely on hover for functionality.** Touch users can't hover.

### Safe Areas

```css
.footer {
  padding-bottom: max(1rem, env(safe-area-inset-bottom));
}
```

Ensure viewport meta tag includes `viewport-fit=cover`.

### Responsive Images

Use Astro's `<Image>` component for automatic `srcset` and `sizes`. For art direction (different crops per viewport), use `<picture>`.

### Layout Adaptation

- **Nav**: hamburger + drawer → horizontal compact → full with labels
- **Tables**: transform to cards on mobile with `data-label` attributes
- **Progressive disclosure**: use `<details>/<summary>` for collapsible content

---

## §5 UX Writing

### Button Labels

**Never use "OK", "Submit", or "Yes/No".** Use specific verb + object:

| Bad | Good | Why |
|-----|------|-----|
| OK | Save changes | Says what will happen |
| Submit | Create account | Outcome-focused |
| Yes | Delete message | Confirms the action |
| Click here | Download PDF | Describes the destination |

For destructive actions, name the destruction and show the count: "Delete 5 items" not "Delete selected."

### Error Messages

Answer three questions: (1) What happened? (2) Why? (3) How to fix it?

"Email address isn't valid. Please include an @ symbol." — not "Invalid input."

**Never blame the user.** "Please enter a date in MM/DD/YYYY format" — not "You entered an invalid date."

### Empty States

Empty states are onboarding moments: (1) Acknowledge briefly, (2) Explain the value, (3) Provide a clear action.

"No projects yet. Create your first one to get started." — not just "No items."

### Voice vs Tone

**Voice** is the brand's personality — consistent everywhere. **Tone** adapts to the moment:

| Moment | Tone |
|--------|------|
| Success | Celebratory, brief |
| Error | Empathetic, helpful |
| Loading | Reassuring |
| Destructive confirm | Serious, clear |

**Never use humor for errors.** Users are frustrated. Be helpful, not cute.

### Accessibility Writing

- Link text must have standalone meaning — "View pricing plans" not "Click here"
- Alt text describes information, not the image — "Revenue increased 40% in Q4" not "Chart"
- Icon buttons need `aria-label`
- Decorative images get `alt=""`

### Consistency

Pick one term and stick with it across the entire site:
- Delete OR Remove (pick one)
- Settings OR Preferences (pick one)
- Sign in OR Log in (pick one)

Build a terminology glossary in the brief and enforce it.

### Avoid Redundant Copy

If the heading explains it, the intro is redundant. If the button is clear, don't explain it again. Say it once, say it well.

---

## §6 Implementation Checklist

Before syncing to VPS, verify:

- [ ] Spacing uses 4pt multiples (4, 8, 12, 16, 24, 32, 48, 64, 96)
- [ ] No cards nested inside cards
- [ ] Hierarchy uses 2–3 dimensions (size + weight + space)
- [ ] All animations use `transform` or `opacity` only
- [ ] Motion hero, if present, is an Astro component with CSS/SVG-first decorative motion — not a standalone artifact
- [ ] No `ease` — use explicit cubic-bezier curves
- [ ] `prefers-reduced-motion` respected
- [ ] All interactive elements have hover AND focus states
- [ ] Focus rings via `:focus-visible`, never bare `outline: none`
- [ ] No `position: absolute` dropdowns inside `overflow: hidden`
- [ ] Touch targets ≥ 44px
- [ ] Mobile-first CSS (`min-width` media queries)
- [ ] `clamp()` used for fluid typography where appropriate
- [ ] No button says "Submit", "OK", or "Click here"
- [ ] Empty states have guidance + action
- [ ] Terminology is consistent across all pages
- [ ] `alt` text on all images — descriptive for content, `""` for decorative
