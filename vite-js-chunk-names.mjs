/*
 * ESM-build machinery for vite-js.config.mjs: the chunk-name contract
 * (`bundlesize.config.json` globs + SW matcher tests are keyed on the webpack
 * chunk names). The jquery-ui AMD interop that used to live here was replaced
 * by explicit wrapper modules (openlibrary/plugins/openlibrary/js/jquery-ui-*).
 *
 * Extracted from vite-js.config.mjs so the plugins are unit-testable
 * (tests/unit/js/vite-js-plugins.test.js).
 */
import { basename } from 'path';

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
