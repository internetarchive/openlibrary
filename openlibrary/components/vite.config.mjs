import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
// import cssInjectedByJsPlugin from 'vite-plugin-css-injected-by-js';

const COMPONENT = process.env.COMPONENT;
if (!COMPONENT) {
    throw new Error('component was not specified in the environment variable. \n' +
        'Try: component=BarcodeScanner npx vite build'
    );
}
// TODO: I want to call the generate file here and have it generate in the moment we call this config.

export default defineConfig({
    plugins: [vue(
        { customElement: true, }
    )],
    build: {
        outDir: './static/build/components/production',
        emptyOutDir: false, // don't empty the out dir because we run this config once for each component
        rollupOptions: {
            input: `./openlibrary/components/build/${COMPONENT}.js`,
            output: {
                entryFileNames: `ol-${COMPONENT}.js`,
                inlineDynamicImports: true,
            },
        },
    },
}
);
