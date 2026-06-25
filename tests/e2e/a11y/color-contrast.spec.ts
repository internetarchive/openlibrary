/**
 * Regression guard: color contrast violations (WCAG 1.4.3).
 *
 * Fixed violations:
 *   - OlToggle.js: sublabel hardcoded #777 (4.47:1) → var(--accessible-grey) (4.54:1)
 *     Appears as .toggle__sublabel on search page (result count badge on toggle)
 *   - nav-bar.css: selected work-menu tab used --blue-5e88B9 background (3.4:1 with white)
 *     → --primary-blue (4.82:1 with white); hover → --header-nav-hover-color (6.56:1)
 *
 * Known pa11y-only violations (not caught by axe, require design decision):
 *   - .star.star--small: gold (hsl 50, 100%, 50%) on white = ~1.4:1
 *     Stars are decorative (rating conveyed in adjacent text) — tracked in #13009.
 *
 * GH: https://github.com/internetarchive/openlibrary/issues/13009
 */

import { test, expect } from '@playwright/test';
import { buildAxeScanner } from './axe-helpers';

test.describe('color-contrast: WCAG 1.4.3 fixes @a11y', () => {
    test('search page — no color-contrast violations (OlToggle sublabel)', async({ page }) => {
        await page.goto('/search?q=the+great+gatsby', { waitUntil: 'domcontentloaded' });

        const results = await buildAxeScanner(page).analyze();
        const violations = results.violations.filter(v => v.id === 'color-contrast');

        if (violations.length > 0) {
            const detail = violations.flatMap(v => v.nodes.map(n => n.html)).join('\n');
            expect.soft(violations, `color-contrast violations:\n${detail}`).toHaveLength(0);
        }
        expect(violations).toHaveLength(0);
    });

    test('work page — no color-contrast violations (nav-bar selected tab)', async({ page }) => {
        await page.goto('/works/OL82563W', { waitUntil: 'domcontentloaded' });

        const results = await buildAxeScanner(page).analyze();
        const violations = results.violations.filter(v => v.id === 'color-contrast');

        if (violations.length > 0) {
            const detail = violations.flatMap(v => v.nodes.map(n => n.html)).join('\n');
            expect.soft(violations, `color-contrast violations:\n${detail}`).toHaveLength(0);
        }
        expect(violations).toHaveLength(0);
    });
});
