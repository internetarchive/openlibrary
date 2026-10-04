import { defineConfig, devices } from '@playwright/test';

/**
 * Run tests against a local Docker instance:
 *   OL_MOUNT_DIR="$(pwd)" docker compose up -d web infobase db memcached home covers
 *   npx playwright install chromium chromium-headless-shell
 *   npm run test:e2e
 *
 * Projects are split so nothing runs twice: the core smoke tests run on the
 * `desktop` project only, while tests tagged `@mobile` (responsive-layout
 * checks) run on the `mobile` project only.
 */
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],

  use: {
    baseURL: process.env.OL_BASE_URL || 'http://localhost:8080',
    headless: true,
  },

  projects: [
    {
      name: 'desktop',
      grepInvert: /@mobile/,
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1280, height: 800 },
      },
    },
    {
      name: 'mobile',
      grep: /@mobile/,
      use: {
        // Use Pixel 5 (Chromium) instead of iPhone 12 (WebKit).
        // WebKit headless launch times out on some macOS systems; Chromium is more reliable.
        ...devices['Pixel 5'],
        viewport: { width: 390, height: 844 },
      },
    },
  ],
});
