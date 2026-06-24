/**
 * Regression guard: link-name violations (WCAG 2.4.4 Link Purpose).
 *
 * Fixed violations:
 *   - generic-dropper__dropclick: the arrow anchor opening the my-books reading-list
 *     dropdown had only a <div class="arrow"> child — no accessible text.
 *     Fix: lib/dropper.html now accepts dropdown_label; my_books/dropper.html
 *     passes "More reading options for <title>" so screen readers announce purpose.
 *
 * Affected pages: /search (~20 nodes), /authors/* (~21 nodes).
 *
 * GH: https://github.com/internetarchive/openlibrary/issues/13009
 * PR: https://github.com/internetarchive/openlibrary/pull/13029
 */

import { test, expect } from '@playwright/test';
import { buildAxeScanner } from './axe-helpers';

test.describe('link-name: WCAG 2.4.4 fixes @a11y', () => {
    test('search page — no link-name violations (generic-dropper arrow)', async({ page }) => {
        await page.goto('/search?q=the+great+gatsby', { waitUntil: 'domcontentloaded' });

        const results = await buildAxeScanner(page).analyze();
        const violations = results.violations.filter(v => v.id === 'link-name');

        if (violations.length > 0) {
            const detail = violations.flatMap(v => v.nodes.map(n => n.html)).join('\n');
            expect.soft(violations, `link-name violations:\n${detail}`).toHaveLength(0);
        }
        expect(violations).toHaveLength(0);
    });

    test('author page — no link-name violations (generic-dropper arrow)', async({ page }) => {
        // F. Scott Fitzgerald — has many works, renders my-books droppers on each card
        await page.goto('/authors/OL34184A', { waitUntil: 'domcontentloaded' });

        const results = await buildAxeScanner(page).analyze();
        const violations = results.violations.filter(v => v.id === 'link-name');

        if (violations.length > 0) {
            const detail = violations.flatMap(v => v.nodes.map(n => n.html)).join('\n');
            expect.soft(violations, `link-name violations:\n${detail}`).toHaveLength(0);
        }
        expect(violations).toHaveLength(0);
    });
});
