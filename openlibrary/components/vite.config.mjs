/* eslint-env node, es6 */
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { writeFileSync } from 'fs';
import { join } from 'path';

const COMPONENT_NAME = process.env.COMPONENT?.replace('.vue', '');
if (!COMPONENT_NAME) {
    throw new Error(
        'Component name not specified in environment variable.\n' +
        'Usage: COMPONENT=ComponentName npx vite build'
    );
}

const BUILD_DIR = './static/build';
const PRODUCTION_DIR = join(BUILD_DIR, 'components/production');
const COMPONENT_PATH = '../../openlibrary/components';

// Generate temporary build file
generateViteEntryFile(COMPONENT_NAME);

export default defineConfig({
    plugins: [vue({ customElement: true })],
    build: {
        outDir: PRODUCTION_DIR,
        emptyOutDir: false, // Preserve existing files since we build components individually
        rollupOptions: {
            input: join(BUILD_DIR, `vue-tmp-${COMPONENT_NAME}.js`),
            output: {
                entryFileNames: `ol-${COMPONENT_NAME}.js`,
                inlineDynamicImports: true,
                format: 'iife' // use iife to support old browsers without type="module"
            },
        },
    },
});

/**
 * Generates a temporary entry file for Vite to build the web component
 * @param {string} componentName - Name of the Vue component to build
 * @throws {Error} If file creation fails
 */
function generateViteEntryFile(componentName) {
    const template = `
import { createWebComponentSimple } from "${COMPONENT_PATH}/rollupInputCore.js";
import rootComponent from '${COMPONENT_PATH}/${componentName}.vue';
createWebComponentSimple(rootComponent, '${componentName}');`;

    try {
        writeFileSync(join(BUILD_DIR, `vue-tmp-${componentName}.js`), template);
    } catch (error) {
        // eslint-disable-next-line no-console
        console.error(`Failed to generate Vite entry file: ${error.message}`);
        process.exit(1);
    }
}
