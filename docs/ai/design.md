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

**Tabular numbers:** Use `font-variant-numeric: tabular-nums` for numbers that change dynamically (counters, prices, timers), so the text doesn't shift width as digits change.

```css
.counter {
  font-variant-numeric: tabular-nums;
}
```

## Visual Design

### Scroll Margins

Set `scroll-margin-top` on anchor targets so a sticky header doesn't cover them when scrolling to a fragment. Derive the offset from the header's height token, never a bare pixel value:

```css
/* page-design.css — the design page's sticky masthead */
[id] {
  scroll-margin-top: calc(var(--ds-masthead-height) + var(--spacing-inset-md));
}
```

### Breakpoints

Custom properties can't be used in `@media`, so breakpoints are hard-coded px values with the token name in a comment. The scale is in `tokens/breakpoints.css`: 375 (`mobile-s`), 425 (`mobile-m`), 450 (`mobile`), 768 (`tablet`), 960 (`desktop`).

- Write `min-width: N` for at-or-above and `max-width: N-1` for below — `767px` is the correct mirror of `768px`. Never `N+1`: `min-width: 769px` leaves a one-pixel hole at exactly 768 where neither rule applies.
- Don't introduce values off the scale. `480px`, `600px`, `800px`, `769px` and `961px` exist in the codebase; they're the migration list, not precedent.

```css
/* --width-breakpoint-tablet */
@media (min-width: 768px) { … }
@media (max-width: 767px) { … }
```

## Components

Before writing new markup or CSS, check whether an existing component already does the job. Every row is documented with live examples and a generated API table at `/developers/design`; the *Avoid* column is the same text the design page shows, sourced from `COMPONENTS` in `openlibrary/plugins/openlibrary/design.py` — change it there and here together.

| Component | Tag | Use it for | Avoid |
|---|---|---|---|
| Button | `ol-button` | One-shot actions, including form submit/reset | For a state that stays on or off, use Toggle. For a filter that can be removed, use Chip. |
| Toggle | `ol-toggle` | A setting that is on or off | For picking one of several options use Segmented Control. |
| Segmented Control | `ol-segmented-control` | Pick one of a few options, shown side by side | More than about four options belong in a Select Popover. |
| Chip | `ol-chip` | A selectable or removable filter | A chip is a removable or selectable filter. A one-shot action is a Button. |
| Chip Group | `ol-chip-group` | Wrapping layout for a set of Chips | Only for laying out Chips; don't wrap other controls in it. |
| Pagination | `ol-pagination` | Navigate numbered pages of results | For an open-ended feed, load more in place instead of paging. |
| Tooltip | `ol-tooltip` | A short hint on hover or focus | Never put essential information or interactive content in a tooltip. |
| Popover | `ol-popover` | An anchored panel with custom content | Use the composed variants (Select, Options, Menu) before a bare Popover; reserve it for custom panel content. |
| Select Popover | `ol-select-popover` | Pick several values from a list | For a single choice use Options Popover; for four or fewer choices use Segmented Control. |
| Options Popover | `ol-options-popover` | Pick one value from a list | Multiple selections belong in a Select Popover. |
| Menu Popover | `ol-menu-popover` | Pick one action from a list | A choice that is read or submitted later is a value, not an action — use Options Popover. |
| Dialog | `ol-dialog` | A centered modal interruption | For a task with its own scrolling content, use Drawer. For a passive message, use Toast or Banner. |
| Drawer | `ol-drawer` | A modal panel that slides in from a viewport edge | A centered interruption is a Dialog. A panel anchored to its trigger is a Popover. |
| Toast | `ol-toast` | Transient confirmation of something that just happened (`ol-toast-region` hosts them) | Anything the reader must act on belongs in a Dialog or a Banner. |
| Banner | `ol-banner` | A persistent page-level announcement | Page-level and persistent. For confirmation of an action the user just took, use Toast. |
| Message | `.ol-message` | An inline notice next to the thing it describes (CSS classes, no tag) | Inline, next to the thing it describes. For page-level notices use Banner. |
| Scorecard | `ol-scorecard` | The book-quality score (`ol-score-gauge` is its internal gauge) | Purpose-built for the book-quality score; don't repurpose it as a generic gauge. |
| Carousel | `ol-carousel` | A horizontal, page-based row of items | For fewer than about six items, lay them out in a row instead. |
| Read More | `ol-read-more` | Collapse long prose behind an expander | Only for prose. Don't hide controls or lists behind it. |
| Markdown Editor | `ol-markdown-editor` | WYSIWYG editing of a Markdown body | For a plain text field use <textarea>; this is for Markdown bodies only. |
| Icon | `ol-icon` | One icon from the Open Library set | Only for icons from the set; don't use it to embed arbitrary SVG. |

