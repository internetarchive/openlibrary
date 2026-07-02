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

- **Warm neutrals** `--neutral-50…900` — one "paper to ink" ramp (hue 40–45) that replaces the legacy grey and beige families. 50 is the page canvas, 800 is primary text ink.
- **Blue** `--blue-50…800` — the single brand accent. 500/600 match the legacy `--primary-blue`/`--link-blue` exactly.
- **Status ramps** `--red-*`, `--green-*`, `--amber-*` — muted tints (50/100/200) for backgrounds and borders, plus text-safe foreground steps (500/600/700).

```css
--neutral-800: hsl(40, 13%, 21%);
--blue-500: hsl(202, 96%, 37%);
--space-16: 16px;
--border-radius-lg: 8px;
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

The main semantic groups in `colors.css`: text (`--color-text`, `-secondary`, `-muted`, `-inverse`), surfaces (`--color-background`, `--color-surface`, `-raised`, `-sunken`, `-header`), links (`--color-link`, `-hover`, `-visited`), primary action (`--color-primary`, `-hover`, `-active`, `-subtle`, `--color-on-primary`), borders (`--color-border`, `-subtle`, `-hovered`, `-focused`, `-error`, `--color-focus-ring`), and status (`--color-{success,error,warning}-{fg,bg,border}`).

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

### Practical Tips

| Scenario | Solution |
| --- | --- |
| Make buttons feel responsive | Add `transform: scale(0.97)` on `:active` |
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
