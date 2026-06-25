/**
 * WCAG 2.1 AA smoke scans — Phase 2 Playwright a11y infrastructure.
 *
 * These tests run axe-core against core Open Library pages and document
 * violations in test annotations. They do NOT fail on violations yet —
 * the baseline (2026-06-23) has 218 violations across 12 pages, and we
 * are fixing them class-by-class via dedicated PRs.
 *
 * Hardening plan (update this comment when a class is fixed):
 *   - contrast (color-contrast): #13009 — .star.star--small, .login-links__secondary
 *   - frame-title: #13008 — all iframes must have title attribute
 *   - Once a class is fully fixed: add .disableRules(['other-rule']) and
 *     assert expect(violations).toHaveLength(0) for that rule only.
 *
 * To run these tests locally:
 *   OL_BASE_URL=https://openlibrary.org npm run test:e2e -- --grep @a11y
 *   (or against Docker: OL_BASE_URL=http://localhost:8080 ...)
 *
 * GH issue: https://github.com/internetarchive/openlibrary/issues/13007
 */

import { test } from '@playwright/test';
import { buildAxeScanner, formatViolationAnnotation } from './axe-helpers';

/** Core pages from scripts/a11y/pages.json — keep in sync. */
const CORE_PAGES = [
    { name: 'home', path: '/' },
    { name: 'search', path: '/search?q=the+great+gatsby' },
    { name: 'work', path: '/works/OL82563W' },
    { name: 'author', path: '/authors/OL23919A' },
    { name: 'subjects', path: '/subjects/science' },
    { name: 'login', path: '/account/login' },
];

test.describe('A11y page scans @a11y', () => {
    for (const { name, path } of CORE_PAGES) {
        test(`${name} — WCAG 2.1 AA axe scan`, async({ page }, testInfo) => {
            await page.goto(path, { waitUntil: 'domcontentloaded' });

            const results = await buildAxeScanner(page).analyze();

            // Annotate with violation summary — visible in the HTML report.
            testInfo.annotations.push({
                type: 'a11y-violations',
                description: formatViolationAnnotation(results.violations),
            });

            // Log for CLI visibility.
            if (results.violations.length > 0) {
                for (const v of results.violations) {
                    console.log(`[a11y:${name}] ${v.id} (${v.impact}) — ${v.nodes.length} node(s): ${v.help}`);
                }
            }

            // Infrastructure gate only: axe must complete successfully.
            // TODO: harden per violation class as PRs land (see file header).
        });
    }
});
