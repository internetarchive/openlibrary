import { test, expect, type Page } from '@playwright/test';
import { collectConsoleErrors } from './helpers';

/**
 * The shelf button on search results, end to end.
 *
 * Unit tests cover the component and the page-level state owner separately.
 * What only shows up here is the seam between them: attributes are rendered by
 * the server, the element upgrades later, and a click has to reach the server
 * *and* come back to the label. Both bugs found while building this lived in
 * that seam.
 */

const SEARCH_URL = '/search?q=the';
const SHELF_BUTTON = 'ol-shelf-button[work-key]';

async function gotoResults(page: Page) {
    await page.goto(SEARCH_URL);
    const count = await page.locator('.searchResultItem').count();
    test.skip(count === 0, 'No Solr data indexed in this environment');
    await page.locator(SHELF_BUTTON).first().waitFor({ timeout: 10_000 });
}

/**
 * The dev-environment test patron. Skips when it is not provisioned.
 * The username field is `type="email"`, so the bare username would fail HTML5
 * validation and never submit.
 */
async function login(page: Page) {
    await page.goto('/account/login');
    await page.fill('input[name="username"]', 'openlibrary@example.com');
    await page.fill('input[name="password"]', 'openlibrary');
    await page.click('button[name="login"]');
    await page.waitForLoadState('networkidle');
    await page.goto(SEARCH_URL);
    test.skip(
        (await page.locator('ol-shelf-button[user-key]').count()) === 0,
        'No signed-in session — dev test patron unavailable',
    );
}

test.describe('Shelf button on search results, signed out @smoke', () => {
    test('renders without building a popover it cannot use', async ({ page }) => {
        const errors = collectConsoleErrors(page);
        await gotoResults(page);

        const button = page.locator(SHELF_BUTTON).first();
        await expect(button).toBeAttached();
        expect(await button.getAttribute('user-key')).toBeNull();

        // Signed out the trigger stands alone; the popover is never constructed.
        const hasPopover = await button.evaluate(
            el => !!el.shadowRoot?.querySelector('ol-book-actions'),
        );
        expect(hasPopover).toBe(false);
        expect(errors()).toHaveLength(0);
    });

    test('a click goes to login and remembers the intent', async ({ page }) => {
        await gotoResults(page);
        await page.locator(SHELF_BUTTON).first()
            .evaluate(el => (el.shadowRoot?.querySelector('.main') as HTMLElement)?.click());

        await page.waitForURL(/\/account\/login/, { timeout: 10_000 });
        const pending = (await page.context().cookies())
            .find(c => c.name === 'pending_action');
        expect(pending).toBeTruthy();
        expect(JSON.parse(decodeURIComponent(pending!.value))).toMatchObject({ type: 'book' });
    });
});

test.describe('Shelf button on search results, signed in', () => {
    test('a shelf change reaches the server and returns to the label', async ({ page }) => {
        await login(page);
        await gotoResults(page);

        const button = page.locator('ol-shelf-button[user-key]').first();
        const workKey = await button.getAttribute('work-key');
        const workOlid = workKey!.split('/').pop();

        // Start from a known state rather than whatever the patron already had.
        await page.evaluate(async (key) => {
            await fetch(`/works/${key}/bookshelves.json`, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: 'bookshelf_id=-1',
            });
        }, workOlid);
        await page.reload();
        await page.locator(SHELF_BUTTON).first().waitFor();

        const target = page.locator('ol-shelf-button[user-key]').first();
        await target.evaluate(el => (el.shadowRoot?.querySelector('.main') as HTMLElement)?.click());

        // The component is stateless — this only holds if the page applied the
        // change it reported.
        await expect.poll(
            () => target.evaluate(el => (el as HTMLElement & { shelf: number | null }).shelf),
            { timeout: 5_000 },
        ).toBe(1);

        const server = await page.evaluate(async (olid) => {
            const r = await fetch(`/reading-state.json?work_ids=${olid}`, { credentials: 'same-origin' });
            return r.json();
        }, workOlid);
        expect(server.shelves[workOlid!]).toBe(1);

        // Leave the patron's reading log as we found it.
        await page.evaluate(async (key) => {
            await fetch(`/works/${key}/bookshelves.json`, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: 'bookshelf_id=-1',
            });
        }, workOlid);
    });

    test('opening the popover does not select the row for the librarian toolbar', async ({ page }) => {
        await login(page);
        await gotoResults(page);

        // A click inside a shadow root retargets to the host, which is how the
        // ILE selection guard stopped seeing the button it was meant to ignore.
        await page.locator('ol-shelf-button[user-key]').first()
            .evaluate(el => (el.shadowRoot?.querySelector('.more') as HTMLElement)?.click());

        await expect.poll(
            () => page.locator('.ile-selected').count(),
            { timeout: 3_000 },
        ).toBe(0);
    });
});
