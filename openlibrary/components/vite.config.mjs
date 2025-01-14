/* eslint-env node, es6 */
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import fs from 'fs';


const COMPONENT = process.env.COMPONENT?.replace('.vue', '');
if (!COMPONENT) {
    throw new Error('component was not specified in the environment variable. \n' +
        'Try: component=BarcodeScanner npx vite build'
    );
}

// Directory where we store the temporary vite input files
// This is because vite doesn't support passing params to input files
const INPUT_JS_DIR = './static/build';
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
import { createWebComponentSimple } from "../../openlibrary/components/rollupInputCore.js"
import rootComponent from '../../openlibrary/components/${componentName}.vue';
createWebComponentSimple(rootComponent, '${componentName}');`;

    try {
        fs.writeFileSync(`${dir}/vue-tmp-${componentName}.js`, template);
    } catch (error) {
        // eslint-disable-next-line no-console
        console.error(`Failed to generate component file: ${error.message}`);
        process.exit(1); // Exit the process with an error code
    }
}
