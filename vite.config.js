// vite.config.js
import vue from '@vitejs/plugin-vue'

export default {
    root: 'openlibrary',
    build: {
        lib: {
            entry: 'components/vue3/index.js',
            name: 'Components',
            fileName: 'components',
            formats: ['es']
        },
        outDir: '../static/build/components/vue3',
        emptyOutDir: true,
        cssCodeSplit: true,
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
            template: {
                customElements: true,
                compilerOptions: {
                    // treat all tags with a dash as custom elements
                    isCustomElement: (tag) => tag.includes('ol-')
                }
            }
        })
    ]
}
