// vite.config.js
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
    root: 'openlibrary',
    build: {
        lib: {
            entry: 'components/index.js',
            name: 'ol-library-explorer',
            fileName: 'ol-library-explorer',
            formats: ['es'],
        },
        outDir: '../static/build/components',
        emptyOutDir: true,
        cssCodeSplit: true,
        minify: true,
    },
    resolve: {
        extensions: ['.js', '.json', '.vue'],
    },
    rollupOptions: {
        // make sure to externalize deps that shouldn't be bundled
        // into your library
        external: ['vue'],
        output: {
            // Provide global variables to use in the UMD build
            // for externalized deps
            globals: {
                vue: 'Vue',
            }
        },
    },
    plugins: [
        vue({
            customElement: true,
        })
    ]
})
