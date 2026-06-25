import { test, expect } from '@playwright/test';
import { collectConsoleErrors } from './helpers';

// OL3421846M is present in the dev DB seed data (referenced in lists unit tests).
// OL7353617M is a known production edition (The Fellowship of the Ring).
const EDITION_URL = process.env.OL_BASE_URL?.startsWith('https')
    ? '/books/OL7353617M'
    : '/books/OL3421846M';

const skipIfNotFound = async ({ page }: { page: import('@playwright/test').Page }) => {
    const response = await page.goto(EDITION_URL);
    if (response?.status() === 404) {
        test.skip(true, 'Edition not in this environment\'s DB — skipping');
    }
};

test.describe('Edition page @smoke', () => {
    test('loads with book title in heading', async ({ page }) => {
        const errors = collectConsoleErrors(page);
        const response = await page.goto(EDITION_URL);
        test.skip(response?.status() === 404, 'Edition not in this environment\'s DB');
        // h1.work-title is the book title heading in type/edition/title_and_author.html
        const title = page.locator('h1.work-title').filter({ visible: true });
        await expect(title).toBeVisible();
        const text = await title.textContent();
        expect(text?.trim().length).toBeGreaterThan(0);
        expect(errors()).toHaveLength(0);
    });

    test('shows work details section', async ({ page }) => {
        await skipIfNotFound({ page });
        await expect(page.locator('.workDetails')).toBeVisible();
    });

    test('renders the edition cover or placeholder', async ({ page }) => {
        await skipIfNotFound({ page });
        // .editionCover is the cover container in type/edition/view.html
        const cover = page.locator('.editionCover').first();
        await expect(cover).toBeAttached();
    });

    test('has a link back to the parent work', async ({ page }) => {
        await skipIfNotFound({ page });
        // The edition page links to its parent work via .work-title-and-author
        const workLink = page.locator('.work-title-and-author a[href*="/works/"]').first();
        await expect(workLink).toBeAttached();
    });

    test('shows edition metadata (publisher, date, or pages)', async ({ page }) => {
        await skipIfNotFound({ page });
        // .edition-omniline contains publisher, publish date, page count
        const omniline = page.locator('.edition-omniline');
        await expect(omniline).toBeAttached();
    });

    test('unknown edition shows a page (not 500)', async ({ page }) => {
        const response = await page.goto('/books/OL999999999M');
        expect(response?.status()).not.toBe(500);
        await expect(page.locator('#header-bar').first()).toBeVisible();
    });

    test('mobile: book title is visible without horizontal overflow', async ({ page, isMobile }) => {
        if (!isMobile) test.skip();
        const response = await page.goto(EDITION_URL);
        test.skip(response?.status() === 404, 'Edition not in this environment\'s DB');
        const title = page.locator('h1.work-title').filter({ visible: true });
        await expect(title).toBeVisible();
        const box = await title.boundingBox();
        expect(box).not.toBeNull();
        const viewport = page.viewportSize();
        expect(box!.x + box!.width).toBeLessThanOrEqual(viewport!.width + 1);
    });
});
