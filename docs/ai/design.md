# Design

Design patterns and conventions for all Open Library UI — templates, Vue components, Lit web components, and plain HTML/CSS alike. These guidelines apply whenever you're writing or modifying frontend code.

## Typography

### Preventing Layout Shift

**Font weight:** Never change font weight on hover or selected states. This causes layout shift.

```css
/* Bad - causes layout shift */
.tab:hover {
  font-weight: 600;
}
.tab.selected {
  font-weight: 600;
}

/* Good - consistent weight */
.tab {
  font-weight: 500;
}
.tab.selected {
  color: var(--color-primary);
}
```

**Tabular numbers:** Use `font-variant-numeric: tabular-nums` for numbers that change dynamically (counters, prices, timers).

```css
.counter {
  font-variant-numeric: tabular-nums;
}
```

### Text Wrapping

Use `text-wrap: balance` on headings for better line breaks.

```css
h1,
h2,
h3 {
  text-wrap: balance;
}
```

## Visual Design

### Scroll Margins

Set `scroll-margin-top` for scrollable elements to ensure proper space above elements when scrolling to anchors:

```css
[id] {
  scroll-margin-top: 80px; /* Height of sticky header */
}
```

## Design Tokens

Open Library uses a two-tier token system defined as CSS custom properties in `static/css/tokens/`.

### Tier 1: Primitives

Raw values with no semantic meaning — the base palette. `colors.css` defines five ramps:

- **Warm neutrals** `--neutral-50…900` — one "paper to ink" ramp (hue 41–48) that replaces the legacy grey and beige families. 50 is the lightest tint (raised warm surfaces), 800 is primary text ink. The page canvas is not on the ramp: it's `--paper`, a one-off a shade deeper and warmer than 200, so the full-bleed background stays close to the beige on openlibrary.org today.
- **Blue** `--blue-50…800` — the single brand accent. 500 is the brand blue, 600 the link blue.
- **Status ramps** `--red-*`, `--green-*`, `--amber-*` — muted tints (50/100/200) for backgrounds and borders, plus text-safe foreground steps (500/600/700).

```css
--neutral-800: hsl(41, 14%, 21%);
--blue-500: hsl(210, 82%, 40%);
--spacing-lg: 1rem;
--border-radius-lg: 9px;
```

You should rarely use primitives directly in component or template styles.

### Tier 2: Semantic Tokens

Semantic tokens reference primitives and describe purpose, not appearance.

```css
--color-text: var(--neutral-800);
--color-link: var(--blue-600);
--color-surface: var(--white);
--border-radius-card: var(--border-radius-lg);
```

The main semantic groups in `colors.css`: text (`--color-text`, `-heading`, `-secondary`, `-muted`, `-inverse`), icons (`--color-icon-muted`), surfaces (`--color-background`, `--color-surface`, `-raised`, `-sunken`, `-header`), links (`--color-link`, `-hover`, `-visited`), primary action (`--color-primary`, `-hover`, `-active`, `-subtle`, `--color-on-primary`), borders (`--color-border`, `-muted`, `-subtle`, `-hover`, `-focused`, `-error`, `--color-focus-ring`), and status (`--color-{info,success,error,warning}-{fg,bg,border}`).

Two of these are a **decorative tier** and carry that caveat in `colors.css`: `--color-border-muted` (1.6:1 on white) and `--color-icon-muted` (2.5:1). In new code they're for dividers and inert chrome — anything a user has to *read*, or that is the sole marker of a control's edge, needs `--color-border` or darker.

You will find existing control borders on `--color-border-muted`. They were migrated at their original weight so the token rollout stayed a no-op; that they sit below 3:1 is a pre-existing gap to fix deliberately, not a precedent to copy.

Hover has two tokens, split by mechanism rather than by surface. `--color-hover-overlay` is a translucent overlay for flat interactive rows (popover items, menu items, list rows) — it composes over whatever surface it lands on, so a row on `--color-surface-sunken` or `-header` still darkens instead of matching its own background. `--color-control-hover` is an opaque fill for raised controls, and must stay opaque: alpha fed to `--control-surface` inverts the specular highlight.

This indirection enables visual redesigns, dark mode, and brand refreshes by changing token values in one place. Semantic tokens are the dark-mode seam: a future theme re-points them at different primitives.

`tests/unit/js/token-contrast.test.js` asserts the WCAG AA contrast matrix over these tokens (text ≥ 4.5:1 on its surfaces, non-text UI ≥ 3:1) — palette changes that break accessibility fail `npm test`.

### Deprecated aliases

The bottom of `colors.css` re-points every legacy token name (`--grey`, `--beige`, `--primary-blue`, …) at the ramps so old consumers keep working. Never use these in new code; when touching a file that uses one, migrate it to a semantic token.

### Which tier to use

Always use semantic tokens. If one doesn't exist for your use case, create it in the appropriate token file rather than using a primitive or hardcoded value.

### Token files

| File | Contents |
|---|---|
| `static/css/tokens/colors.css` | Color primitives, semantic color tokens, deprecated legacy aliases |
| `static/css/tokens/spacing.css` | Spacing scale |
| `static/css/tokens/border-radius.css` | Border radius primitives and semantic tokens |
| `static/css/tokens/font-families.css` | Font families and sizes |

### Tokens in Shadow DOM

CSS custom properties inherit through the shadow boundary, so design tokens work directly inside Lit component `static styles` blocks without any extra wiring.

## Animations

### Hover state changes are instant

Don't transition the background-color, color, or border-color of a hover
state. A hover should snap in the instant the pointer arrives — easing it in
makes the control feel laggy and unresponsive, and on a fast pointer sweep the
fade is just visual noise. Transitions belong on press feedback (`transform`
on `:active`), enter/exit animations, and loading states — not on `:hover`
color changes.

