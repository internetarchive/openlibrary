# Icons

Open Library uses an SVG sprite system powered by [Lucide](https://lucide.dev) icons. Icons are rendered via a Templetor macro with no JavaScript dependency.

## How It Works

1. **Sprite file** (`static/icons/sprite.svg`) — Contains `<symbol>` elements for each icon
2. **Icon macro** (`openlibrary/macros/Icon.html`) — Renders an `<svg><use href="..."></svg>` referencing the sprite
3. **Build script** (`scripts/build-icons.js`) — Generates the sprite from Lucide + custom icons
4. **Base CSS** (`static/css/components/icon.css`) — Shared `.icon` class for display and stroke properties

## Using Icons in Templates

```html
$# Basic icon (24px default, decorative, aria-hidden)
$:macros.Icon("search")

$# Custom size
$:macros.Icon("chevron-down", size=16)

$# Accessible standalone icon (adds aria-label and role="img")
$:macros.Icon("x", label="Close dialog")

$# With extra CSS class
$:macros.Icon("chevron-right", cls="my-custom-class")
```

### Macro signature

```
$def with (name, size=24, label=None, cls="")
```

- `name` — Icon ID from the sprite (matches Lucide icon names, e.g., `"search"`, `"book-open"`)
- `size` — Width and height in pixels. Icons scale cleanly to any size.
- `label` — When set, adds `aria-label` and `role="img"`. When omitted, icon is `aria-hidden="true"`.
- `cls` — Additional CSS class(es) to add to the `<svg>` element.

## Color

Icons use `stroke="currentColor"` — they inherit the text color of their parent element. To change icon color, set `color` on the parent or on the icon itself:

```html
<span style="color: var(--green);">$:macros.Icon("check-circle") Success</span>
```

## Adding New Icons

### From Lucide

1. Find the icon name at [lucide.dev](https://lucide.dev)
2. Add it to the `ICONS` array in `scripts/build-icons.js`
3. Run `make icons` to regenerate the sprite

### Custom icons

1. Create an SVG following Lucide conventions: 24x24 viewBox, 2px stroke, round caps/joins, `currentColor`
2. Save to `static/icons/custom/my-icon.svg`
3. Run `make icons` — the build script automatically picks up custom icons
4. Use as `$:macros.Icon("my-icon")`

## Build

```bash
make icons              # Rebuild sprite
npm run build-icons     # Same thing via npm
```

The sprite is preloaded in `<head>` via `openlibrary/templates/site/head.html` and cache-busted with the `static_url()` hash.

## Key Files

| File | Purpose |
|------|---------|
| `openlibrary/macros/Icon.html` | Templetor macro |
| `scripts/build-icons.js` | Sprite generator |
| `static/icons/sprite.svg` | Generated sprite (do not edit by hand) |
| `static/icons/custom/` | Custom SVG icons |
| `static/css/components/icon.css` | Base `.icon` styles |
| `static/css/tokens/icon-sizes.css` | Size tokens (`--icon-sm` through `--icon-xl`) |

## Accessibility

- **Decorative icons** (next to visible text): Use `$:macros.Icon("name")` — renders with `aria-hidden="true"`
- **Standalone icons** (no adjacent text): Use `$:macros.Icon("name", label="Descriptive text")` — renders with `aria-label` and `role="img"`
- **Icon buttons**: Hide the icon and add a visually-hidden label:
  ```html
  <button>
      $:macros.Icon("trash-2")
      <span class="visually-hidden">Delete this list</span>
  </button>
  ```

## What NOT to use the icon system for

- **Brand logos** (Facebook, GitHub, etc.) — Keep as individual SVGs in `static/images/`
- **Category illustrations** (art.svg, biographies.svg, etc.) — These are full-color spot illustrations, not system icons
- **Onboarding illustrations** — Keep in `static/images/onboarding/`
