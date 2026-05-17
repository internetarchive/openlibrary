// @ts-check
import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for header search UX visual/E2E tests.
 * Requires Docker to be running on port 8080:
 *   OL_MOUNT_DIR=$(pwd) docker compose up -d web
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
