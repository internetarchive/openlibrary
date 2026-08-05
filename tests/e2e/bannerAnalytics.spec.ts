import { test, expect } from '@playwright/test';
import { collectConsoleErrors } from './helpers';

/**
 * Guards the wiring that has now broken three times (PR #13038, issue #13261,
 * and the Book Preview / Search Inside fix): a banner dismissal must reach
 * Matomo's `_paq` queue.
 *
 * Athena's `archive_analytics.ol_send_event_ping` does not forward into Matomo,
 * so a unit test that mocks the analytics module cannot catch a regression here
 * — it would pass against either implementation. Only asserting against the
 * real queue, through the real bundle, distinguishes them. Verified by reverting
 * the fix: this spec fails on the Athena-only version and passes on the fixed
 * one.
 */

// The shape queueAction() writes in js/utils.js.
const PENDING_ACTION = encodeURIComponent(JSON.stringify({
    action: 'follow',
    name: 'Test Author',
    url: '/authors/OL1A',
    type: 'author',
}));

test.describe('Banner dismissal analytics', () => {
    test('reports PreserveIntent|Dismiss to the Matomo queue', async ({ page, context, baseURL }) => {
        const errors = collectConsoleErrors(page);

        // The banner only renders for a logged-in patron (account/view.html).
        // Authenticate via the JSON API rather than the form: `context.request`
        // shares the browser's cookie jar, so the session lands in the page.
        const login = await context.request.post('/account/login.json', {
            headers: { 'Content-Type': 'application/json' },
            data: { username: 'openlibrary', password: 'openlibrary' },
        });
        expect(login.status()).toBe(200);

        await context.addCookies([
            { name: 'pending_action', value: PENDING_ACTION, url: baseURL! },
        ]);

        // Record every Matomo push. Installed before app JS so head.html's
        // `window._paq || []` adopts this array rather than replacing it.
        await page.addInitScript(() => {
            const spy: unknown[][] = [];
            Object.assign(window, { __paqSpy: spy });
            const queue: unknown[] = (window as { _paq?: unknown[] })._paq || [];
            Object.assign(window, { _paq: queue });
            const original = queue.push.bind(queue);
            queue.push = (...args: unknown[]) => {
                spy.push(args[0] as unknown[]);
                return original(...args);
            };
        });

        await page.goto('/account/books');

        const banner = page.locator('#pending-action-container');
        await expect(banner).toBeVisible();

        await banner.locator('.ol-banner__close').click();

        await expect
            .poll(() => page.evaluate(() => (window as { __paqSpy?: unknown[][] }).__paqSpy))
            .toContainEqual(['trackEvent', 'PreserveIntent', 'Dismiss']);

        expect(errors()).toHaveLength(0);
    });
});
