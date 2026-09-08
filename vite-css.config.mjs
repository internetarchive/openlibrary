/*
 * Vite config to replace webpack.config.css.js
 * ============================================
 *
 * Compiles static/css entries (tokens, ol-components, page-*.css) to
 * standalone minified CSS files, mirroring webpack.config.css.js:
 *
 *   - entry: static/css/tokens.css, static/css/ol-components.css, static/css/page-*.css
 *   - @import resolution (css-loader import:true) -> Vite handles natively (postcss-import)
 *   - minification (css-minimizer-webpack-plugin) -> esbuild via cssMinify
 *   - url() passthrough (webpack url:false) -> see the publicDir comment below
 *   - no JS output (webpack's RemoveJSAssetsPlugin) -> Vite 8 omits the stub
 *     JS chunk for pure-CSS entries natively, so no plugin needed
 *
 * Usage:
 *   npx vite build -c vite-css.config.mjs
 *   npx vite build -c vite-css.config.mjs --watch --mode development  (readable dev output)
 *
 * Build output defaults to static/build/css. Set BUILD_DIR to override.
 */
import { defineConfig } from 'vite';
import { readdirSync } from 'fs';
import { resolve } from 'path';

const outDir = resolve(process.env.BUILD_DIR || 'static/build/css');

// docker (and other environments without working file watchers) set this via `npm run watch-polling`.
const forcePolling = process.env.FORCE_POLLING === 'true';

// Same entry discovery as webpack.config.css.js
const cssFiles = readdirSync('./static/css')
    .filter((name) => name.startsWith('page-') && name.endsWith('.css'));

const entries = {
    tokens: resolve('./static/css/tokens.css'),
    'ol-components': resolve('./static/css/ol-components.css'),
};
cssFiles.forEach((file) => {
    const name = file.replace(/\.css$/, '');
    entries[name] = resolve('./static/css', file);
});

/*
 * webpack `url: false` parity: leave root-absolute url(/static/...) exactly as
 * written. Vite has no such flag — it would inline small /static/ assets as
 * base64 data URIs and rewrite the rest, breaking the paths nginx serves
 * directly. Setting `publicDir: '.'` makes every root-absolute url() resolve
 * to a *public asset*, the one class Vite deliberately leaves unprocessed
 * (public urls are keyed relative to publicDir, so only the project root
 * matches urls that carry the /static/ prefix). `copyPublicDir` is disabled
 * below so the whole project isn't copied into the build output. Scope is
 * intentionally global: any root-absolute url pointing at an existing project
 * file is left untouched — that's the contract here.
 */
export default defineConfig(({ mode }) => ({
    // webpack `url: false` parity for root-absolute urls — see the comment above.
    publicDir: '.',
    // Don't clear the shared terminal in `npm run watch`, where webpack and
    // Vite log to the same screen (Vite clears the screen on build by default).
    clearScreen: false,
    build: {
        outDir,
        emptyOutDir: true,
        // The whole project is the "public dir" (see publicDir above) — never
        // copy it into outDir.
        copyPublicDir: false,
        // Minify in every mode except explicit dev watch (`watch:css` passes
        // `--mode development`); `vite build` defaults to mode 'production'.
        cssMinify: mode !== 'development',
        sourcemap: false,
        // `vite build --watch` uses the rollup watcher; enable polling for
        // environments (e.g. docker bind mounts) that need it. This implies
        // watch mode, which is exactly what `watch-polling` is for.
        watch: forcePolling ? { chokidar: { usePolling: true, interval: 1000 } } : null,
        rollupOptions: {
            input: entries,
            output: {
                assetFileNames: '[name][extname]',
            },
        },
    },
}));
