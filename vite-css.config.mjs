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
 *   - url() passthrough (webpack url:false) -> see cssUrlPassthrough()
 *   - no JS output (webpack's RemoveJSAssetsPlugin) -> companion plugin below
 *
 * Usage:
 *   npx vite build -c vite-css.config.mjs
 *   npx vite build -c vite-css.config.mjs --watch
 *
 * Build output defaults to static/build/css. Set BUILD_DIR to override.
 */
import { defineConfig } from 'vite';
import { readdirSync, readFileSync, writeFileSync } from 'fs';
import { resolve } from 'path';

const outDir = resolve(process.env.BUILD_DIR || 'static/build/css');

// Matches webpack: minify for production builds, keep readable output in dev watch mode.
const isDev = process.env.NODE_ENV === 'development';
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
 * Preserve root-absolute url(/static/...) references exactly as written
 * (webpack's css-loader does this via `url: false`). Without this, Vite
 * would inline small images as base64 data URIs and emit/rewrite larger
 * ones, changing both the payload and the served paths.
 *
 * Mechanism: a PostCSS plugin encodes each root-absolute url() as
 * `url(#__OL__/static/...)` inside a `Once` hook. `Once` runs right after
 * postcss-import inlines the raw imported CSS but BEFORE Vite's internal
 * url-rewriting plugin (which skips urls starting with `#`), so nothing
 * gets inlined or rewritten. A Vite plugin then decodes the placeholders
 * back in the emitted CSS files (in closeBundle, after minification).
 */
const encodeStaticUrls = {
    postcssPlugin: 'ol-encode-static-urls',
    Once(root) {
        root.walkDecls((decl) => {
            if (decl.value && decl.value.includes('url(')) {
                decl.value = decl.value.replace(
                    /url\((['"]?)(\/[^'")]*)\1\)/g,
                    (_match, _quote, url) => `url("#__OL__${url}")`,
                );
            }
        });
    },
};

function cssUrlPassthrough() {
    // `url(#__OL__/static/...)` -> `url(/static/...)`, handling both the
    // quoted form (before minification) and unquoted form (after).
    const placeholderRe = /url\("?#__OL__([^)"']+)"?\)/g;
    return {
        name: 'css-url-passthrough',
        // Vite's CSS minification runs after plugin generateBundle hooks, so
        // decode from disk in closeBundle (the final phase) instead.
        closeBundle() {
            for (const fileName of readdirSync(outDir)) {
                if (!fileName.endsWith('.css')) continue;
                const filePath = resolve(outDir, fileName);
                let source = readFileSync(filePath, 'utf8');
                const decoded = source.replace(placeholderRe, (_m, url) => `url(${url})`);
                if (decoded !== source) {
                    writeFileSync(filePath, decoded);
                    source = decoded;
                }
                // Regression guard: the passthrough relies on Vite's internal
                // postcss plugin ordering and `#`-url skipping, which are not
                // public API. If a Vite upgrade ever inlines assets again or
                // breaks the placeholder decoding, fail loudly instead of
                // silently shipping bloated/broken CSS.
                if (/data:image\//.test(source)) {
                    console.warn(`[css-url-passthrough] ${fileName}: found data:image/ URIs — Vite inlined assets despite the passthrough; check Vite version compatibility.`);
                }
                if (source.includes('__OL__')) {
                    console.warn(`[css-url-passthrough] ${fileName}: leftover __OL__ placeholders — decoding failed; check Vite version compatibility.`);
                }
            }
        },
    };
}

// Vite emits a companion (empty) JS chunk for every pure-CSS entry — the
// same problem webpack's RemoveJSAssetsPlugin solves. Delete them here.
function removeCompanionJsChunks() {
    return {
        name: 'remove-companion-js-chunks',
        generateBundle(_options, bundle) {
            for (const [fileName, chunk] of Object.entries(bundle)) {
                if (chunk.type === 'chunk' && fileName.endsWith('.js')) {
                    delete bundle[fileName];
                }
            }
        },
    };
}

export default defineConfig({
    plugins: [cssUrlPassthrough(), removeCompanionJsChunks()],
    css: {
        postcss: {
            plugins: [encodeStaticUrls],
        },
    },
    build: {
        outDir,
        emptyOutDir: true,
        cssMinify: !isDev,
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
});
