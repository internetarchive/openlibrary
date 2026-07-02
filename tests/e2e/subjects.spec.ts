import { test, expect } from '@playwright/test';
import { collectConsoleErrors } from './helpers';

const SUBJECT_URL = '/subjects/fiction';

// Subjects pages require a healthy Solr index.
// In local dev with no Solr data they may return 404, or return 200 with an error page.
// Guard: skip if the page returned a non-OL page (no #header-bar) or a 404.
const skipIfNoSolr = async ({ page }: { page: import('@playwright/test').Page }) => {
    const response = await page.goto(SUBJECT_URL);
    if (response?.status() === 404) {
        test.skip(true, 'Subjects require Solr data — not available in this environment');
    }
    const hasHeader = await page.locator('#header-bar').isVisible().catch(() => false);
    if (!hasHeader) {
        test.skip(true, 'Subjects page returned an error (Solr likely unhealthy) — skipping');
    }
};

test.describe('Subjects page @smoke', () => {
    test('loads with subject heading', async ({ page }) => {
        const errors = collectConsoleErrors(page);
        const response = await page.goto(SUBJECT_URL);
        test.skip(response?.status() === 404, 'Subjects require Solr data — not available in this environment');
        const hasHeader = await page.locator('#header-bar').isVisible().catch(() => false);
        test.skip(!hasHeader, 'Subjects page returned an error (Solr likely unhealthy) — skipping');
        // h1.inline is the subject name heading (from subjects.html template)
        const heading = page.locator('h1.inline, h1').first();
        await expect(heading).toBeVisible();
        const text = await heading.textContent();
        expect(text?.trim().length).toBeGreaterThan(0);
        expect(errors()).toHaveLength(0);
    });

    test('shows book count for the subject', async ({ page }) => {
        await skipIfNoSolr({ page });
        // #coversCount shows the number of works with this subject
        const count = page.locator('#coversCount');
        await expect(count).toBeVisible();
    });

    test('unknown subject shows a page (not 500)', async ({ page }) => {
        // First confirm the subjects system is healthy; if not, skip (Solr down causes 500 everywhere).
        await skipIfNoSolr({ page });
        const response = await page.goto('/subjects/xyzzy_nonexistent_subject_12345');
        expect(response?.status()).not.toBe(500);
        await expect(page.locator('#header-bar').first()).toBeVisible();
    });
});
