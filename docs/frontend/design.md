# Design

Design patterns and conventions for all Open Library UI — templates, Vue components, Lit web components, and plain HTML/CSS alike. These guidelines apply whenever you're writing or modifying frontend code.

## Scope

These rules apply to every line you write or modify, in any file. Much of `static/css` predates them, so:

- **Don't match the surrounding legacy convention when it conflicts with a rule here.** The file's existing `--grey` or ungated `:hover` is not a precedent.
- **Fix the declaration you touch, not the file.** Changing a hover background? Move that value to a semantic token. Rewriting the whole rule block? Gate it to hover-capable pointers too. Leave untouched neighbors alone — whole-file migrations are their own PR.
- **`legacy.css` and `legacy-tools.css` are delete-only.** Move rules out; never edit them toward compliance in place.

The principles these rules serve — and the tensions between them — are on `/developers/design/principles`, registered as `PRINCIPLES` and `TENSIONS` in `openlibrary/plugins/openlibrary/design.py`. When a rule here feels arbitrary, that page has the reason; when two rules conflict, the *Tensions* list says which wins.

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

### Text-style roles

`tokens/typography.css` holds every text token: the primitives (families, the size ramp, the four weights `--font-weight-regular/medium/semibold/bold`, line heights) and the roles built from them, one token per property. Apply a role's tokens **together** — setting the size from the token and hand-coding the weight or tracking is how six copies of "overline" drifted apart. Never write a bare weight; take it from a role, or from a weight primitive where no role fits. Headings take the **heading** role (h1–h3) or **subheading** (h4–h6) in `base/common.css`. The **overline** role is the small all-caps heading over a group (a popover's "Sort by", the search modal's "Top results", a scorecard label):

```css
.section-heading {
  font-size: var(--font-size-overline);
  font-weight: var(--font-weight-overline);
  letter-spacing: var(--letter-spacing-overline);
  text-transform: var(--text-transform-overline);
}
```

Headings share the body ink (`--color-text-heading` is `--color-text`); size and weight carry the hierarchy, not color.

### Actions wrap; passive text truncates

A button label never ellipsizes. "Присоедин…" in a 140px carousel card hides the one thing the button does, so action labels wrap instead: give the control a `min-height` (not `height`), `text-wrap: balance`, and `hyphens: auto` with `overflow-wrap: anywhere` for single long words. In a flex row, the label or the button's half of a split control needs `min-width: 0`, or a long label sets its minimum width and pushes its neighbour out of the column. Ellipsis stays for passive text — titles, author names, subject chips — where the full value is one click away.

A state with nothing to act on ("Not in Library", "Checked Out") is status text, not a disabled-looking button. That is a book-page rule: off the book page (carousel cards, search results in list or grid, lists, the reading log) every entry ends in a button, and a book that can't be read here gets one secondary "Learn More" to its page instead of a preview, a library lookup, or status text. Where status text does stand in a card it takes the button's slot: centred in `--control-height-medium`, which holds two lines at `--font-size-label-medium`, and clamped at two so the row stays one height.

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

### Breakpoints

Custom properties can't be used in `@media`, so breakpoints are hard-coded px values with the token name in a comment. The scale is in `tokens/breakpoints.css`: 375 (`mobile-s`), 425 (`mobile-m`), 450 (`mobile`), 768 (`tablet`), 960 (`desktop`).

- Write `min-width: N` for at-or-above and `max-width: N-1` for below — `767px` is the correct mirror of `768px`. Never `N+1`: `min-width: 769px` leaves a one-pixel hole at exactly 768 where neither rule applies.
- Don't introduce values off the scale. `480px`, `600px`, `800px`, `769px` and `961px` exist in the codebase; they're the migration list, not precedent.

```css
/* --width-breakpoint-tablet */
@media (min-width: 768px) { … }
@media (max-width: 767px) { … }
```

### Right-to-left

Open Library serves Arabic, Hebrew, and Persian readers, so layout must mirror under `dir="rtl"`. Use **logical properties** for anything horizontal — `margin-inline-start`, `padding-inline`, `inset-inline-end`, `text-align: start` — and they mirror for free. `left`, `right`, `margin-left`, and `text-align: left` do not, and are the bugs the playground's *Right-to-left* check (`/developers/design/playground#rtl`) exists to catch.

