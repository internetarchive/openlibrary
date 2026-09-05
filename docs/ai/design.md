# Design

Design patterns and conventions for all Open Library UI — templates, Vue components, Lit web components, and plain HTML/CSS alike.

## Scope

These rules apply to every line you write or modify, in any file. Much of `static/css` predates them, so:

- **Don't match the surrounding legacy convention when it conflicts with a rule here.** The file's existing `--grey` or ungated `:hover` is not a precedent.
- **Fix the declaration you touch, not the file.** Changing a hover background? Move that value to a semantic token. Rewriting the whole rule block? Gate it to hover-capable pointers too. Leave untouched neighbors alone — whole-file migrations are their own PR.
- **`legacy.css` and `legacy-tools.css` are delete-only.** Move rules out; never edit them toward compliance in place.

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

The bottom of `colors.css` re-points every legacy token name (`--grey`, `--beige`, `--primary-blue`, …) at the ramps so old consumers keep working. Never use these in new code; when you modify a declaration that uses one, migrate that declaration to a semantic token (see [Scope](#scope)).

### Which tier to use

Always use semantic tokens. If one doesn't exist for your use case, create it in the appropriate token file rather than using a primitive or hardcoded value.

### Token files

| File | Contents |
|---|---|
| `static/css/tokens/colors.css` | Color primitives, semantic color tokens, deprecated legacy aliases |
| `static/css/tokens/spacing.css` | Spacing scale |
| `static/css/tokens/border-radius.css` | Border radius primitives and semantic tokens |
| `static/css/tokens/font-families.css` | Font families and sizes |
| `static/css/tokens/press.css` | Press-feedback scale tiers (`--press-scale-compact` / `--press-scale` / `--press-scale-wide`) |
| `static/css/tokens/borders.css` | Border and shadow tokens, plus the modal overlay scrim (`--overlay-backdrop-color` / `--overlay-backdrop-blur`) |

### Tokens in Shadow DOM

CSS custom properties inherit through the shadow boundary, so design tokens work directly inside Lit component `static styles` blocks without any extra wiring.

## Overlays

### Blur follows modality, not viewport width

An overlay dims and blurs the page behind it **if and only if it is modal** — it
traps focus, inerts the background, and the page behind genuinely cannot be
reached. The blur is not decoration; it is how "the page is inert" gets
rendered. An overlay whose page stays interactive gets no scrim and no blur: its
own border and shadow do the separating, and dimming a page you can still click
is a lie.

| Surface | Modal? | Scrim + blur |
|---|---|---|
| `ol-dialog` | yes — native `showModal()` | yes |
| `ol-drawer` | yes — `showModal()` + focus trap | yes |
| `ol-popover` mobile tray | yes — `aria-modal`, scrim, scroll lock | yes |
| `ol-popover` desktop panel | no — Tab leaves, page stays live | no |
| `ol-tooltip` | no | no |

The one pair that looks like a viewport rule is `ol-popover`, whose tray blurs
and whose desktop panel doesn't. **That is not a mobile rule.** The 767px check
in `OlPopover` picks the *shape*; modality follows from the shape; blur follows
modality. Never key a blur off a breakpoint — the first modal surface on desktop
(or non-modal panel on mobile) breaks it.

Every modal surface reads the same two tokens, `--overlay-backdrop-color` and
`--overlay-backdrop-blur`. Don't hand-roll a per-component scrim value: a
hamburger drawer that dims harder than a confirm dialog reads as the more
serious interruption, which is backwards. `ol-drawer` carried its own `0.5`
black for exactly that reason until the three were unified.

**The blur is what lets the dim stay light.** 32% black over a page of book
covers still leaves a legible, busy field competing with the panel — you can
read the titles through it. The blur destroys that detail so nothing behind
reads as content any more, which is what buys the dim the freedom to stay at
0.32 and keep the page feeling present rather than switched off. Drop the blur
and you inevitably compensate with more black.

**Declare the blur constant; animate only opacity.** Never transition a blur
radius — the layer is viewport-sized and the drawer's enter runs 400ms. Setting
`backdrop-filter` on the scrim and transitioning the scrim's `opacity` fades the
blur in with it for free, since an element's opacity carries its own
`backdrop-filter`. This is also what makes the drawer's swipe-to-dismiss work:
it drives `opacity` directly from drag progress and the blur tracks it.

Two consequences worth knowing before adding a scrim to something new:

- **`backdrop-filter` establishes a containing block**, so a blurred scrim is a
  positioning trap for any `position: fixed` descendant. Our scrims have no
  descendants (the drawer's panel is a *sibling* of its scrim, not a child) —
  keep it that way, and see [Overlays and the top
  layer](web-components.md#overlays-and-the-top-layer) for the full trap.
- **Nested modals compound**, since each scrim blurs whatever is painted below
  it. A popover tray opened from inside the drawer stacks two layers: ~0.54
  effective dim and ~4.2px of blur, with the drawer panel itself pushed back
  along with the page. Measured, that reads as intentional depth rather than a
  bug — but it is the reason the shared token is light. Two 0.5 scrims would
  not survive the same stacking.

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
  background: var(--color-surface);
  transition: background-color 0.15s ease;
}
.button:hover {
  background: var(--color-control-hover);
}

/* Good - hover is instant; only the press-scale animates */
.button {
  background: var(--color-surface);
  transition: transform 0.08s;
}
.button:hover {
  background: var(--color-control-hover);
}
.button:active {
  transform: scale(var(--press-scale));
}
```

### Hover moves the whole control, and its direction depends on the fill

Two rules keep hover feedback coherent across our controls (`ol-button`,
`ol-toggle`, `ol-chip`, and anything built on them):

**1. The border moves with the fill.** When a control darkens (or lightens) its
fill on hover, its border must shift by the same amount. A fill that darkens
inside a static outline reads as two disconnected pieces; moving both together
reads as one solid shape. Match the magnitude — our light controls step the fill
one rung down the ramp (`--color-surface` → `--color-control-hover`) and the border
tracks it (`--color-border-subtle` → `--color-border-muted`), each a 6–9% drop in
lightness. `OLButton.js` is the reference implementation; keep these examples in
lockstep with it.

```css
/* Bad - fill darkens inside a frozen border */
.button:hover {
  background: var(--color-control-hover);
}

/* Good - border tracks the fill by the same amount */
.button:hover {
  background: var(--color-control-hover);
  border-color: var(--color-border-muted);
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
  border-color: var(--color-border-muted);
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
| Make a control feel responsive | Scale it on `:active` only if it is a self-contained control: it has its own visible boundary (fill, border, or shadow) separating it from its neighbors, and pressing it completes an action. Buttons, chips, icon buttons, pagination items, and carousel arrows qualify. Menu rows and drawer items press with a fill, no squeeze: their edges touch their siblings, so a shrinking row reads as the panel moving rather than the row being pressed. Surfaces (popover, dialog, drawer, toast) are never pressed; their `scale(0.95)` is an enter animation, not press feedback. |
| Press-scale looks exaggerated or invisible | Pick the tier by width, not importance: `--press-scale-compact` (0.92) for square icon controls, `--press-scale` (0.97) for text controls, `--press-scale-wide` (0.985) for stretched controls like `full-width` buttons and the search bar. Each is tuned so the edge travels ~1.5px; 3% is sub-pixel at 32px and a 15px lurch at 500px. See `static/css/tokens/press.css`. |
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
  background: var(--color-surface);
}

@media (hover: hover) and (pointer: fine) {
  .chip:hover {
    background: var(--color-control-hover);
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
