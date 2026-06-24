/**
 * Regression guard: aria-prohibited-attr violations (WCAG 4.1.2 Name, Role, Value).
 *
 * Fixed violations:
 *   - <ol-select-popover aria-label="Filter by language"> on /search:
 *     custom elements have no implicit ARIA role, so aria-label is prohibited.
 *     Fix: OlSelectPopover.connectedCallback sets role="group" on the host
 *     (when no explicit role is set), making aria-label valid.
 *
 * GH: https://github.com/internetarchive/openlibrary/issues/13009
 * PR: https://github.com/internetarchive/openlibrary/pull/13037
 */

import { test, expect } from '@playwright/test';
import { buildAxeScanner } from './axe-helpers';

test.describe('aria-prohibited-attr: WCAG 4.1.2 fixes @a11y', () => {
    test('search page — no aria-prohibited-attr violations (ol-select-popover)', async({ page }) => {
        await page.goto('/search?q=the+great+gatsby', { waitUntil: 'domcontentloaded' });

        const results = await buildAxeScanner(page).analyze();
        const violations = results.violations.filter(v => v.id === 'aria-prohibited-attr');

        if (violations.length > 0) {
            const detail = violations.flatMap(v => v.nodes.map(n => n.html)).join('\n');
            expect.soft(violations, `aria-prohibited-attr violations:\n${detail}`).toHaveLength(0);
        }
        expect(violations).toHaveLength(0);
    });
});
