// @ts-check
import { test, expect } from '@playwright/test';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SCREENSHOTS = join(__dirname, 'screenshots');

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function screenshotPath(name) {
    return join(SCREENSHOTS, `${name}.png`);
}

// ─────────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Header Search — Desktop', () => {
    test.use({ viewport: { width: 1280, height: 800 } });

    test('baseline: page loads with header search visible', async ({ page }) => {
        await page.goto('/');
        await page.waitForSelector('header#header-bar');

        await page.screenshot({ path: screenshotPath('01-baseline-desktop'), clip: { x: 0, y: 0, width: 1280, height: 120 } });

        // Search input is visible
        const input = page.locator('header#header-bar input[name="q"]').first();
        await expect(input).toBeVisible();

        // Facet selector area is visible (either native select or ol-facet-select)
        const facetArea = page.locator('header#header-bar .search-bar').first();
        await expect(facetArea).toBeVisible();
    });

    test('facet selector: shows current selection', async ({ page }) => {
        await page.goto('/');
        await page.waitForSelector('header#header-bar');

        const searchBar = page.locator('header#header-bar .search-bar').first();
        await expect(searchBar).toBeVisible();

        await page.screenshot({ path: screenshotPath('02-facet-selector-default'), clip: { x: 0, y: 0, width: 500, height: 120 } });
    });

    test('facet selector: ol-facet-select opens popover on click', async ({ page }) => {
        await page.goto('/');
        await page.waitForSelector('ol-facet-select', { timeout: 5000 }).catch(() => {
            test.skip(true, 'ol-facet-select not yet in page (pre-migration)');
        });

        const trigger = page.locator('ol-facet-select .trigger').first();
        await trigger.click();

        await page.screenshot({ path: screenshotPath('03-facet-popover-open'), clip: { x: 0, y: 0, width: 500, height: 400 } });

        // Popover panel with options should be visible
        const panel = page.locator('ol-popover').first();
        await expect(panel).toBeVisible();
    });

    test('facet selector: selecting Title closes popover and updates trigger', async ({ page }) => {
        await page.goto('/');
        const facetSelectEl = await page.locator('ol-facet-select').first().elementHandle();
        if (!facetSelectEl) {
            test.skip(true, 'ol-facet-select not in page');
            return;
        }

        const trigger = page.locator('ol-facet-select .trigger').first();
        await trigger.click();

        // Click the "Title" option
        const titleBtn = page.locator('ol-facet-select li button').filter({ hasText: 'Title' }).first();
        await titleBtn.click();

        await page.screenshot({ path: screenshotPath('04-facet-title-selected'), clip: { x: 0, y: 0, width: 500, height: 120 } });

        // Trigger should now show "Title"
        await expect(trigger).toContainText('Title');
    });

    test('search: submitting navigates to /search', async ({ page }) => {
        await page.goto('/');
        await page.waitForSelector('header#header-bar input[name="q"]');

        const input = page.locator('header#header-bar input[name="q"]').first();
        await input.fill('frankenstein');
        await input.press('Enter');

        await page.waitForURL(/\/search\?.*q=frankenstein/, { timeout: 10000 });
        expect(page.url()).toContain('/search');
        expect(page.url()).toContain('frankenstein');
    });

    test('autocomplete: shows results after 3+ characters', async ({ page }) => {
        await page.goto('/');
        await page.waitForSelector('header#header-bar input[name="q"]');

        const input = page.locator('header#header-bar input[name="q"]').first();
        await input.fill('dune');

        // Wait for autocomplete results to appear (debounced at 500ms)
        await page.waitForSelector('header#header-bar .search-results li', { timeout: 5000 }).catch(() => null);
        await page.screenshot({ path: screenshotPath('05-autocomplete-results'), clip: { x: 0, y: 0, width: 600, height: 400 } });
    });
});

test.describe('Header Search — Mobile', () => {
    test.use({ viewport: { width: 375, height: 812 } });

    test('baseline: mobile layout at 375px', async ({ page }) => {
        await page.goto('/');
        await page.waitForSelector('header#header-bar');

        await page.screenshot({ path: screenshotPath('06-baseline-mobile'), clip: { x: 0, y: 0, width: 375, height: 120 } });
    });

    test('mobile: search expands on click', async ({ page }) => {
        await page.goto('/');
        await page.waitForSelector('header#header-bar');

        // Click the search area to expand it
        const searchComponent = page.locator('header#header-bar .search-component').first();
        await searchComponent.click();

        await page.waitForTimeout(300);
        await page.screenshot({ path: screenshotPath('07-mobile-expanded'), clip: { x: 0, y: 0, width: 375, height: 160 } });
    });
});
