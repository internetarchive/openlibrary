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
 * See docs/ai/js-vite-migration-progress.md for the full rationale and the
 * webpack-parity harness.
 *
 * Usage:
 *   BUILD_DIR=static/build/js npx vite build -c vite-js.config.mjs
 *   BUILD_DIR=static/build/js npx vite build -c vite-js.config.mjs --watch --mode development
 */
import { defineConfig } from 'vite';
import { resolve, basename, dirname } from 'path';

const outDir = resolve(process.env.BUILD_DIR || 'static/build/js');

// docker / bind-mount environments set this via `npm run watch-polling`.
const forcePolling = process.env.FORCE_POLLING === 'true';

const VITE_VERSION = '8.0.16'; // keep in sync with package.json

/*
 * jquery-ui AMD-deps interop.
 *
 * jquery-ui 1.14 ships UMD only, and its inter-module dependencies are AMD:
 * `define(["jquery", "../widget", ...], factory)`. Vite/Rolldown has no AMD
 * loader, so importing `jquery-ui/ui/widgets/tabs` alone would take the UMD's
 * browser-globals branch (`factory(jQuery)`) *without* loading `../widget` —
 * and `$.widget` is undefined at runtime. Webpack handled this with built-in
 * AMD support; to match it, inject side-effect imports for every relative AMD
 * dependency so they execute (in order) before the importing module.
 */
function jqueryUiAmdDeps() {
    return {
        name: 'jquery-ui-amd-deps',
        transform(code, id) {
            if (!id.includes('node_modules/jquery-ui/')) return null;
            const match = code.match(/define\s*\(\s*\[([\s\S]*?)\]\s*,\s*factory\s*\)/);
            if (!match) return null;
            const deps = [...match[1].matchAll(/"([^"\\]+)"/g)]
                .map((m) => m[1])
                .filter((d) => d !== 'jquery'); // jquery is a window global
            if (!deps.length) return null;

            const dir = dirname(id);
            const imports = deps.map((dep) => {
                const resolved = resolve(dir, dep);
                return `import '${resolved.endsWith('.js') ? resolved : `${resolved}.js`}';`;
            });
            return { code: `${imports.join('\n')}\n${code}`, map: null };
        },
    };
}

/*
 * webpack `ProvidePlugin` parity: 30 modules use bare `$`/`jQuery` with no
 * import (webpack injected `import $ from 'jquery'` for them). Vite has no
 * ProvidePlugin equivalent, so inject the import into project modules that
 * reference the identifier. Modules that already `import` from 'jquery'
 * (e.g. Toast.js, SelectionManager.js) are left alone.
 */
