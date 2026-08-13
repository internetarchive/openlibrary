/*
 * Vite config for the classic-script JS bundles: `sw` + `partnerLib`.
 *
 * `sw.js` is a service worker served raw at /sw.js and registered as a
 * *classic* script, so it must be a single self-contained IIFE (no top-level
 * import/export, no external chunks). `partnerLib.js` is embedded by external
 * partners as a classic script. Neither code-splits, so `format: 'iife'` is
 * safe here — but IIFE implies `codeSplitting: false`, which only allows ONE
 * input, so this config builds one entry per invocation:
 *
 *   BUILD_DIR=static/build/js IIFE_ENTRY=sw         npx vite build -c vite-js-iife.config.mjs
 *   BUILD_DIR=static/build/js IIFE_ENTRY=partnerLib npx vite build -c vite-js-iife.config.mjs
 *
 * Run *after* vite-js.config.mjs against the same BUILD_DIR (this config does
 * not empty the directory, it appends). Shared options live in
 * vite-js-shared.mjs; this file only states what is specific to the IIFE build.
 */
import { defineConfig } from 'vite';
import { resolve } from 'path';
import { commonBuildOptions, jsBuildMarker } from './vite-js-shared.mjs';

const ENTRY = process.env.IIFE_ENTRY || 'sw';

const entries = {
    sw: resolve('openlibrary/plugins/openlibrary/js/service-worker.js'),
    partnerLib: resolve('openlibrary/plugins/openlibrary/js/partner_ol_lib.js'),
};

if (!entries[ENTRY]) {
    throw new Error(`Unknown IIFE_ENTRY "${ENTRY}" (expected one of: ${Object.keys(entries).join(', ')})`);
}

export default defineConfig(({ mode }) => ({
    publicDir: '.',
    clearScreen: false,
    plugins: [jsBuildMarker('vite-js-iife.config.mjs')],
    build: {
        ...commonBuildOptions({ mode }),
        rollupOptions: {
            input: { [ENTRY]: entries[ENTRY] },
            output: {
                format: 'iife',
                entryFileNames: '[name].js',
                chunkFileNames: '[name].[hash].js',
                assetFileNames: '[name][extname]',
            },
        },
    },
}));
