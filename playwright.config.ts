import { defineConfig, devices } from '@playwright/test';

/**
 * Run tests against a local Docker instance:
 *   cd ~/Projects/openlibrary-<slug>
 *   OL_MOUNT_DIR="$(pwd)" docker compose up -d web infobase db memcached home covers
 *   npx playwright install chromium
 *   npm run test:e2e
 */
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],

  use: {
    baseURL: process.env.OL_BASE_URL || 'http://localhost:8080',
    // Collect browser console errors for assertion in tests
    // (each test sets up its own listener)
    headless: true,
  },

  projects: [
    {
      name: 'desktop',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1280, height: 800 },
      },
    },
    {
      name: 'mobile',
      use: {
        // Use Pixel 5 (Chromium) instead of iPhone 12 (WebKit).
        // WebKit headless launch times out on some macOS systems; Chromium is more reliable.
        ...devices['Pixel 5'],
        viewport: { width: 390, height: 844 },
      },
    },
  ],
});