`ol-otp-login` is also registered but is a single login flow, not a reusable component. For when to build something new versus enhance a template, see [When to Build a Component](web-components.md#when-to-build-a-component).

## Icons

One set — sources in `static/icons/src/`, built into `static/icons/sprite.svg` — and two ways to draw from it. Pick by who renders the markup:

| Markup rendered by | Use | Why |
|---|---|---|
| The server — Templetor or Jinja templates, macros | the `icon()` macro (`openlibrary/macros/icon.html`): `icon("name", size="md", label="…")` | Sprite `<use>` — one cached request covers every icon on the page |
| Client-side JS, or anything inside a shadow root | `<ol-icon name="name" size="md" label="…">` | Inlines the glyph — sprite `<use>` is unreliable across shadow roots |

- **Never hand-inline an `<svg>` for a glyph that is in the set.** If a glyph is missing, add it to `static/icons/src/` so both paths get it.
- **Size is the `size` argument** — `sm` 16px, `md` 20px (default), `lg` 24px, from `tokens/icon-sizes.css`, which also corrects stroke width per size. Don't set width or height on the SVG.
- **`label` decides the semantics.** Omit it for decorative icons (rendered `aria-hidden`); pass it when the icon is the control's only content.
- Inside `ol-button`, pass `slot="icon-start"` or `slot="icon-end"` (the macro takes a `slot` argument) and let the button size and gap it.

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
--border-radius-lg: 12px;
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

The main semantic groups in `colors.css`: text (`--color-text`, `-heading`, `-secondary`, `-muted`, `-inverse`), icons (`--color-icon-muted`), surfaces (`--color-background`, `--color-surface`, `-raised`, `-sunken`, `-header`), links (`--color-link`, `-hover`, `-visited`), primary action (`--color-primary`, `-hover`, `-active`, `-subtle`, `--color-on-primary`), borders (`--color-border`, `-muted`, `-subtle`, `-extra-subtle`, `-hover`, `-focused`, `-error`, `--color-focus-ring`), and status (`--color-{info,success,error,warning}-{fg,bg,border}`).

Three of these are a **decorative tier** and carry that caveat in `colors.css`: `--color-border-muted` (1.6:1 on white), `--color-border-extra-subtle` (1.11:1) and `--color-icon-muted` (2.5:1). In new code they're for dividers and inert chrome — anything a user has to *read*, or that is the sole marker of a control's edge, needs `--color-border` or darker.

The three border weights are a scale, not three names for the same job. `--color-border-subtle` (1.3:1) is the everyday divider. `--color-border-extra-subtle` is for a separator that *repeats* — the rules between rows of a result list — where the everyday weight accumulates into a grid and the list starts reading as a spreadsheet.

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
| `static/css/tokens/typography.css` | Text-style roles, one token per property (`--font-size-overline`, `--font-weight-overline`, `--letter-spacing-overline`, `--text-transform-overline`); apply a role's tokens together |
| `static/css/tokens/motion.css` | Easing primitives and semantic motion tokens (`--ease-enter`, `--duration-base`, …) |
| `static/css/tokens/press.css` | Press-feedback scale tiers (`--press-scale-compact` / `--press-scale` / `--press-scale-wide`) |
| `static/css/tokens/borders.css` | Border and shadow tokens, plus the modal overlay scrim (`--overlay-backdrop-color` / `--overlay-backdrop-blur`) |
| `static/css/tokens/z-index.css` | Stacking primitives and semantic layers (`--z-index-sticky`, `-dropdown`, `-modal`, `-toast`, …) plus `--z-index-local-*` for layering inside an `isolation: isolate` root |
| `static/css/tokens/breakpoints.css` | Breakpoint scale — reference only, see [Breakpoints](#breakpoints) |
| `static/css/tokens/control-heights.css` | Outer heights for single-line controls |
| `static/css/tokens/icon-sizes.css` | Icon size and per-size stroke tokens |
| `static/css/tokens/line-heights.css` | Line-height scale |

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
serious interruption, which is backwards.

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
  it. A popover tray opened from inside the drawer stacks two scrims, and the
  drawer panel is pushed back along with the page. That reads as depth rather
  than a bug — but only because the shared token is light. Don't raise it.

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
  transition: transform var(--duration-press);
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

### Press feedback: self-contained controls squeeze, rows and surfaces don't

Scale a control on `:active` only if it is **self-contained**: it has its own visible boundary (fill, border, or shadow) separating it from its neighbors, and pressing it completes an action. Buttons, chips, icon buttons, pagination items, and carousel arrows qualify. Menu rows and drawer items press with a fill and no squeeze — their edges touch their siblings, so a shrinking row reads as the panel moving rather than the row being pressed. Surfaces (popover, dialog, drawer, toast) are never pressed; their `scale(0.95)` is an enter animation, not press feedback.

**Pick the tier by width, not importance.** The percentage is tuned so the edge travels about 1.5px: 3% is sub-pixel on a 32px icon button and a 15px lurch on a 500px search bar.

```css
/* Square icon controls (26–40px) */
.icon-button:active { transform: scale(var(--press-scale-compact)); } /* 0.92 */

/* Text controls (60–160px) */
.button:active { transform: scale(var(--press-scale)); }              /* 0.97 */

/* Stretched controls: full-width buttons, the search bar (200px+) */
.search-bar:active { transform: scale(var(--press-scale-wide)); }     /* 0.985 */
```

Tokens live in `static/css/tokens/press.css`. The press transition is the one place a hover-adjacent transition is allowed — `transform` only, never color (see [Hover state changes are instant](#hover-state-changes-are-instant)).

### Motion: pick the token for what is happening, not a curve

Every duration and easing comes from `tokens/motion.css`. Choose by what the element is doing:

| What's happening | Easing | Duration |
|---|---|---|
| A surface appears (popover, dialog, banner) | `--ease-enter` | `--duration-base` (200ms); large surfaces like the drawer and toast use `--duration-slower` (400ms) |
| That surface leaves | `--ease-exit` — same curve, shorter | `--duration-fast` or `--duration-base`; `--duration-slow` (300ms) for large surfaces. Exit ≤ enter, always |
| Something already on screen moves (segmented pill, a reorder) | `--ease-move` | `--duration-base` |
| A control changes state (checked, selected, loading, focused) | `--ease-state` | `--duration-fast` (150ms), `--duration-base` for a crossfade |
| Press | none needed | `--duration-press` (80ms), `transform` only |
| A spinner | `linear` | `--duration-spin` (700ms) per revolution |

Never write a raw `cubic-bezier()` or a bare `200ms` in a component. If a surface needs a different curve, add a named primitive to `motion.css` and a semantic token that references it — the codebase had reached five hand-written curves and three spinner speeds before these tokens existed.

```css
/* Bad - a bespoke curve and a magic number */
.tray { transition: transform 280ms cubic-bezier(0.23, 1, 0.32, 1); }

/* Good - says what it is */
.tray { transition: transform var(--duration-slow) var(--ease-enter); }
```

### Honor `prefers-reduced-motion`

Every transition and animation gets a `prefers-reduced-motion: reduce` override that sets it to `none`. Motion is enhancement; users who asked for less get the end state immediately. Ten of the eleven animated Lit components already do this — match them, including in `static/css`, where most animated files still don't.

```css
.panel {
  transition: transform 200ms ease-out;
}

@media (prefers-reduced-motion: reduce) {
  .panel {
    transition: none;
  }
}
```

**Never wait on `transitionend` or `animationend` unconditionally.** Under `reduce` the element has no transition, so the event never fires — a close handler waiting for the exit animation leaves a drawer stuck open with focus trapped. Read the computed duration and run the callback immediately when it is `0s`, with a timer fallback for dropped events (backgrounded tabs). `OlDrawer._afterTransition()` is the reference; `OlDialog` handles the same case for its open/close keyframes.

### Practical Tips

| Scenario | Solution |
| --- | --- |
| Icon next to a button label | Put the SVG in `ol-button`'s `icon-start` / `icon-end` slot — it's sized to the button (14/16/18px by size) and gapped automatically; don't set width/height/margin on the SVG or add a `::part(label)` gap |
| Hover on a solid/colored button | Lighten with `filter: brightness(1.1)`, not a darker color — see [above](#hover-moves-the-whole-control-and-its-direction-depends-on-the-fill) |
| Element appears from nowhere | Start from `scale(0.95)`, not `scale(0)` |
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

## Enforcement

What checks each rule today. "Review" means only a human or the Copilot UI checklist (`.github/instructions/ui.instructions.md`) catches it; those are the candidates for a lint. When a rule gains a check, shorten its entry above to a pointer here.

| Rule | Checked by |
|---|---|
| No raw colors; tokens for `color`, `background-color`, `font-family`, `z-index` | stylelint `color-no-hex`, `color-named`, `declaration-strict-value` — `static/**/*.css` and `openlibrary/**/*.css` only, **not** CSS inside Lit `static styles` |
| Semantic tokens meet WCAG AA | `tests/unit/js/token-contrast.test.js` (palette matrix), `tests/unit/js/design-contrast.test.js` (design-page badges) |
| Deprecated aliases | Review |
| No font-weight change on hover | Review |
| Hover is instant / border tracks fill / fill direction | Review |
| Press feedback tiers | Review |
| Motion via tokens, no raw curves or durations | Review |
| Blur follows modality; shared scrim tokens | Review |
| 16px text-entry controls | Review |
| Hover gated to hover-capable pointers | Review |
| Reduced-motion override on every transition/animation | Review |
| Breakpoints on the token scale, `max-width: N-1` | Review |
| Icons via macro / `ol-icon`, never inline SVG | Review |
