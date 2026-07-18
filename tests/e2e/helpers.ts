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
