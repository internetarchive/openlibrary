/**
 * Regression guard: <summary> elements must have accessible names.
 *
 * Root cause: ReadButton.html rendered <summary></summary> (no content, no
 * aria-label) for the "More reading options" dropdown trigger on every book
 * result card. Fix: added aria-label="More reading options" in
 * openlibrary/macros/ReadButton.html.
 *
 * Covers: search results, author works list, book/work pages — any page
 * that renders the ReadButton macro with listen or locate options.
 *
 * GH: https://github.com/internetarchive/openlibrary/issues/13007
 */

import { test, expect } from '@playwright/test';
import { buildAxeScanner } from './axe-helpers';

const PAGES_WITH_READ_BUTTONS = [
    { name: 'search results', path: '/search?q=the+great+gatsby' },
    { name: 'author works', path: '/authors/OL23919A' },
    { name: 'work page', path: '/works/OL82563W' },
];

test.describe('summary-name: ReadButton dropdown has accessible name @a11y', () => {
    for (const { name, path } of PAGES_WITH_READ_BUTTONS) {
        test(`${name} — no summary-name violations`, async({ page }) => {
            await page.goto(path, { waitUntil: 'domcontentloaded' });

            const results = await buildAxeScanner(page).analyze();
            const violations = results.violations.filter(v => v.id === 'summary-name');

            if (violations.length > 0) {
                const detail = violations.flatMap(v => v.nodes.map(n => n.html)).join('\n');
                expect.soft(violations, `summary-name violations:\n${detail}`).toHaveLength(0);
            }

            expect(violations).toHaveLength(0);
        });
    }
});
