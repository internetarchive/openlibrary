/*
 * Vite config to replace webpack.config.js — JS bundles.
 * =====================================================================
 *
 * Builds the Open Library JavaScript. There are two configs because the
 * three webpack entries need two different output formats:
 *
 *   vite-js.config.mjs       -> `all` (index.js) as **ESM** so that the ~55
 *                               `import()` chunks can be code-split. Rollup /
 *                               Vite cannot emit IIFE/UMD for a code-splitting
 *                               build, so `all.js` moves from a classic
 *                               `<script>` to `<script type="module">`.
 *   vite-js-iife.config.mjs  -> `sw` + `partnerLib` as **IIFE** classic
 *                               scripts (service worker + external partner lib;
 *                               neither code-splits).
 *
 * Shared options (outDir, sourcemaps, targets, AGPL license header/footer, …)
 * live in vite-js-shared.mjs and chunk naming in vite-js-chunk-names.mjs; this
 * file only wires them together. jquery-ui's AMD interop needs no plugin —
 * explicit wrapper modules handle it (openlibrary/plugins/openlibrary/js/jquery-ui-*).
 *
 * The webpack-parity harness lives in scripts/js-build-parity.sh.
 *
 * Usage:
 *   BUILD_DIR=static/build/js npx vite build -c vite-js.config.mjs
 *   BUILD_DIR=static/build/js npx vite build -c vite-js.config.mjs --watch --mode development
 */
import { defineConfig } from 'vite';
import { resolve } from 'path';
import { commonBuildOptions, AGPL_LICENSE_HEADER, AGPL_LICENSE_FOOTER } from './vite-js-shared.mjs';
import { chunkName } from './vite-js-chunk-names.mjs';
import { renderBuiltAssetUrl } from './vite-asset-urls.mjs';

export default defineConfig(({ mode }) => ({
    // CSS that JavaScript imports has root-absolute url(/static/...). This
    // hook writes these urls unchanged. Without the hook, `base` below
    // changes /static/images/x.svg to /static/build/js/static/images/x.svg.
    // The server then returns 404. See vite-asset-urls.mjs.
    experimental: { renderBuiltUrl: renderBuiltAssetUrl },
    // webpack `output.publicPath: "/static/build/js/"` parity. Without this the
    // dynamic-import chunks and their preload <link>s are resolved against `/`
    // (Vite's default base) and 404 — the entry is served at /static/build/js/,
    // not at the site root. Only the ESM build needs it: sw.js/partnerLib.js
    // (IIFE) don't code-split, so they never emit chunk URLs.
    base: '/static/build/js/',
    // webpack `url:false` parity for root-absolute url(/static/...) — see the
    // comment in vite-css.config.mjs. Every JS-imported stylesheet uses
    // root-absolute urls; leaving them unprocessed avoids Vite inlining them
    // as data URIs or rewriting/copying them (which breaks nginx-served paths).
    // Note: `base` below changes these urls. The
    // experimental.renderBuiltUrl hook above stops this.
    publicDir: '.',
    clearScreen: false,
    build: {
        ...commonBuildOptions({ mode }),
        rolldownOptions: {
            input: {
                // Thin facade (main-entry.js) — the real app is a dynamic chunk
                // so lazy chunks never import the entry (see main-entry.js).
                all: resolve('openlibrary/plugins/openlibrary/js/main-entry.js'),
            },
            output: {
                // AGPLv3 license header/footer (LibreJS magnet comment). Applied
                // after minification (postBanner/postFooter) so they survive.
                postBanner: AGPL_LICENSE_HEADER,
                postFooter: AGPL_LICENSE_FOOTER,
                entryFileNames: '[name].js',
                chunkFileNames: (info) => `${chunkName(info)}.[hash].js`,
                assetFileNames: '[name].[hash][extname]',
            },
        },
    },
}));
