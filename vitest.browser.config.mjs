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
    // Pre-bundle Lit and its directive subpaths. Vitest's dependency scan
    // misses some of these (e.g. OlCoverEditor's class-map import) and then
    // discovers them mid-run, which makes Vite optimize them and reload the
    // browser page. That reload re-runs the active file and leaves its DOM
    // behind, so the next file (TestingEnvironment) sees duplicated rows.
    // Listing them here keeps the optimized graph stable from the first test.
    optimizeDeps: {
        include: [
            'lit',
            'lit/directives/class-map.js',
            'lit/directives/if-defined.js',
            'lit/directives/repeat.js',
            'lit/directives/style-map.js',
            'lit/directives/unsafe-html.js',
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
