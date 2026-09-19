import { defineConfig, devices } from '@playwright/test';

/**
 * Run tests against the local Docker stack:
 *   make e2e-up      # stack, assets, Solr index, browser — once per session
 *   make test-e2e    # the suite; PLAYWRIGHT_ARGS="--headed search" to narrow
 *
 * Point them at another host with OL_BASE_URL. See tests/e2e/README.md.
 *
 * Projects are split so nothing runs twice: the core smoke tests run on the
 * `desktop` project only, while tests tagged `@mobile` (responsive-layout
 * checks) run on the `mobile` project only.
 *
 * visual.spec.ts stays opt-in behind OL_VISUAL=1 and must never run in CI:
 * full-page screenshots differ with platform font rendering, so a shared
 * baseline can only ever be right for the machine that recorded it.
 */
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,

  // A single dropped connection shouldn't fail someone's pull request. A pass
  // that needed a retry is still reported as flaky, so the signal survives.
  // Local runs stay at zero, where a flake is worth looking at immediately.
  retries: process.env.CI ? 2 : 0,
  forbidOnly: !!process.env.CI,

  reporter: [['list'], ['html', { open: 'never' }]],

  use: {
    baseURL: process.env.OL_BASE_URL || 'http://localhost:8080',
    headless: true,
    // Enough to diagnose a CI failure without a local repro.
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
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
