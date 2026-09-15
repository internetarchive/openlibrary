/**
 * Guards the WCAG contrast matrix that the color token system promises.
 * Parses static/css/tokens/colors.css, resolves var() chains, and asserts
 * contrast ratios so a palette tweak can't silently break accessibility.
 */
import fs from 'fs';
import path from 'path';
import { contrastRatio, relativeLuminance } from '../../../openlibrary/plugins/openlibrary/js/design-system/contrast.js';

const css = fs.readFileSync(
    path.join(__dirname, '../../../static/css/tokens/colors.css'),
    'utf8'
);

// --token-name: value; declarations (values may be hsl()/hsla()/var()).
// Comments are stripped first: the file documents itself in prose, and a
// declaration written inside one would shadow the real token (later wins).
const tokens = {};
for (const [, name, value] of css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    tokens[name] = value.trim();
}

function resolve(name, depth = 0) {
    expect(depth).toBeLessThan(10); // circular var() chain
    const value = tokens[name];
    expect(value).toBeDefined();
    const varMatch = value.match(/^var\((--[\w-]+)\)$/);
    return varMatch ? resolve(varMatch[1], depth + 1) : value;
}

function hslToRgb(cssValue) {
    const m = cssValue.match(/^hsla?\(\s*([\d.]+),\s*([\d.]+)%,\s*([\d.]+)%/);
    expect(m).not.toBeNull();
    const h = Number(m[1]) / 360, s = Number(m[2]) / 100, l = Number(m[3]) / 100;
    if (s === 0) {
        return [l, l, l];
    }
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    const hue = (t) => {
        if (t < 0) t += 1;
        if (t > 1) t -= 1;
        if (t < 1 / 6) return p + (q - p) * 6 * t;
        if (t < 1 / 2) return q;
        if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
        return p;
    };
    return [hue(h + 1 / 3), hue(h), hue(h - 1 / 3)];
}

// The luminance and ratio math is imported, not repeated here — the design
// system page badges tokens with the same functions, so the page and this
// guard can't disagree about where a threshold falls.
function contrast(fgToken, bgToken) {
    return contrastRatio(
        relativeLuminance(hslToRgb(resolve(fgToken))),
        relativeLuminance(hslToRgb(resolve(bgToken)))
    );
}

// [foreground, background, minimum ratio]
// 4.5 = WCAG AA normal text; 3 = AA large text and non-text UI (borders, icons)
const MATRIX = [
    // Text on the two page surfaces
    ['--color-text', '--color-surface', 4.5],
    ['--color-text', '--color-background', 4.5],
    ['--color-text', '--color-surface-sunken', 4.5],
    ['--color-text-heading', '--color-surface', 4.5],
    ['--color-text-heading', '--color-background', 4.5],
    ['--color-text-heading', '--color-surface-sunken', 4.5],
    ['--color-text-secondary', '--color-surface', 4.5],
    ['--color-text-secondary', '--color-background', 4.5],
    ['--color-text-secondary', '--color-surface-sunken', 4.5],
    // Muted text is only rated for white / neutral-50 surfaces — not for the
    // warm page canvas, which is darker than either
    ['--color-text-muted', '--color-surface', 4.5],
    ['--color-text-muted', '--neutral-50', 4.5],
    // Links
    ['--color-link', '--color-surface', 4.5],
    ['--color-link', '--color-background', 4.5],
    ['--color-link-hover', '--color-surface', 4.5],
    ['--color-link-visited', '--color-surface', 4.5],
    // Primary buttons
    ['--color-on-primary', '--color-primary', 4.5],
    ['--color-on-primary', '--color-primary-hover', 4.5],
    ['--color-on-primary', '--color-primary-active', 4.5],
    // Status text on white and on its own tint
    ['--color-info-fg', '--color-surface', 4.5],
    ['--color-info-fg', '--color-info-bg', 4.5],
    ['--color-success-fg', '--color-surface', 4.5],
    ['--color-success-fg', '--color-success-bg', 4.5],
    ['--color-error-fg', '--color-surface', 4.5],
    ['--color-error-fg', '--color-error-bg', 4.5],
    ['--color-warning-fg', '--color-surface', 4.5],
    ['--color-warning-fg', '--color-warning-bg', 4.5],
    // Non-text UI (3:1): default input border, focus ring, disabled text.
    // --color-border-muted and --color-icon-muted are absent on purpose — the
    // decorative tier (1.6:1 and 2.5:1 on white) makes no 3:1 promise.
    ['--color-border', '--color-surface', 3],
    ['--color-focus-ring', '--color-surface', 3],
    ['--color-focus-ring', '--color-background', 3],
    ['--color-disabled-fg', '--color-disabled-bg', 3],
];

describe('color token contrast (WCAG AA)', () => {
    test.each(MATRIX)('%s on %s ≥ %s:1', (fg, bg, min) => {
        expect(contrast(fg, bg)).toBeGreaterThanOrEqual(min);
    });

    test('semantic tokens reference primitives, not literals', () => {
        const semantic = Object.keys(tokens).filter(
            (name) => name.startsWith('--color-') && !name.startsWith('--color-chip-')
        );
        // A bare var(--ramp) or a color-mix() over one — both keep the ramp as
        // the single source of truth. What's banned is a raw color literal.
        for (const name of semantic) {
            const decl = `${name}: ${tokens[name]}`;
            expect(decl).toMatch(/var\(--[\w-]+\)/);
            expect(decl).not.toMatch(/#[\da-f]{3,8}\b|hsla?\(|rgba?\(/i);
        }
    });
});
