/* eslint-env node, es6 */
import { defineConfig } from 'vite';
import legacy from '@vitejs/plugin-legacy';
import { readdirSync } from 'fs';
import { join } from 'path';

const BUILD_DIR = process.env.BUILD_DIR || 'static/build/components';

/**
 * Get all Lit component files from the components-lit directory
 * Example output: { 'ol-button': './openlibrary/components-lit/ol-button.js', 'ol-input': './openlibrary/components-lit/ol-input.js' }
 * @returns {Object} Input object mapping component names to file paths
 */
function getLitComponentInputs() {
    const files = readdirSync('./openlibrary/components-lit');
    const buildInput = {};

    files
        .filter(name => name.endsWith('.js') && !name.startsWith('vite.config'))
        .forEach(filename => {
            const componentName = filename.replace('.js', '');
            buildInput[componentName] = join('./openlibrary/components-lit', filename);
        });

    return buildInput;
}

export default defineConfig({
    plugins: [
        legacy({ targets: ['defaults', 'not IE 11'] })
    ],
    build: {
        outDir: join(BUILD_DIR, '/production'),
        rollupOptions: {
            input: getLitComponentInputs(),
            output: {
                entryFileNames: '[name].js',
                format: 'es' // ES modules for browser
            },
        },
    },
});

