/**
 * Vite config for Vue components. (for Lit components see vite-lit.config.mjs)
 */
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { writeFileSync, readdirSync } from 'fs';
import { join } from 'path';


const BUILD_DIR = process.env.BUILD_DIR || 'static/build/components';

const componentNames = getComponentNames();
componentNames.forEach(generateViteEntryFile)

const buildInput = {};
componentNames.forEach(name => { buildInput[name] = getTemporaryVueInputPath(name) });

export default defineConfig({
    plugins: [
        vue({ customElement: true })
    ],
    build: {
        // Keep syntax compatible with our supported floor (see browserslist in
        // package.json). Without this, Vite defaults to 'baseline-widely-available'
        // (~Safari 16), which would ship untranspiled ES2021+ syntax.
        target: ['es2019', 'safari13'],
        outDir: join(BUILD_DIR, '/production'),
        rollupOptions: {
            input: buildInput,
            output: {
                entryFileNames: 'ol-[name].js',
                format: 'es' // for browser only builds (not NodeJS)
            },
        },
    },
});

/**
 * Retrieves the names of Vue components in the specified directory.
 * Scans the './openlibrary/components' directory for files with a '.vue' extension,
 * and returns an array of component names without the extension.
 *
 * @returns {string[]} An array of component names, e.g., ['BarcodeScanner', 'BulkSearch'].
 */
function getComponentNames() {
    const files = readdirSync('./openlibrary/components');
    return files.filter(name => name.includes('.vue')).map(name => name.replace('.vue', ''));
}

function getTemporaryVueInputPath(componentName) {
    return join(BUILD_DIR, `tmp-${componentName}.js`)
}

/**
 * Generates a temporary entry file for Vite to build the web component
 * @param {string} componentName - Name of the Vue component to build
 * @throws {Error} If file creation fails
 */
function generateViteEntryFile(componentName) {
    const componentsPath = '../../../openlibrary/components';
    const template = `
import { createWebComponentSimple } from '${componentsPath}/rollupInputCore.js';
import rootComponent from '${componentsPath}/${componentName}.vue';
createWebComponentSimple(rootComponent, '${componentName}');`;

    try {
        writeFileSync(getTemporaryVueInputPath(componentName), template);
    } catch (error) {
        console.error(`Failed to generate Vite entry file: ${error.message}`);
        process.exit(1);
    }
}
