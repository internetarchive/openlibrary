/**
 * WCAG 2.x relative luminance and contrast ratio. Shared by the live contrast
 * badges and the token-contrast guard test, so the two can't disagree.
 */

export const WHITE = [255, 255, 255];

/**
 * Relative luminance of an sRGB triple whose channels are already 0–1.
 */
export function relativeLuminance([r, g, b]) {
    const [rl, gl, bl] = [r, g, b].map((channel) =>
        channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
    );
    return 0.2126 * rl + 0.7152 * gl + 0.0722 * bl;
}

/**
 * Contrast ratio between two relative luminances, lighter over darker.
 */
export function contrastRatio(luminanceA, luminanceB) {
    return (Math.max(luminanceA, luminanceB) + 0.05) / (Math.min(luminanceA, luminanceB) + 0.05);
}

/**
 * A browser-resolved color as `{ rgb, alpha }`, channels 0–255.
 *
 * A computed style serializes a resolved color two ways: `rgb()`/`rgba()` with
 * 0–255 channels, and — for `color-mix()`, depending on the engine —
 * `color(srgb …)` with 0–1 ones. Any other color space is declined rather than
 * read at the wrong channel scale. Returns null if it can't be read.
 */
export function parseCssColor(color) {
    if (!color) return null;
    const wide = color.match(/^color\(\s*([\w-]+)([^)]*)\)/);
    if (wide && wide[1] !== 'srgb') return null;
    const parts = (wide ? wide[2] : color).match(/[\d.]+/g);
    if (!parts || parts.length < 3) return null;
    return {
        rgb: parts.slice(0, 3).map((value) => Number(value) * (wide ? 255 : 1)),
        alpha: parts.length > 3 ? Number(parts[3]) : 1,
    };
}

/**
 * Flatten a parsed color onto an opaque backdrop. Browsers composite in
 * gamma-encoded sRGB, so the channels blend as they are.
 */
export function compositeOver({ rgb, alpha }, backdrop = WHITE) {
    if (alpha >= 1) return rgb;
    return rgb.map((channel, index) => channel * alpha + backdrop[index] * (1 - alpha));
}

/**
 * Contrast between a parsed color and an opaque backdrop.
 *
 * A translucent color has no ratio of its own — what shows through it is part
 * of what you see — so it is composited onto the backdrop first. Measuring its
 * opaque base instead would score `color-mix(--blue-500 8%, transparent)`, a
 * fill that reads as barely-tinted white, as if it were solid blue.
 */
export function contrastOn(color, backdrop) {
    return contrastRatio(luminanceOf(compositeOver(color, backdrop)), luminanceOf(backdrop));
}

/**
 * Relative luminance from a browser-resolved color string, composited over an
 * opaque backdrop (white unless given one). Returns null if it can't be read.
 */
export function luminanceFromCssColor(color, backdrop = WHITE) {
    const parsed = parseCssColor(color);
    return parsed === null ? null : luminanceOf(compositeOver(parsed, backdrop));
}

function luminanceOf(rgb) {
    return relativeLuminance(rgb.map((channel) => channel / 255));
}
