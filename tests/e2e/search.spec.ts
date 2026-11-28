import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import { collectConsoleErrors } from './helpers';

const SEARCH_URL = '/search?q=tolkien';
// The work list only: the author suggestions and the lazy Search Inside band
// (whose archive.org-only hits don't link to /works/) reuse the item class.
const WORK_RESULT = '#searchResults > ul.list-books > .searchResultItem';
const NO_RESULTS = '.search-no-direct-match';

/**
 * Load the results page and report whether any works rendered.
 *
 * An empty index serves the no-results state, so callers skip on false. Any
 * other page (a 500, renamed markup) renders neither and fails here instead.
 */
async function gotoResults(page: Page): Promise<boolean> {
    await page.goto(SEARCH_URL);
    await expect(page.locator(`${WORK_RESULT}, ${NO_RESULTS}`).first()).toBeAttached({ timeout: 10_000 });
    return (await page.locator(NO_RESULTS).count()) === 0;
}

test.describe('Search page @smoke', () => {
    test('loads results for a known query', async ({ page }) => {
        const errors = collectConsoleErrors(page);
        test.skip(!(await gotoResults(page)), 'No Solr data indexed in this environment');
        await expect(page.locator(WORK_RESULT).first()).toBeVisible();
        expect(errors()).toHaveLength(0);
    });

    test('every result links to a work', async ({ page }) => {
        test.skip(!(await gotoResults(page)), 'No Solr data indexed in this environment');
        const works = page.locator(WORK_RESULT);
        await expect(works.filter({ hasNot: page.locator('a[href^="/works/"]') })).toHaveCount(0);
    });

    test('empty query shows no error page', async ({ page }) => {
        const response = await page.goto('/search?q=');
        expect(response?.status()).not.toBe(500);
        // Should not crash — either redirect to home or show empty state
        await expect(page.locator('#header-bar').first()).toBeVisible();
    });
});
