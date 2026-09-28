/**
 * The contrast math behind the design system's live token badges.
 *
 * The palette matrix itself is guarded by token-contrast.test.js; this covers
 * reading a browser-resolved color and compositing it, which is what the badges
 * do and the matrix doesn't.
 */
import {
    WHITE,
    compositeOver,
    contrastOn,
    luminanceFromCssColor,
    parseCssColor,
} from '../../../openlibrary/plugins/openlibrary/js/design-system/contrast.js';

// --blue-500, hsl(202, 96%, 37%), as a computed style resolves it.
const BLUE_500 = [4, 119, 185];
// --paper, hsl(48, 31%, 84%) — the page canvas.
const PAPER = [227, 222, 202];

describe('parseCssColor', () => {
    test('reads rgb() as opaque', () => {
        expect(parseCssColor('rgb(4, 119, 185)')).toEqual({ rgb: BLUE_500, alpha: 1 });
    });

    test('reads the alpha off rgba()', () => {
        expect(parseCssColor('rgba(4, 119, 185, 0.08)')).toEqual({ rgb: BLUE_500, alpha: 0.08 });
    });

    test('scales color(srgb …) channels up from 0–1', () => {
        const { rgb, alpha } = parseCssColor('color(srgb 0 0.5 1 / 0.5)');
        expect(rgb).toEqual([0, 127.5, 255]);
        expect(alpha).toBe(0.5);
    });

    test('declines a color space whose channel scale it would have to guess', () => {
        expect(parseCssColor('color(display-p3 0.1 0.4 0.7)')).toBeNull();
    });

    test('returns null for anything unreadable', () => {
        expect(parseCssColor('')).toBeNull();
        expect(parseCssColor(null)).toBeNull();
        expect(parseCssColor('rgb(4, 119)')).toBeNull();
    });
});

describe('compositeOver', () => {
    test('leaves an opaque color alone', () => {
        expect(compositeOver({ rgb: BLUE_500, alpha: 1 })).toEqual(BLUE_500);
    });

    test('blends toward white by default', () => {
        expect(compositeOver({ rgb: [0, 0, 0], alpha: 0.5 })).toEqual([127.5, 127.5, 127.5]);
    });

    test('blends toward whatever backdrop it is given', () => {
        expect(compositeOver({ rgb: [0, 0, 0], alpha: 0.5 }, [100, 100, 100])).toEqual([50, 50, 50]);
    });
});

describe('contrastOn', () => {
    test('an opaque token scores against the backdrop directly', () => {
        // --color-link (--blue-600) on white, the ratio the palette promises.
        expect(contrastOn(parseCssColor('rgb(3, 89, 140)'), WHITE)).toBeCloseTo(7.47, 2);
    });

    test('a translucent token is composited, not scored as its opaque base', () => {
        // --color-control-selected-bg: color-mix(in srgb, var(--blue-500) 8%,
        // transparent). Dropping the alpha scored this ~4.8:1 — an AA badge on
        // a fill that reads as barely-tinted white.
        const tint = parseCssColor('rgba(4, 119, 185, 0.08)');
        expect(contrastOn(tint, WHITE)).toBeCloseTo(1.11, 2);
        expect(contrastOn(tint, PAPER)).toBeCloseTo(1.1, 1);
    });

    test('fully transparent is indistinguishable from its backdrop', () => {
        expect(contrastOn(parseCssColor('rgba(0, 0, 0, 0)'), WHITE)).toBeCloseTo(1, 5);
    });
});

describe('luminanceFromCssColor', () => {
    test('composites before measuring', () => {
        // Half-opacity black over white is mid-grey, not black.
        expect(luminanceFromCssColor('rgba(0, 0, 0, 0.5)')).toBeCloseTo(0.214, 3);
        expect(luminanceFromCssColor('rgb(0, 0, 0)')).toBe(0);
    });

    test('returns null for an unreadable color', () => {
        expect(luminanceFromCssColor('none')).toBeNull();
    });
});
