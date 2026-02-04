/* eslint-env node, es6 */
/**
 * Vite config for Lit web components. (for Vue components see vite.config.mjs)
 *
 * This creates a bundled build of all Lit components in a single file
 * with legacy browser support via polyfills.
 *
 * Output:
 * - ol-components.js (modern ES modules)
 * - ol-components-legacy.js (transpiled for older browsers)
 */

import { defineConfig } from 'vite';
import legacy from '@vitejs/plugin-legacy';
import { join } from 'path';

const BUILD_DIR = process.env.BUILD_DIR || 'static/build/components';

export default defineConfig({
    plugins: [
        // Provides legacy browser support
        // Creates both modern and legacy builds
        legacy({
            targets: ['defaults', 'not IE 11'],
            // Generate polyfills for older browsers
            modernPolyfills: true
        })
    ],
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