Glyphs that point in the reading direction (a "next" arrow, a toggle knob's travel) don't mirror on their own; flip them explicitly, scoped to the host:

```css
/* OlPagination.js — the arrow points "forward" in both directions */
:host(:dir(rtl)) .pagination-arrow ol-icon {
  transform: scaleX(-1);
}
```

Symmetric glyphs (close, search, chevron-down) stay as they are.

### Blur follows modality, not viewport width

A surface blurs the page behind it when it is **modal** — when the page is
inert and a tap on the scrim is a dismiss. Blur is the signal that what's
behind is out of reach, so it tracks reachability, not screen size.

`ol-dialog` and `ol-drawer` are always modal, so they always carry the scrim
and its `backdrop-filter`. `ol-popover` is the instructive case: as a desktop
popover it is non-modal — the page stays live behind it, so it has no backdrop
at all — while its mobile bottom tray *is* modal, with a tap-to-dismiss scrim,
and so it blurs. The same component blurs in one mode and not the other because
modality changed, not because the viewport got narrow.

The practical consequence: don't reach for a blur because a surface is
full-screen on a phone, and don't drop one because a surface is small. Ask
whether the page behind is still usable.

```css
/* Both come from the shared overlay tokens, so every modal surface
   dims and blurs by the same amount. */
.scrim {
  background: var(--overlay-backdrop-color);
  backdrop-filter: blur(var(--overlay-backdrop-blur));
  -webkit-backdrop-filter: blur(var(--overlay-backdrop-blur));
}
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

### Popover placement

The default `ol-popover` placement is `bottom-start`, and the panel is never narrower than what it is anchored to. A short menu under a wide button fills the button's width, and a wider panel grows to one side instead of straddling the control. Keep that default in stacked columns of controls (the book page sidebar, a result row). Reserve `bottom-center` for icon-only or very small triggers, and `bottom-end` for triggers flush against a right edge. When only part of a control opens the popover, such as a split button's caret, set `anchor` (a selector) or `anchorElement` (across a shadow boundary) to the whole control so the panel lines up under it.

### Primary action goes right in a dialog, left in a page form

Two conventions, each standard in its own context. Both are deliberate — a page form whose button order disagrees with a dialog's is not a bug.

- **Dialogs and other contained surfaces** put the primary action on the right, matching OS and web convention. `olConfirm()` renders `[Cancel] [Confirm]` into a `justify-content: flex-end` row, and the footer example on `/developers/design` follows the same order.
- **Page forms** left-align their buttons with the primary action first, so it lines up with the inputs and sits where the reader's eye already is after the last field.

GitHub, Atlassian and Adobe split the same way.

### Menu rows

Rows inside a panel — the menu, options, and select popovers, the browse popover, the hamburger drawer, the design-site nav — are one shape, and share the tokens in `tokens/control-heights.css`:

- **Height** is `--menu-row-height`, applied as `min-height` so a row with a description can grow. Keep the row's own vertical padding under it, or the padding sets the height and rows drift apart again. On hover-capable pointers the token drops to `--control-height-medium`, so a menu reads as a stack of medium controls.
- **Inset as a pill.** A row sits `--menu-row-inset` in from the panel edge and takes `--border-radius-menu-row`, so its hover fill reads as a pill inside the panel rather than a band running to the edges. It gives that inset back as `--menu-row-padding-inline`, which keeps the label at 16px from the panel. A light-DOM panel that can't put a margin on its rows (the browse popover, the drawer) puts the inset on the panel's padding instead — on all four sides, not just the sides, or the corner rows stop being concentric (see [Nested radii are computed](#nested-radii-are-computed-not-chosen)). The row padding is the same either way.
- **Hover is `--color-hover-overlay`**, so it darkens whatever the panel is painted on. No press-scale — see [Press feedback](#press-feedback-self-contained-controls-squeeze-rows-and-surfaces-dont).
- **Selected rows get no tint and no weight change.** The radio or checkbox already carries the state, and a tinted row looks hovered. Where there is no control (`ol-menu-popover`, the design nav) the label goes `--color-link` — color only, so nothing re-measures.

```css
.item {
  min-height: var(--menu-row-height);
  margin-inline: var(--menu-row-inset);
  padding-inline: var(--menu-row-padding-inline);
  border-radius: var(--border-radius-menu-row);
}
```

## Icons

One set — sources in `static/icons/src/`, built into `static/icons/sprite.svg` — and two ways to draw from it. Pick by who renders the markup:

| Markup rendered by | Use | Why |
|---|---|---|
| The server — Templetor or Jinja templates, macros | the `icon()` macro (`openlibrary/macros/icon.html`): `icon("name", size="md", label="…")` | Sprite `<use>` — one cached request covers every icon on the page |
| Client-side JS, or anything inside a shadow root | `<ol-icon name="name" size="md" label="…">` | Inlines the glyph — sprite `<use>` is unreliable across shadow roots |

- **Never hand-inline an `<svg>` for a glyph that is in the set.** If a glyph is missing, drop a 24×24 `currentColor` SVG into `static/icons/src/<group>/` and run `make icons` — the filename becomes the icon name, and both outputs are generated, not committed.
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
| `static/css/tokens/spacing.css` | Spacing scale (inset / inline / stack) |
| `static/css/tokens/border-radius.css` | Border radius primitives and semantic tokens |
| `static/css/tokens/borders.css` | Border widths, divider and overlay borders, backdrop scrim |
| `static/css/tokens/breakpoints.css` | Viewport breakpoints |
| `static/css/tokens/control-heights.css` | Control heights and the menu-row contract |
| `static/css/tokens/font-families.css` | Font families and sizes |
| `static/css/tokens/icon-sizes.css` | Icon sizes |
| `static/css/tokens/line-heights.css` | Line heights |
| `static/css/tokens/motion.css` | Durations and easing curves |
| `static/css/tokens/press.css` | Press-feedback scale tiers |
| `static/css/tokens/z-index.css` | Stacking levels |

### Tokens in Shadow DOM

CSS custom properties inherit through the shadow boundary, so design tokens work directly inside Lit component `static styles` blocks without any extra wiring.

## Overlays

### Every floating surface shares one edge

A popover panel, a dialog, a drawer, a toast, and the mobile tray are the same object — a surface floating over the page — and take the same three tokens from `tokens/borders.css`: `--border-overlay`, `--border-radius-overlay`, `--box-shadow-overlay`. The hairline border draws the edge, which is what lets the shadow stay light enough to read as depth rather than a smudge. Don't drop the border on one surface or hand-roll a heavier shadow on another; a toast with a different edge from the popover next to it reads as a third kind of thing.

### Nested radii are computed, not chosen

When a shape sits inside a rounded surface, its radius is not a taste call — it
falls out of the surface it sits in:

```
inner radius = outer radius − inset
```

Two corners look right together when their arcs share a centre. Pick the inner
radius independently and the arcs drift apart, which is what a menu row looks
like when it turns its corner early and leaves a wedge of panel showing behind
it. Apple ships this rule as an API (`ConcentricRectangle` in iOS 26); we spell
it out in the tokens instead:

| Outer | Inset | Inner | Token |
|---|---|---|---|
| `--border-radius-overlay` 12px | `--menu-row-inset` 4px | 8px | `--border-radius-menu-row` |

Two things follow. **The inset has to be equal on all four sides** — a row inset
4px at the side but 8px at the top has no single concentric radius, so a panel
that puts the gutter on its own padding uses one value, not a two-value
shorthand. And **the pair moves together**: change `--border-radius-overlay` and
`--border-radius-menu-row` has to move with it, which is why the row has its own
token rather than borrowing `--border-radius-button`. A button is a free-standing
control and keeps its radius wherever it sits; a menu row does not.

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
  transition: transform var(--duration-press);
}
.button:hover {
  background: var(--lightest-grey);
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

A split control — `ol-shelf-button`'s split, the CTA dropper — is one fused shape, so the wrapper carries the press and `:active` reaches it from either half; a half that squeezes on its own reads as the control breaking. The wrapper stretches to its column, so it takes the wide tier, the same as `ol-button[full-width]` and the Buy trigger it sits beside on the book page.

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

Every transition and animation gets a `prefers-reduced-motion: reduce` override that sets it to `none`. Motion is enhancement; users who asked for less get the end state immediately. Every animated Lit component does this — match them, including in `static/css`, where most animated files still don't. Looping illustrations (the design page's principle figures) are gated the same way.

```css
.panel {
  transition: transform var(--duration-base) var(--ease-enter);
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
| Make buttons feel responsive | Add `transform: scale(var(--press-scale))` on `:active` — buttons only; icon-only controls take `--press-scale-compact` and stretched ones `--press-scale-wide` (see `tokens/press.css`). Menu rows and drawer items press with a fill, no squeeze: a shrinking row reads as the panel moving rather than the row being pressed. |
| Icon next to a button label | Put the SVG in `ol-button`'s `icon-start` / `icon-end` slot — it's sized to the button (14/16/18px by size) and gapped automatically; don't set width/height/margin on the SVG or add a `::part(label)` gap |
| Hover on a solid/colored button | Lighten with `filter: brightness(1.1)`, not a darker color — see [above](#hover-moves-the-whole-control-and-its-direction-depends-on-the-fill) |
| Hover border looks detached from fill | Shift `border-color` by the same amount as the fill |
| Element appears from nowhere | Start from `scale(0.95)`, not `scale(0)`; time it with `--duration-base` and `--ease-enter` |
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

### Fullscreen on mobile is for scrolling content, not forms

`ol-dialog`'s `fullscreen-on-mobile` renders the dialog edge-to-edge at ≤767px with `height: 100dvh`. **`dvh` tracks browser chrome, not the virtual keyboard** — and the site's viewport meta (`templates/site/head.html`) has no `interactive-widget=resizes-content`, so on iOS the keyboard doesn't resize the layout viewport at all. A full-height dialog therefore stays taller than the visible area while a field is focused: its footer is pinned to the bottom of a box that is now behind the keyboard, so the buttons the reader needs are unreachable. The taller-than-visible box also lets iOS pan the visual viewport and expose the page behind the dialog, which is why `ol-dialog` blurs the focused field on `touchmove` in fullscreen mode — a mitigation, not a fix.

Reach for fullscreen when the content itself scrolls and the actions are in the header or inline: a search palette, a result list, a picker. A dialog that is a label, a field, and two buttons stays compact, and the footer sits directly under the field where the keyboard can't reach it. The notes dialog (`macros/NotesModalDialog.html`) measures 372×396 at phone width against roughly 508px of keyboard-free space.

If a fullscreen dialog does contain a text field, its primary action has to be reachable without scrolling past the keyboard — put it in the header rather than a bottom footer.

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

## Enforcement

What checks each rule today. "Review" means only a human or the Copilot UI checklist (`.github/instructions/ui.instructions.md`) catches it; those are the candidates for a lint. When a rule gains a check, shorten its entry above to a pointer here.

| Rule | Checked by |
|---|---|
| No raw colors; tokens for `color`, `background-color`, `font-family`, `z-index` | stylelint `color-no-hex`, `color-named`, `declaration-strict-value` — `static/**/*.css` and `openlibrary/**/*.css` only, **not** CSS inside Lit `static styles` |
| Semantic tokens meet WCAG AA | `tests/unit/js/token-contrast.test.js` (palette matrix), `tests/unit/js/design-contrast.test.js` (design-page badges) |
| Deprecated aliases | Review |
| No font-weight change on hover | Review |
| Action labels wrap, never ellipsize; status text instead of dead buttons | Review |
| Hover is instant / border tracks fill / fill direction | Review |
| Press feedback tiers | Review |
| Motion via tokens, no raw curves or durations | Review |
| Blur follows modality; shared scrim tokens | Review |
| 16px text-entry controls | Review |
| Fullscreen dialogs only for scrolling content, not forms | Review |
| Hover gated to hover-capable pointers | Review |
| Menu rows on the shared height/inset tokens; selected rows untinted | Review |
| Overline via the typography role tokens, applied together | Review |
| Logical properties; directional glyphs flipped under `:dir(rtl)` | Review |
| Floating surfaces on the shared overlay border/radius/shadow | Review |
| Reduced-motion override on every transition/animation | Review |
| Breakpoints on the token scale, `max-width: N-1` | Review |
| Icons via macro / `ol-icon`, never inline SVG | Review |