function injectJqueryGlobals() {
    return {
        name: 'ol-inject-jquery-globals',
        transform(code, id) {
            // Only project source, only JS/TS. node_modules is untouched (UMD
            // libs like jquery-ui reference `$`/`jQuery` internally).
            if (!/\.(?:[cm]?[jt]sx?)$/.test(id)) return null;
            if (id.includes('/node_modules/') || id.includes('node_modules\\')) return null;

            // Already imports from jquery — don't double-inject.
            if (/from\s+['"]jquery['"]|require\(\s*['"]jquery['"]\s*\)/.test(code)) return null;

            // Don't inject if the module declares its own binding for either
            // name. `$` must be standalone (`$foo` is a different identifier).
            if (/\b(?:const|let|var|function|class|import)\s+(?:\$(?![\w$])|jQuery\b)/.test(code)) return null;

            const needsJquery = /\bjQuery\b/.test(code);
            const needsDollar = /(?<![\w$])\$(?![\w${])/.test(code);

            if (!needsJquery && !needsDollar) return null;

            // `$` and `jQuery` are the same default export; emit them as two
            // separate default-import statements (a single statement can only
            // carry one default binding).
            const lines = [];
            if (needsDollar) lines.push("import $ from 'jquery';");
            if (needsJquery) lines.push("import jQuery from 'jquery';");

            return {
                code: `${lines.join('\n')}\n${code}`,
                map: null,
            };
        },
    };
}

/*
 * webpack named its dynamic-import chunks after the `webpackChunkName` magic
 * comment, which deliberately differs from the imported file name in ~16
 * places (e.g. `./edit` -> chunk "user-website"). Vite/Rolldown names chunks
 * after the imported file. `bundlesize.config.json` globs and deploy tooling
 * are keyed on the webpack names, so remap them here.
 */
const CHUNK_NAME_MAP = {
    banner: 'dismissible-banner',
    breadcrumb_select: 'breadcrumb-select',
    dropper: 'droppers',
    edit: 'user-website',
    'edition-nav-bar': 'nav-bar',
    goodreads_import: 'goodreads-import',
    'lazy-carousel': 'lazy-carousels',
    list_books: 'list-books',
    modals: 'modal-links',
    'password-toggle': 'password-visibility-toggle',
    patron_exports: 'patron-exports',
    'private-button': 'private-buttons',
    readinglog_stats: 'readinglog-stats',
    SearchFilterBar: 'search-filter-bar',
    sort_options: 'sort-options',
    type_changer: 'type-changer',
};

/*
 * Build-tool marker: prepend a "built by Vite …" comment to every output so
 * any deployed file is attributable at a glance. rolldown-vite ignores
 * `output.banner`, so do it in `generateBundle` (the CSS migration's
 * `cssBuildMarker` pattern). The AGPL license header is still added by the
 * Makefile's build-agnostic shell loop.
 */
function jsBuildMarker() {
    return {
        name: 'js-build-marker',
        generateBundle(_options, bundle) {
            const marker = `/* built by Vite ${VITE_VERSION} (vite-js.config.mjs) */\n`;
            for (const item of Object.values(bundle)) {
                if (item.type === 'chunk') item.code = marker + item.code;
            }
        },
    };
}

/*
 * Entry CSS (js-all.css, imported by index.js) needs no custom machinery: the
 * `main` chunk's preload map includes `js.css`, so Vite injects a
 * `<link rel="stylesheet">` when `all.js` dynamically imports `main` — which
 * satisfies js-all.css's contract ("JS-only, non-render-blocking"). webpack
 * used style-loader for the same effect.
 */

function chunkName(info) {
    // Rolldown derives `name` from the imported file/directory; fall back to the
    // facade module basename for robustness across bundler versions.
    let raw = info.name || (info.facadeModuleId ? basename(info.facadeModuleId).replace(/\.[^.]+$/, '') : 'chunk');
    // The dynamically-imported app entry (index.js, via the main-entry facade)
    // is named "js" (its parent directory) by rolldown — give it a stable name.
    if (info.facadeModuleId && info.facadeModuleId.endsWith('/js/index.js')) raw = 'main';
    return CHUNK_NAME_MAP[raw] ?? raw;
}

export default defineConfig(({ mode }) => ({
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
    publicDir: '.',
    clearScreen: false,
    plugins: [jqueryUiAmdDeps(), injectJqueryGlobals(), jsBuildMarker()],
    build: {
        outDir,
        // Don't empty the dir: sw.js/partnerLib.js are appended by
        // vite-js-iife.config.mjs, and in watch mode an `emptyOutDir: true`
        // rebuild would wipe them. The Makefile owns directory cleanliness.
        emptyOutDir: false,
        copyPublicDir: false,
        sourcemap: true,
        minify: mode !== 'development',
        // Mirror package.json's browserslist. The binding constraint is Safari
        // 11.1 / iOS 11.3 — Chrome/Edge/Firefox are "last 3 years" (116/117+),
        // which never constrains anything Safari 11.1 doesn't already. esbuild
        // transpiles *syntax* (optional chaining, nullish coalescing, …) down to
        // that floor; API polyfills are covered by the explicit core-js import
        // at the top of index.js (replaces babel useBuiltIns:'usage').
        target: ['safari11.1', 'ios11.3'],
        // Vite only warns about big chunks; `bundlesize` (CI) is the real gate,
        // replacing webpack's `performance.hints: 'error'`.
        chunkSizeWarningLimit: 3000,
        watch: forcePolling ? { chokidar: { usePolling: true, interval: 1000 } } : null,
        rollupOptions: {
            input: {
                // Thin facade (main-entry.js) — the real app is a dynamic chunk
                // so lazy chunks never import the entry (see main-entry.js).
                all: resolve('openlibrary/plugins/openlibrary/js/main-entry.js'),
            },
            output: {
                entryFileNames: '[name].js',
                chunkFileNames: (info) => `${chunkName(info)}.[hash].js`,
                assetFileNames: '[name][extname]',
            },
        },
    },
}));