```css
/* Bad - hover background eases in, feels laggy */
.button {
  background: var(--white);
  transition: background-color 0.15s ease;
}
.button:hover {
  background: var(--lightest-grey);
}

/* Good - hover is instant; only the press-scale animates */
.button {
  background: var(--white);
  transition: transform 0.08s;
}
.button:hover {
  background: var(--lightest-grey);
}
.button:active {
  transform: scale(0.97);
}
```

### Hover moves the whole control, and its direction depends on the fill

Two rules keep hover feedback coherent across our controls (`ol-button`,
`ol-toggle`, `ol-chip`, and anything built on them):

**1. The border moves with the fill.** When a control darkens (or lightens) its
fill on hover, its border must shift by the same amount. A fill that darkens
inside a static outline reads as two disconnected pieces; moving both together
reads as one solid shape. Match the magnitude — our light controls drop the fill
~7% in lightness (`--white` → `--lightest-grey`) and the border tracks it (`--color-border-subtle`
→ `--light-grey`, both ~7%).

```css
/* Bad - fill darkens inside a frozen border */
.button:hover {
  background: var(--lightest-grey);
}

/* Good - border tracks the fill by the same amount */
.button:hover {
  background: var(--lightest-grey);
  border-color: var(--light-grey);
}
```

**2. Light fills darken; saturated/dark fills lighten.** Hover should always
shift the fill toward *more* activation, and the visible direction of that shift
depends on where the fill starts. A near-white control (secondary button,
unchecked toggle, neutral chip) darkens. A solid, saturated fill (primary and
destructive buttons, the selected chip) instead *lightens* — darkening an
already-dark fill barely registers, and lightening reads as the control coming
forward. For a saturated fill, `filter: brightness(1.1)` is the cleanest tool:
it carries the fill, the border, and any inset specular highlight together in
one declaration, so there's nothing to keep in sync.

```css
/* Light fill: darken fill + border on hover */
:host([variant="secondary"]) .control:hover {
  background-color: var(--color-control-hover);
  border-color: var(--light-grey);
}

/* Saturated fill: lighten the whole thing at once */
:host([variant="primary"]) .control:hover,
:host([variant="destructive"]) .control:hover {
  filter: brightness(1.1);
}
```

Both still obey "hover is instant" above — no transition on the color/filter
change; only the `:active` press-scale animates.

### Practical Tips

| Scenario | Solution |
| --- | --- |
| Make buttons feel responsive | Add `transform: scale(0.97)` on `:active` |
| Icon next to a button label | Put the SVG in `ol-button`'s `icon-start` / `icon-end` slot — it's sized to the button (14/16/18px by size) and gapped automatically; don't set width/height/margin on the SVG or add a `::part(label)` gap |
| Hover on a solid/colored button | Lighten with `filter: brightness(1.1)`, not a darker color — see [above](#hover-moves-the-whole-control-and-its-direction-depends-on-the-fill) |
| Hover border looks detached from fill | Shift `border-color` by the same amount as the fill |
| Element appears from nowhere | Start from `scale(0.95)`, not `scale(0)` |
| Shaky/jittery animations | Add `will-change: transform` |
| Hover causes flicker | Animate child element, not parent |
| Popover scales from wrong point | Set `transform-origin` to trigger location |
| Sequential tooltips feel slow | Skip delay/animation after first tooltip |
| Hover triggers on mobile | Use `@media (hover: hover) and (pointer: fine)` — see [Mobile](#mobile) |

## Mobile

### Prevent iOS Safari auto-zoom on input focus

iOS Safari auto-zooms the viewport when the user focuses any text-entry control with `font-size < 16px`. The page stays zoomed after the control blurs, which is jarring and breaks fixed-position layout. Fix: set `font-size: 16px` on every focusable text-entry control on mobile — this covers `<input>`, `<textarea>`, `<select>`, and `contenteditable` elements, not just `<input>`.

```css
.search-modal__input {
  /* Visually 14px-feeling input, but 16px to dodge iOS auto-zoom. */
  font-size: 16px;
}
```

If you need the control to look smaller, scale it visually rather than dropping below 16px (e.g., reduce padding, use `transform: scale()` only on non-text affordances).

This fix relies on the page declaring `<meta name="viewport" content="width=device-width, initial-scale=1">` (set site-wide in the base layout). Do **not** suppress auto-zoom with `maximum-scale=1` or `user-scalable=no` on the viewport meta — that disables pinch-zoom entirely, which is an accessibility failure for low-vision users. The 16px rule is the correct fix.

### Gate hover styles to hover-capable pointers

Touch devices fire `:hover` on tap and the style sticks until the next tap elsewhere. That makes plain `:hover` rules feel broken on phones — buttons stay highlighted, tooltips linger.

Wrap hover styles in `@media (hover: hover) and (pointer: fine)` so they only apply on devices with a precise hover-capable pointer (mouse, trackpad):

```css
.chip {
  background: var(--white);
}

@media (hover: hover) and (pointer: fine) {
  .chip:hover {
    background: var(--lightest-grey);
  }
}
```

Use the same query to decide which affordance to render in markup. For example, the search modal shows a tappable close button on touch devices and an "ESC" pill on hover-capable pointers (where the keyboard is the expected dismiss path). Pick one or the other rather than showing both.

```css
.dismiss-touch { display: block; }
.dismiss-keyboard { display: none; }

@media (hover: hover) and (pointer: fine) {
  .dismiss-touch { display: none; }
  .dismiss-keyboard { display: block; }
}
```
