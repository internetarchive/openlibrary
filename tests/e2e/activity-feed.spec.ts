import { expect, test } from '@playwright/test';
import { collectConsoleErrors } from './helpers';

/**
 * The social activity feed (#10242).
 *
 * Three previous attempts at this feature were closed without anyone verifying
 * a real, populated, correctly-styled feed end to end. These tests assert the
 * populated state specifically -- an empty feed passing as "it renders" is the
 * exact failure mode to guard against -- and capture screenshots of every
 * layout variant at both widths for design review.
 *
 * Requires seeded social data:
 *   docker compose run --rm home python scripts/dev-instance/seed_social_feed.py
 *
 * A local dev stack has no proxy from web.py to FastAPI, so the feed endpoint's
 * origin is passed explicitly. In production nginx routes /api/internal itself.
 */

const FEED_API = process.env.OL_FEED_API || 'http://localhost:18080/api/internal/activity/feed.json';
const VARIANT_COUNT = 11;

function galleryUrl(design?: number): string {
    const params = new URLSearchParams({ api: FEED_API, scope: 'public' });
    if (design) params.set('design', String(design));
    return `/developers/design/activity-feed?${params}`;
}

/** Wait for a feed element to finish loading and report what it rendered. */
async function feedItemCount(page, index = 0): Promise<number> {
    const feed = page.locator('ol-social-feed').nth(index);
    await expect(feed.locator('.feed')).toBeVisible({ timeout: 15_000 });
    return feed.locator('.card').count();
}

