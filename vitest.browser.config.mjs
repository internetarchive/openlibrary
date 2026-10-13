import { defineConfig } from 'vitest/config';
import { playwright } from '@vitest/browser-playwright';
import vue from '@vitejs/plugin-vue';

/**
 * Vitest Browser Mode: component tests that need the things jsdom only
 * simulates — a real layout engine, real ResizeObserver/IntersectionObserver,
 * the real Popover/Dialog top layer, and trusted input events.
 *
 * A separate config rather than a `projects` entry keeps `npm run test:js` a
 * fast jsdom run with no browser dependency; this one pays Playwright's
 * Chromium startup cost and needs its binary installed.
 *
 * Tests live in `tests/browser/` and are named `*.browser.test.js`, which the
 * jsdom config's `include` globs never match, so no test runs twice.
 */
export default defineConfig({
    // Compiles .vue single-file components (only .vue files are affected, so
    // the Lit suites are untouched).
    plugins: [vue()],
    // Pre-bundle deps reached only through covers.js's dynamic import. On a cold
    // cache (CI) Vite otherwise finds them mid-run and reloads, failing the import.
    optimizeDeps: {
        include: [
            'jquery',
            'jquery-ui/ui/version',
            'jquery-ui/ui/widget',
            'jquery-ui/ui/widgets/mouse',
            'jquery-ui/ui/data',
            'jquery-ui/ui/scroll-parent',
            'jquery-ui/ui/disable-selection',
            'jquery-ui/ui/widgets/sortable',
            'jquery-ui-touch-punch',
        ],
    },
    test: {
        include: ['tests/browser/**/*.browser.test.js'],
        browser: {
            enabled: true,
            provider: playwright(),
            headless: true,
            instances: [{ browser: 'chromium' }],
            viewport: { width: 1280, height: 800 },
        },
    },
});
