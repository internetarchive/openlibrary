/*
 * Shared pieces for the JS build configs (vite-js.config.mjs +
 * vite-js-iife.config.mjs).
 *
 * Both configs build to the same directory and share all build options except
 * entries, output format, and the extra transform plugins — keep that common
 * boilerplate here so the two configs only state what actually differs.
 *
 * See docs/ai/js-vite-migration-progress.md for the full rationale.
 */
import { createRequire } from 'module';
import { resolve } from 'path';

const require = createRequire(import.meta.url);

/*
 * Read the real installed version so the build marker can never drift from
 * what's actually in node_modules (package.json only pins a semver range).
 */
export const VITE_VERSION = require('vite/package.json').version;

export const JS_OUT_DIR = resolve(process.env.BUILD_DIR || 'static/build/js');

// docker / bind-mount environments set this via `npm run watch-polling`.
const forcePolling = process.env.FORCE_POLLING === 'true';

/*
 * Build-tool marker: prepend a "built by Vite …" comment to every output so
 * any deployed file is attributable at a glance. rolldown-vite ignores
 * `output.banner`, so do it in `generateBundle`. The AGPL license header is
 * still added by the Makefile's build-agnostic shell loop.
 */
export function jsBuildMarker(configFile) {
    return {
        name: 'js-build-marker',
        generateBundle(_options, bundle) {
            const marker = `/* built by Vite ${VITE_VERSION} (${configFile}) */\n`;
            for (const item of Object.values(bundle)) {
                if (item.type === 'chunk') item.code = marker + item.code;
            }
        },
    };
}

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
        // which never constrains anything Safari 11.1 doesn't already. esbuild
        // transpiles *syntax* (optional chaining, nullish coalescing, …) down to
        // that floor; API polyfills are covered by the explicit core-js import
        // at the top of index.js (replaces babel useBuiltIns:'usage').
        target: ['safari11.1', 'ios11.3'],
        // Vite only warns about big chunks; `bundlesize` (CI) is the real gate,
        // replacing webpack's `performance.hints: 'error'`.
        chunkSizeWarningLimit: 3000,
        watch: forcePolling ? { chokidar: { usePolling: true, interval: 1000 } } : null,
    };
}
