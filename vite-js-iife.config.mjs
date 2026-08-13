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
 * not empty the directory, it appends).
 */
import { defineConfig } from 'vite';
import { resolve } from 'path';

const outDir = resolve(process.env.BUILD_DIR || 'static/build/js');
const forcePolling = process.env.FORCE_POLLING === 'true';

const ENTRY = process.env.IIFE_ENTRY || 'sw';

const entries = {
    sw: resolve('openlibrary/plugins/openlibrary/js/service-worker.js'),
    partnerLib: resolve('openlibrary/plugins/openlibrary/js/partner_ol_lib.js'),
};

if (!entries[ENTRY]) {
    throw new Error(`Unknown IIFE_ENTRY "${ENTRY}" (expected one of: ${Object.keys(entries).join(', ')})`);
}

const VITE_VERSION = '8.0.16'; // keep in sync with package.json

/*
 * Build-tool marker (see jsBuildMarker in vite-js.config.mjs). rolldown-vite
 * ignores `output.banner`, so prepend via `generateBundle`.
 */
function jsBuildMarker() {
    return {
        name: 'js-build-marker',
        generateBundle(_options, bundle) {
            const marker = `/* built by Vite ${VITE_VERSION} (vite-js-iife.config.mjs) */\n`;
            for (const item of Object.values(bundle)) {
                if (item.type === 'chunk') item.code = marker + item.code;
            }
        },
    };
}

export default defineConfig(({ mode }) => ({
    publicDir: '.',
    clearScreen: false,
    plugins: [jsBuildMarker()],
    build: {
        outDir,
        emptyOutDir: false, // appended after the ESM build; don't wipe all.js + chunks
        copyPublicDir: false,
        sourcemap: true,
        minify: mode !== 'development',
        // The service worker runs in the same old-browser surface as the site;
        // keep the syntax floor in line with the ESM build (Safari 11.1 / iOS
        // 11.3, per package.json's browserslist).
        target: ['safari11.1', 'ios11.3'],
        chunkSizeWarningLimit: 3000,
        watch: forcePolling ? { chokidar: { usePolling: true, interval: 1000 } } : null,
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
