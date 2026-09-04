import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import { collectConsoleErrors } from './helpers';

const SEARCH_URL = '/search?q=tolkien';
const RESULT_ITEM = '.searchResultItem';

/**
 * Load the results page and report how many results rendered.
 *
 * An environment with no Solr index serves the same page with no results, so
 * the specs below skip rather than fail. The check is the result items
 * themselves, not the page title: the title is set client-side, and reading it
 * straight after goto() races that update, which silently skipped these tests.
 */
async function gotoResults(page: Page): Promise<number> {
    await page.goto(SEARCH_URL);
    const items = page.locator(RESULT_ITEM);
    await items.first().waitFor({ timeout: 10_000 }).catch(() => {});
    return items.count();
}

test.describe('Search page @smoke', () => {
    test('loads results for a known query', async ({ page }) => {
        const errors = collectConsoleErrors(page);
        const count = await gotoResults(page);
        test.skip(count === 0, 'No Solr data indexed in this environment');
        await expect(page.locator('.search-results, #searchResults').first()).toBeVisible();
        expect(errors()).toHaveLength(0);
    });

    test('every result links to a work', async ({ page }) => {
        const count = await gotoResults(page);
        test.skip(count === 0, 'No Solr data indexed in this environment');
        const links = await page.locator(`${RESULT_ITEM} a[href^="/works/"]`).count();
        expect(links).toBeGreaterThan(0);
    });

    test('empty query shows no error page', async ({ page }) => {
        const response = await page.goto('/search?q=');
        expect(response?.status()).not.toBe(500);
        // Should not crash — either redirect to home or show empty state
        await expect(page.locator('#header-bar').first()).toBeVisible();
    });
});
