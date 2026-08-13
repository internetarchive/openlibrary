/*
 * ESM-build machinery for vite-js.config.mjs: the two transform plugins that
 * reproduce webpack behaviors Vite lacks (ProvidePlugin + AMD interop) and the
 * chunk-name contract (`bundlesize.config.json` globs + SW matcher tests are
 * keyed on the webpack chunk names).
 *
 * Extracted from vite-js.config.mjs so the plugins are unit-testable
 * (tests/unit/js/vite-js-plugins.test.js).
 */
import { resolve, basename, dirname } from 'path';

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
export function jqueryUiAmdDeps() {
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
export function injectJqueryGlobals() {
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
export const CHUNK_NAME_MAP = {
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

export function chunkName(info) {
    // Rolldown derives `name` from the imported file/directory; fall back to the
    // facade module basename for robustness across bundler versions.
    let raw = info.name || (info.facadeModuleId ? basename(info.facadeModuleId).replace(/\.[^.]+$/, '') : 'chunk');
    // The dynamically-imported app entry (index.js, via the main-entry facade)
    // is named "js" (its parent directory) by rolldown — give it a stable name.
    if (info.facadeModuleId && info.facadeModuleId.endsWith('/js/index.js')) raw = 'main';
    return CHUNK_NAME_MAP[raw] ?? raw;
}
