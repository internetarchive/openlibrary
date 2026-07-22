import { test, expect } from '@playwright/test';

/**
 * Opt-in visual regression screenshots for the design-refresh series.
 *
 * Not CI-gating: these only run when OL_VISUAL=1 is set, and are meant to
 * be run locally before/after each design phase:
 *
 *   OL_VISUAL=1 npx playwright test visual --update-snapshots   # baseline
 *   OL_VISUAL=1 npx playwright test visual                      # compare
 *
 * Snapshots are stored per-project (desktop 1280x800, mobile 390x844 via
 * the @mobile-tagged copies) next to this spec.
 */

const visual = process.env.OL_VISUAL === '1';

// OL286811W is present in the dev DB seed data
const PAGES: Array<[name: string, path: string]> = [
    ['home', '/'],
    ['search', '/search?q=lord+of+the+rings'],
    ['book', '/works/OL286811W'],
];

for (const [name, path] of PAGES) {
    test(`visual: ${name}`, async ({ page }) => {
        test.skip(!visual, 'Set OL_VISUAL=1 to run visual regression checks');
        await page.goto(path, { waitUntil: 'networkidle' });
        await page.waitForTimeout(1500);
        await expect(page).toHaveScreenshot(`${name}-full.png`, {
            fullPage: true,
            // Covers and carousels vary with dev data; mask the volatile bits.
            mask: [page.locator('.bookcover img'), page.locator('.carousel')],
            maxDiffPixelRatio: 0.02,
        });
    });

    test(`visual: ${name} @mobile`, async ({ page }) => {
        test.skip(!visual, 'Set OL_VISUAL=1 to run visual regression checks');
        await page.goto(path, { waitUntil: 'networkidle' });
        await page.waitForTimeout(1500);
        await expect(page).toHaveScreenshot(`${name}-mobile-full.png`, {
            fullPage: true,
            mask: [page.locator('.bookcover img'), page.locator('.carousel')],
            maxDiffPixelRatio: 0.02,
        });
    });
}

test('visual: header + footer', async ({ page }) => {
    test.skip(!visual, 'Set OL_VISUAL=1 to run visual regression checks');
    await page.goto('/', { waitUntil: 'networkidle' });
    await expect(page.locator('header#header-bar')).toHaveScreenshot('header.png');
    await expect(page.locator('footer').first()).toHaveScreenshot('footer.png');
});
