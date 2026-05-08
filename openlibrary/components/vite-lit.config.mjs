/**
 * Vite config for Lit web components. (for Vue components see vite.config.mjs)
 *
 * This creates a bundled build of all Lit components in a single file.
 *
 * Output:
 * - ol-components.js (ES modules)
 */

import { defineConfig } from 'vite';
import { join } from 'path';

const BUILD_DIR = process.env.BUILD_DIR || 'static/build/components';

export default defineConfig({
    build: {
        // Output directory for built files
        outDir: join(BUILD_DIR, '/production'),

        // Rollup-specific options
        rollupOptions: {
            input: {
                'ol-components': 'openlibrary/components/lit/index.js'
            },
            output: {
                // Output filename pattern
                entryFileNames: '[name].js',

                // Ensure we're building for browsers, not Node.js
                format: 'es'
            }
        },

        // Minify the output
        minify: 'terser',

        // Generate source maps for debugging
        sourcemap: true
    }
});
