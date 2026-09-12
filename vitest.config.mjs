import { defineConfig } from 'vitest/config';

export default defineConfig({
  // Tests import everything explicitly through vite-node, so dependency
  // pre-bundling and its project-wide scan are unnecessary. The __vitest_vm__
  // environment (used by the vmThreads pool) is exempt from Vitest's own
  // optimizer normalization, so it must opt out of discovery here — otherwise
  // the scan trips over openlibrary/components/dev/index.html's virtual
  // `_dev.js` module (resolved only by that directory's dev-server config).
  optimizeDeps: {
    noDiscovery: true,
  },
  environments: {
    __vitest_vm__: {
      optimizeDeps: {
        noDiscovery: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['tests/unit/js/setup.js'],
    // Hide console output from passing tests (e.g. ol.js's per-PUT success
    // logging); failing tests still print theirs for debugging.
    // Override with `vitest run --silent=false` when debugging.
    silent: 'passed-only',
    include: [
      'openlibrary/components/__tests__/**/*.test.js',
      'tests/unit/js/**/*.test.js',
    ],
    // Vitest default pool creates a fresh jsdom environment per file (~2x slower).
    // 'vmThreads' creates it once per worker and gives Jest-parity performance.
    // Note: this shares the environment (incl. customElements registry) across files on a worker;
    // each self-registering component module must stay imported by at most one test file.
    pool: 'vmThreads',
    onConsoleLog(msg, type) {
      // Lit prints this once per module graph that imports it; under vmThreads
      // that means once per test file. Expected in a test environment.
      if (type === 'stderr' && msg.includes('Lit is in dev mode')) {
        return false;
      }
      // OlPopover/OlCarousel drive multi-phase open/close animations by setting
      // reactive state in updated() and after updateComplete (off-screen render
      // → measure → position → enter). Each phase must paint before the next,
      // so the follow-up update is deliberate — the exact exception Lit's
      // change-in-update warning carves out. Fixing it means redesigning the
      // animation lifecycle; until then the warning is pure noise.
      if (type === 'stderr' && msg.includes('change-in-update')) {
        return false;
      }
    },
  },
});
