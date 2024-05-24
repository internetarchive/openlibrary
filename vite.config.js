// vite.config.js
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
    plugins: [vue()],
    build: {
        lib: {
            entry: './openlibrary/components/index.js',
            name: 'LibraryExplorer',
            fileName: () => 'index.js',
            formats: ['es'],
        },
        outDir: './static/build/components/ol-library-explorer/',
        emptyOutDir: true,
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
})
