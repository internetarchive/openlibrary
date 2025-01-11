/* eslint-env node, es6 */
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import fs from 'fs';
// import cssInjectedByJsPlugin from 'vite-plugin-css-injected-by-js';


const COMPONENT = process.env.COMPONENT?.replace('.vue', '');
if (!COMPONENT) {
    throw new Error('component was not specified in the environment variable. \n' +
        'Try: component=BarcodeScanner npx vite build'
    );
}

// Directory where we store the temporary vite input files
// This is because vite doesn't support passing params to input files
const INPUT_JS_DIR = '/openlibrary/openlibrary/static/build';
const COMPONENT_SOURCE_DIR = '/openlibrary/openlibrary/components';
generateComponentFile(COMPONENT, INPUT_JS_DIR);

export default defineConfig({
    plugins: [vue({ customElement: true })],
    build: {
        outDir: './static/build/components/production',
        emptyOutDir: false, // don't empty the out dir because we run this config once for each component
        rollupOptions: {
            input: `${INPUT_JS_DIR}/vue-tmp-${COMPONENT}.js`,
            output: {
                entryFileNames: `ol-${COMPONENT}.js`,
                inlineDynamicImports: true,
            },
        },
    },
});

function generateComponentFile(componentName, dir) {
    const template = `
import { createWebComponentSimple } from "${COMPONENT_SOURCE_DIR}/rollupInputCore.js"
import rootComponent from '${COMPONENT_SOURCE_DIR}/${componentName}.vue';
createWebComponentSimple(rootComponent, '${componentName}');`;

    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(`${dir}/vue-tmp-${componentName}.js`, template);
}
