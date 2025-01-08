import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
// import cssInjectedByJsPlugin from 'vite-plugin-css-injected-by-js';

export default defineConfig({
    plugins: [vue(
        { customElement: true, }
    )],
    // define: {
    //     'process.env': {} // I don't think this is needed
    // },
    build: {
        outDir: './static/build/components/production',
        rollupOptions: {
            input: './openlibrary/components/main.js',
            output: {
                entryFileNames: 'ol-BarcodeScanner.js',
                inlineDynamicImports: true,
            },
        },
    },
}
);
