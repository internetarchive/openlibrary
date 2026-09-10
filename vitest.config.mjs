import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['tests/unit/js/setup.js'],
    include: [
      'openlibrary/components/__tests__/**/*.test.js',
      'tests/unit/js/**/*.test.js',
    ],
    // Vitest default pool creates a fresh jsdom environment per file (~2x slower).
    // 'vmThreads' creates it once per worker and gives Jest-parity performance.
    // Note: this shares the environment (incl. customElements registry) across files on a worker;
    // each self-registering component module must stay imported by at most one test file.
    pool: 'vmThreads',
    coverage: {
      provider: 'v8',
      include: ['openlibrary/plugins/openlibrary/js/**/*.js'],
      thresholds: {
        branches: 14,
        functions: 11,
        lines: 14,
        statements: 14,
      },
    },
  },
});
