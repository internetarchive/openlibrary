# Self-hosted web fonts

| File | Family | Axes kept | Subset | Size |
|---|---|---|---|---|
| `Literata-latin.woff2` | [Literata](https://github.com/googlefonts/literata) (OFL) | `wght 400–700`, `opsz 12–36` | latin | ~55 KB |
| `Inter-latin.woff2` | [Inter](https://github.com/rsms/inter) (OFL) | `wght 400–700` (`opsz` pinned at 14) | latin | ~50 KB |

Literata is the serif for headings, book titles, and quotes; Inter is the
sans for UI and body text. `@font-face` rules (including metric-adjusted
local fallbacks that minimize CLS) live in `static/css/tokens/font-faces.css`,
and both files are preloaded in `openlibrary/templates/site/head.html`.

Italics are not shipped — browsers synthesize an oblique, which is acceptable
for the small amount of italic text. Non-latin scripts fall back to the
system stacks via `unicode-range`.

## Rebuilding the subsets

Source: the variable TTFs from the [google/fonts](https://github.com/google/fonts)
repo (`ofl/literata/Literata[opsz,wght].ttf`, `ofl/inter/Inter[opsz,wght].ttf`).

```bash
LATIN="U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"

# 1. Restrict the variation space (fonttools varLib.instancer)
uvx --from "fonttools[woff]" --with brotli fonttools varLib.instancer \
    -o Literata-inst.ttf "Literata[opsz,wght].ttf" "wght=400:700" "opsz=12:36"
uvx --from "fonttools[woff]" --with brotli fonttools varLib.instancer \
    -o Inter-inst.ttf "Inter[opsz,wght].ttf" "wght=400:700" "opsz=14"

# 2. Subset to latin and compress to woff2 (pyftsubset)
uvx --from "fonttools[woff]" --with brotli pyftsubset Literata-inst.ttf \
    --unicodes="$LATIN" --flavor=woff2 --output-file=Literata-latin.woff2
uvx --from "fonttools[woff]" --with brotli pyftsubset Inter-inst.ttf \
    --unicodes="$LATIN" --flavor=woff2 --output-file=Inter-latin.woff2
```

The fallback metrics in `font-faces.css` (`size-adjust` / `ascent-override` /
`descent-override`) come from [fontpie](https://github.com/pixel-point/fontpie)
(`npx fontpie <file>.woff2`) for Inter/Arial, and the same
frequency-weighted-average-width method computed against Georgia for
Literata (fontpie has no Georgia preset). Recompute them if the font files
change.
