import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import { a11yCheck, expectNoViolations, THIRD_PARTY_FRAMES } from './a11y';

/**
 * Navigate, then wait for the global header before scanning.
 *
 * `goto` resolves on `load`, which can be before the page has painted. Axe's
 * contrast rules read computed pixels, so scanning that early gives different
 * results run to run. Every other spec in this directory anchors on
 * `#header-bar` for the same reason.
 *
 * Note this settles first paint, not lazily-loaded content: the home page's
 * carousels populate after `load` and may or may not be in a given scan.
 * That's why the canary below counts rules evaluated rather than nodes.
 */
async function gotoSettled(page: Page, path: string): Promise<void> {
    // Block archive.org before navigating so the donation banner never loads.
    // Its content rotates by campaign, and axe does scan inside cross-origin
    // frames under Playwright, so an unblocked scan could flip between runs
    // with no Open Library change. These scans should only ever see markup
    // we author.
    await page.route('https://archive.org/**', (route) => route.abort());
    await page.goto(path);
    await expect(page.locator('#header-bar').first()).toBeVisible();
}

test.describe('Accessibility @a11y', () => {
    test('home page has no WCAG 2.1 AA violations', async ({ page }) => {
        await gotoSettled(page, '/');
        expectNoViolations(await a11yCheck(page, { exclude: THIRD_PARTY_FRAMES }));
    });

    test('home page passes colour contrast', async ({ page }) => {
        // The example of a scoped, single-rule check. Contrast is also the
        // headline reason this suite exists: the jsdom component tests can't
        // evaluate it at all, because jsdom never paints anything.
        await gotoSettled(page, '/');
        expectNoViolations(await a11yCheck(page, { rules: ['color-contrast'], exclude: THIRD_PARTY_FRAMES }));
    });

    test('axe actually evaluates rules', async ({ page }) => {
        // Guard against a passing suite that checks nothing: a bad selector or
        // a broken tag filter would leave zero applicable rules, and every
        // "no violations" assertion above would be vacuously true.
        await gotoSettled(page, '/');
        const results = await a11yCheck(page, { exclude: THIRD_PARTY_FRAMES });

        // Count every rule axe reached a conclusion about, not just the ones
        // that passed. A rule that starts failing moves from `passes` to
        // `violations`, which is a real regression for the tests above to
        // report — this one should keep confirming axe ran, not fail alongside
        // them with a misleading "axe is broken" message.
        const evaluated = [...results.passes, ...results.violations, ...results.incomplete].map((rule) => rule.id);

        expect(results.testEngine.name).toBe('axe-core');
        expect(evaluated.length).toBeGreaterThan(20);
        expect(evaluated).toContain('color-contrast');
    });
});
