/**
 * Regression guard: nested-interactive violations (WCAG 4.1.2 Name, Role, Value).
 *
 * Fixed violations:
 *   - slick carousel slides had role="option" which made them interactive
 *     containers. Slides also contained links, creating nested-interactive
 *     violations (9 nodes on home: tutorial carousel + category carousel).
 *   - Fix: MutationObserver in Carousel.js removes role="option" from slides
 *     after init and after any dynamically added slides (loadMore path).
 *
 * GH: https://github.com/internetarchive/openlibrary/issues/13009
 * PR: https://github.com/internetarchive/openlibrary/pull/13031
 */

import { test, expect } from '@playwright/test';
import { buildAxeScanner } from './axe-helpers';

test.describe('nested-interactive: WCAG 4.1.2 fixes @a11y', () => {
    test('home page — no nested-interactive violations (slick carousel slides)', async({ page }) => {
        await page.goto('/', { waitUntil: 'domcontentloaded' });

        const results = await buildAxeScanner(page).analyze();
        const violations = results.violations.filter(v => v.id === 'nested-interactive');

        if (violations.length > 0) {
            const detail = violations.flatMap(v => v.nodes.map(n => n.html)).join('\n');
            expect.soft(violations, `nested-interactive violations:\n${detail}`).toHaveLength(0);
        }
        expect(violations).toHaveLength(0);
    });
});
