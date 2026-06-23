/**
 * Regression guard: all <iframe> elements must have a title attribute (WCAG 2.4.1 / H64).
 *
 * Fixed iframes:
 *   - ia_thirdparty_logins.html — social login iframe on login/signup pages
 *     (title: "Sign in with a third-party account")
 *   - BookPreview.html — book preview floater dialog
 *     (title: "Book preview")
 *
 * Known exclusions:
 *   - reCAPTCHA iframe on signup page — third-party JS injection; not fixable
 *     in OL templates. Excluded via disableRules for that page only.
 *
 * GH: https://github.com/internetarchive/openlibrary/issues/13008
 */

import { test, expect } from '@playwright/test';
import { buildAxeScanner } from './axe-helpers';

test.describe('frame-title: iframes have accessible names @a11y', () => {
    test('login page — no frame-title violations', async({ page }) => {
        await page.goto('/account/login', { waitUntil: 'domcontentloaded' });

        const results = await buildAxeScanner(page).analyze();
        const violations = results.violations.filter(v => v.id === 'frame-title');

        if (violations.length > 0) {
            const detail = violations.flatMap(v => v.nodes.map(n => n.html)).join('\n');
            expect.soft(violations, `frame-title violations:\n${detail}`).toHaveLength(0);
        }
        expect(violations).toHaveLength(0);
    });

    test('work page — no frame-title violations (BookPreview iframe)', async({ page }) => {
        await page.goto('/works/OL82563W', { waitUntil: 'domcontentloaded' });

        const results = await buildAxeScanner(page).analyze();
        const violations = results.violations.filter(v => v.id === 'frame-title');

        if (violations.length > 0) {
            const detail = violations.flatMap(v => v.nodes.map(n => n.html)).join('\n');
            expect.soft(violations, `frame-title violations:\n${detail}`).toHaveLength(0);
        }
        expect(violations).toHaveLength(0);
    });

    test('signup page — no frame-title violations outside reCAPTCHA', async({ page }) => {
        await page.goto('/account/create', { waitUntil: 'domcontentloaded' });

        // reCAPTCHA is third-party JS — its iframe title is injected by Google
        // and not under OL control. Exclude the specific reCAPTCHA iframe.
        const results = await buildAxeScanner(page)
            .exclude('#g-recaptcha-response')
            .exclude('[src*="recaptcha"]')
            .analyze();

        const violations = results.violations.filter(v => v.id === 'frame-title');

        if (violations.length > 0) {
            const detail = violations.flatMap(v => v.nodes.map(n => n.html)).join('\n');
            expect.soft(violations, `frame-title violations (non-reCAPTCHA):\n${detail}`).toHaveLength(0);
        }
        expect(violations).toHaveLength(0);
    });
});