test.describe('activity feed design gallery', () => {
    test('renders every variant with populated data', async ({ page }) => {
        const errors = collectConsoleErrors(page);
        await page.goto(galleryUrl());

        const feeds = page.locator('ol-social-feed');
        await expect(feeds).toHaveCount(VARIANT_COUNT);

        // Every variant must actually show events. A variant that silently
        // renders nothing is the failure this whole test exists to catch.
        for (let i = 0; i < VARIANT_COUNT; i++) {
            expect(await feedItemCount(page, i), `variant ${i + 1} rendered no cards`).toBeGreaterThan(0);
        }

        expect(errors()).toHaveLength(0);
    });

    test('cards carry a book, a patron, and a next action', async ({ page }) => {
        await page.goto(galleryUrl(1));
        const feed = page.locator('ol-social-feed').first();
        await expect(feed.locator('.feed')).toBeVisible({ timeout: 15_000 });

        const card = feed.locator('.card').first();
        await expect(card.locator('.handle')).toBeVisible();
        await expect(card.locator('.title')).toBeVisible();
        await expect(card.locator('.btn--primary')).toBeVisible();

        // Covers come off the Solr record's cover id. An earlier attempt at this
        // feature guessed work-OLID cover URLs and rendered the wrong books.
        const cover = card.locator('.cover img').first();
        await expect(cover).toHaveAttribute('src', /covers\.openlibrary\.org\/b\/id\/\d+/);
        // Poll rather than sampling once: the cover comes from the CDN and may
        // not have decoded yet when the card first paints.
        await expect
            .poll(() => cover.evaluate((img: HTMLImageElement) => img.naturalWidth), { timeout: 15_000 })
            .toBeGreaterThan(0);
    });

    test('follow button reflects pressed state', async ({ page }) => {
        await page.goto(galleryUrl(1));
        const feed = page.locator('ol-social-feed').first();
        await expect(feed.locator('.feed')).toBeVisible({ timeout: 15_000 });

        const follow = feed.locator('.follow').first();
        await expect(follow).toHaveAttribute('aria-pressed', 'false');
    });

    test('every link and control in the feed has an accessible name', async ({ page }) => {
        // Avatar-only links and the list-cover fan are images with no text, so
        // they need an explicit label. axe flagged 66 of these before they got one.
        await page.goto(galleryUrl());
        await expect(page.locator('ol-social-feed .feed').first()).toBeVisible({ timeout: 15_000 });

        const unnamed = await page.evaluate(() => {
            const bad: string[] = [];
            document.querySelectorAll('ol-social-feed').forEach((host: any) => {
                const variant = host.getAttribute('variant');
                host.shadowRoot.querySelectorAll('a, button').forEach((el: Element) => {
                    const name = (el.getAttribute('aria-label') || el.textContent || '').trim()
                        || [...el.querySelectorAll('img')].map((img) => img.getAttribute('alt')).join('').trim();
                    if (!name) bad.push(`v${variant} <${el.tagName.toLowerCase()} class="${el.className}">`);
                });
            });
            return bad;
        });

        expect(unnamed, 'links/buttons without an accessible name').toEqual([]);
    });

    test('navigating between variants keeps the feed populated', async ({ page }) => {
        // The endpoint override lives in the query string, so every link on the
        // page has to carry it. Drop it and each variant renders empty with
        // nothing on screen to say why.
        await page.goto(galleryUrl());
        await expect(page.locator('ol-social-feed .feed').first()).toBeVisible({ timeout: 15_000 });

        await page.getByRole('link', { name: '5. Social thread' }).click();
        await expect(page.locator('ol-social-feed')).toHaveCount(1);
        expect(await feedItemCount(page), 'feed emptied after clicking a variant chip').toBeGreaterThan(0);

        await page.getByRole('link', { name: 'scope: public' }).click();
        expect(await feedItemCount(page), 'feed emptied after clicking a scope chip').toBeGreaterThan(0);

        await page.getByRole('link', { name: 'All variants' }).click();
        await expect(page.locator('ol-social-feed')).toHaveCount(VARIANT_COUNT);
        expect(await feedItemCount(page), 'feed emptied after returning to all ten').toBeGreaterThan(0);
    });

    test('the showcase row pages and refreshes', async ({ page }) => {
        // Variant 11 is the only one with controls: three across, refresh the
        // whole row, and turn to older activity rather than scrolling forever.
        await page.goto(galleryUrl(11));
        const feed = page.locator('ol-social-feed').first();
        await expect(feed.locator('.feed')).toBeVisible({ timeout: 15_000 });

        await expect(feed.locator('.card')).toHaveCount(3);
        // Every card type should be on screen, or the row cannot be judged.
        const types = await feed.locator('.card').evaluateAll((cards) => cards.map((c) => c.dataset.type));
        expect(new Set(types).size).toBeGreaterThan(1);

        const newer = feed.getByRole('button', { name: 'Newer activity' });
        await expect(newer).toBeDisabled();

        await feed.getByRole('button', { name: 'Older activity' }).click();
        await expect(newer).toBeEnabled();
        expect(await feed.locator('.card').count()).toBeGreaterThan(0);

        await feed.getByRole('button', { name: 'Refresh activity' }).click();
        await expect(feed.locator('.card').first()).toBeVisible();
    });

    test('captures every variant for review', async ({ page }, testInfo) => {
        for (let design = 1; design <= VARIANT_COUNT; design++) {
            await page.goto(galleryUrl(design));
            await expect(page.locator('ol-social-feed .feed')).toBeVisible({ timeout: 15_000 });
            // Covers load from the CDN; let them land before capturing.
            await page.waitForLoadState('networkidle');
            const shot = await page.locator('.feed-gallery__variant').screenshot();
            await testInfo.attach(`variant-${design}-${testInfo.project.name}`, {
                body: shot,
                contentType: 'image/png',
            });
        }
    });

    test('@mobile every variant holds up at a phone width', async ({ page }) => {
        const errors = collectConsoleErrors(page);
        await page.goto(galleryUrl());

        for (let i = 0; i < VARIANT_COUNT; i++) {
            expect(await feedItemCount(page, i), `variant ${i + 1} rendered no cards`).toBeGreaterThan(0);
        }

        // Nothing may push the page into horizontal scroll on a phone.
        const overflow = await page.evaluate(
            () => document.documentElement.scrollWidth - document.documentElement.clientWidth
        );
        expect(overflow, 'page scrolls horizontally on mobile').toBeLessThanOrEqual(1);

        expect(errors()).toHaveLength(0);
    });

    test('@mobile captures every variant for review', async ({ page }, testInfo) => {
        for (let design = 1; design <= VARIANT_COUNT; design++) {
            await page.goto(galleryUrl(design));
            await expect(page.locator('ol-social-feed .feed')).toBeVisible({ timeout: 15_000 });
            await page.waitForLoadState('networkidle');
            const shot = await page.locator('.feed-gallery__variant').screenshot();
            await testInfo.attach(`variant-${design}-${testInfo.project.name}`, {
                body: shot,
                contentType: 'image/png',
            });
        }
    });
});
