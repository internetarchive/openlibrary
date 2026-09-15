import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';

// Console messages that are infrastructure/environment noise, not JS bugs.
// - "Failed to load resource:" — fetch/XHR calls that hit unavailable external services
//   (e.g. IA availability API, CDN assets) in local dev or test environments.
// - "violates the following Content Security Policy" — CSP violations for archive.org
//   iframes that are blocked on localhost but not on openlibrary.org.
const CONSOLE_NOISE_PATTERNS = [
    'Failed to load resource:',
    'violates the following Content Security Policy',
];

/**
 * Attach a console-error collector to a page.
 * Returns a getter for all JS errors collected so far (network resource errors excluded).
 *
 * Usage:
 *   const errors = collectConsoleErrors(page);
 *   await page.goto('/');
 *   expect(errors()).toHaveLength(0);
 */
export function collectConsoleErrors(page: Page): () => string[] {
    const errors: string[] = [];
    page.on('console', msg => {
        if (msg.type() === 'error') {
            const text = msg.text();
            if (!CONSOLE_NOISE_PATTERNS.some(pat => text.includes(pat))) {
                errors.push(text);
            }
        }
    });
    page.on('pageerror', err => errors.push(err.message));
    return () => errors;
}

/**
 * Credentials for logged-in tests.
 *
 * Default to the dev stack's seeded patron (see CLAUDE.md and login.html's
 * LOCAL_DEV hint). Against any other host set OL_E2E_USERNAME /
 * OL_E2E_PASSWORD (or OL_E2E_S3_ACCESS / OL_E2E_S3_SECRET) for the session
 * helper, plus OL_E2E_EMAIL for tests that drive the login form. Without
 * credentials, logged-in tests skip.
 */
const isLocal = !process.env.OL_BASE_URL || /localhost|127\.0\.0\.1/.test(process.env.OL_BASE_URL);
export const E2E_USERNAME = process.env.OL_E2E_USERNAME || (isLocal ? 'openlibrary' : '');
export const E2E_PASSWORD = process.env.OL_E2E_PASSWORD || (isLocal ? 'openlibrary' : '');
export const E2E_EMAIL = process.env.OL_E2E_EMAIL || (isLocal ? 'openlibrary@example.com' : '');
const E2E_S3 = process.env.OL_E2E_S3_ACCESS && process.env.OL_E2E_S3_SECRET
    ? { access: process.env.OL_E2E_S3_ACCESS, secret: process.env.OL_E2E_S3_SECRET }
    : null;

/** True when this environment has credentials for logged-in tests. */
export const HAS_CREDENTIALS = Boolean(E2E_S3 || E2E_USERNAME);

/**
 * Log the page's browser context in via the JSON login endpoint.
 *
 * `page.request` shares the context's cookie jar, so the session cookie is
 * in place for the next `page.goto()` without ever driving the login form.
 * Skips the test when no credentials are available for this environment.
 *
 * Usage:
 *   test.beforeEach(({ page }) => login(page));
 */
export async function login(page: Page): Promise<void> {
    test.skip(!HAS_CREDENTIALS, 'No credentials for this environment — set OL_E2E_USERNAME / OL_E2E_PASSWORD');
    const response = await page.request.post('/account/login.json', {
        data: E2E_S3 ?? { username: E2E_USERNAME, password: E2E_PASSWORD },
    });
    expect(response.status(), `login.json failed: ${await response.text()}`).toBe(200);
}
