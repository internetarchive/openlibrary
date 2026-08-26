/*
 * Shared pieces for the JS build configs (vite-js.config.mjs +
 * vite-js-iife.config.mjs).
 *
 * Both configs build to the same directory and share all build options except
 * entries, output format, and the extra transform plugins — keep that common
 * boilerplate here so the two configs only state what actually differs.
 *
 */
import { resolve } from 'path';

export const JS_OUT_DIR = resolve(process.env.BUILD_DIR || 'static/build/js');

/*
 * AGPLv3 license header/footer (GNU LibreJS magnet comment). Applied via
 * `output.postBanner` / `output.postFooter` in both configs so every emitted
 * file carries the license after minification. This replaces the Makefile's
 * shell loop (which prepended the header to every .js file post-build).
 */
export const AGPL_LICENSE_HEADER = '// @license magnet:?xt=urn:btih:0b31508aeb0634b347b8270c7bee4d411b5d4109&dn=agpl-3.0.txt AGPL-v3.0';
export const AGPL_LICENSE_FOOTER = '\n// @license-end';

// docker / bind-mount environments set this via `npm run watch-polling`.
const forcePolling = process.env.FORCE_POLLING === 'true';

/*
 * Options shared verbatim by both configs. Only the output-shape keys
 * (entryFileNames/chunkFileNames/format/base/plugins) are left to the caller.
 */
export function commonBuildOptions({ mode }) {
    return {
        outDir: JS_OUT_DIR,
        // Don't empty the dir: sw.js/partnerLib.js are appended by
        // vite-js-iife.config.mjs, and in watch mode an `emptyOutDir: true`
        // rebuild would wipe them. The Makefile owns directory cleanliness.
        emptyOutDir: false,
        copyPublicDir: false,
        sourcemap: true,
        minify: mode !== 'development',
        // Mirror package.json's browserslist. The binding constraint is Safari
        // 11.1 / iOS 11.3 — Chrome/Edge/Firefox are "last 3 years" (116/117+),
        // which never constrains anything Safari 11.1 doesn't already. Oxc lowers
        // syntax (optional chaining, nullish coalescing, …) to that floor; API
        // polyfills are covered by the explicit core-js import at the top of
        // index.js (replaces babel useBuiltIns:'usage').
        target: ['safari11.1', 'ios11.3'],
        // Vite only warns about big chunks; `bundlesize` (CI) is the real gate,
        // replacing webpack's `performance.hints: 'error'`.
        chunkSizeWarningLimit: 3000,
        watch: forcePolling ? { chokidar: { usePolling: true, interval: 1000 } } : null,
    };
}
