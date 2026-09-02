/*
 * Keep root-absolute url(/static/...) unchanged in CSS that JavaScript
 * imports. This gives the same result as webpack `url:false`.
 *
 * Problem
 * =======
 * The JS configs set `publicDir: '.'` (see vite-css.config.mjs). So Vite
 * sees each root-absolute url() that points to an existing file as a
 * public asset. Vite does not inline this asset and does not copy it.
 *
 * The standalone CSS build has base "/". It writes these urls unchanged.
 * The JS builds set `base: '/static/build/js/'`. Code-split chunks need
 * this base to load correctly. It matches webpack output.publicPath. But
 * Vite joins the base to each public url:
 *
 *   /static/build/js/ + /static/images/... = /static/build/js/static/images/...
 *
 * The path contains the word "static" two times. The browser cannot find
 * the file. The server returns 404. The carousel arrows show this problem.
 * Their background image is in static/css/lib/slick-theme.css. Other icons
 * in CSS from JS chunks have the same problem.
 *
 * Fix
 * ===
 * Vite gives the `experimental.renderBuiltUrl` option for this case. Vite
 * calls this function before it applies `base`. For public urls, the type
 * is "public". This function returns these urls unchanged. So the urls
 * stay root-absolute. vite-css.config.mjs gives the same result.
 *
 * For other asset urls, this function returns undefined. Vite then applies
 * `base` as usual. Code-split chunk urls need this.
 *
 * The slash: for public urls, Vite removes the leading slash from
 * `filename` before it calls this function. This function adds the slash
 * again. A path with no leading slash gives a url relative to the page.
 *
 * Follow-up: this hook is a stopgap. The proper fix is to write relative
 * urls in CSS and delete this file, `publicDir: '.'`, and the parity check.
 * Tracked in the follow-up discussion on the migration PR:
 * https://github.com/internetarchive/openlibrary/pull/13331#issuecomment-5514656942
 */
export function renderBuiltAssetUrl(filename, { type }) {
    // Only public urls have these /static/... paths. Do not change these
    // urls. For all other urls, return undefined. Vite then uses its
    // default rules.
    if (type === 'public' && /^\/?static\//.test(filename)) {
        return `/${filename.replace(/^\//, '')}`;
    }
    return undefined;
}
