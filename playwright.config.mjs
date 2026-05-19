// @ts-check
import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for header search UX visual/E2E tests.
 * Requires Docker to be running on port 8080:
 *   OL_MOUNT_DIR=$(pwd) docker compose up -d web
 *
 * These tests are intentionally manual-only — they require a running
 * OL Docker instance and are not wired into `npm run test` (JS unit CI).
 * Run with: npx playwright test
 */
export default defineConfig({
    testDir: './tests/e2e',
    timeout: 30000,
    fullyParallel: false,
    reporter: [['html', { outputFolder: 'tests/e2e/reports', open: 'never' }]],
    use: {
        baseURL: 'http://localhost:8080',
        screenshot: 'only-on-failure',
    },
    projects: [
        {
            name: 'desktop',
            use: { ...devices['Desktop Chrome'] },
        },
        {
            name: 'mobile',
            use: { ...devices['iPhone 12'] },
        },
    ],
});
