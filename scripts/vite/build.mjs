/*
 * Single build entry for all Vite jobs.
 *
 * Jobs:
 *   css        -> static/build/css
 *   js         -> static/build/js (ESM `all` + IIFE `sw`, `partnerLib`)
 *   components -> static/build/components/production (Vue + Lit merged)
 *
 * Why one file:
 *   Vite allows one outDir and one module format per build.
 *   This file runs each build with the correct options.
 *   One command builds all. One command watches all.
 *
 * Use:
 *   node scripts/vite/build.mjs
 *   node scripts/vite/build.mjs --only css|js|components
 *   node scripts/vite/build.mjs --watch --mode development
 *   FORCE_POLLING=true node scripts/vite/build.mjs --watch --mode development
 *   node scripts/vite/build.mjs --help
 *
 * Flags accept space or `=` form (`--only css`, `--only=css`).
 *
 * Env:
 *   BUILD_DIR overrides the outDir for single-group runs.
 *   The Makefile uses this for atomic *_new dirs.
 *   JS_OUT_DIR, CSS_OUT_DIR, COMPONENTS_OUT_DIR override each group.
 */
import { build } from "vite";
import vue from "@vitejs/plugin-vue";
import { readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { parseArgs } from "node:util";
import { AGPL_LICENSE_FOOTER, AGPL_LICENSE_HEADER, commonBuildOptions } from "../../vite-js-shared.mjs";
import { renderBuiltAssetUrl } from "../../vite-asset-urls.mjs";

const root = resolve(import.meta.dirname, "../..");

const { values } = parseArgs({
    options: {
        watch: { type: "boolean", default: false },
        mode: { type: "string" },
        only: { type: "string" },
        help: { type: "boolean", default: false },
    },
});
const isWatch = values.watch;
const only = values.only ?? null;
const mode = values.mode ?? (isWatch ? "development" : "production");
const forcePolling = process.env.FORCE_POLLING === "true";

if (values.help) {
    console.log(`Use: node scripts/vite/build.mjs [--only css|js|components] [--watch] [--mode development|production]

Builds all frontend assets. One command builds all groups in parallel.
Groups use distinct outDirs: static/build/css, static/build/js,
static/build/components/production.

Env: BUILD_DIR overrides the outDir for --only runs (used by the
Makefile for atomic *_new dirs). FORCE_POLLING=true helps file
watchers on bind mounts (see npm run watch-polling).`);
    process.exit(0);
}

const VALID_ONLY = new Set(["css", "js", "components"]);
if (only !== null && !VALID_ONLY.has(only)) {
    console.error(`Unknown --only "${only}" (use one of: css, js, components)`);
    process.exit(1);
}

// Watch option for the Vite JS API. Null means no watch.
// Empty object means watch with default file watcher.
const watchOption = isWatch ? (forcePolling ? { chokidar: { interval: 1000, usePolling: true } } : {}) : null;

// Keys shared by every build. `configFile: false` stops Vite
// from auto-loading a vite.config.* file (we pass all options inline).
function baseConfig() {
    return {
        mode,
        root,
        configFile: false,
        publicDir: ".",
        clearScreen: false,
    };
}

function outDirFor(name, fallback) {
    if (process.env.BUILD_DIR && only !== null) {
        // Single-group run (Makefile atomic dir or old npm script).
        // Vue/Lit group keeps the `/production` suffix.
        return only === "components" ? join(resolve(process.env.BUILD_DIR), "production") : resolve(process.env.BUILD_DIR);
    }
    const override = process.env[`${name}_OUT_DIR`];
    if (override) {
        return resolve(override);
    }
    return resolve(root, fallback);
}

// -----------------------------------------------------------------
// CSS: tokens, ol-components, page-*.css -> static/build/css
// -----------------------------------------------------------------
function getCssConfig() {
    const cssFiles = readdirSync(join(root, "static/css")).filter((f) => f.startsWith("page-") && f.endsWith(".css"));
    const entries = {
        tokens: resolve(root, "static/css/tokens.css"),
        "ol-components": resolve(root, "static/css/ol-components.css"),
    };
    for (const f of cssFiles) {
        entries[f.replace(/\.css$/, "")] = resolve(root, "static/css", f);
    }

    return {
        ...baseConfig(),
        build: {
            outDir: outDirFor("CSS", "static/build/css"),
            emptyOutDir: true,
            copyPublicDir: false,
            cssMinify: mode !== "development",
            sourcemap: false,
            watch: watchOption,
            rolldownOptions: {
                input: entries,
                output: { assetFileNames: "[name][extname]" },
            },
        },
    };
}

// -----------------------------------------------------------------
// JS: ESM `all` + IIFE `sw` + IIFE `partnerLib` -> static/build/js
// -----------------------------------------------------------------
// AGPL license header/footer (LibreJS magnet comment). Applied after
// minification (postBanner/postFooter) so the license survives it.
function agplOutput(extra) {
    return {
        postBanner: AGPL_LICENSE_HEADER,
        postFooter: AGPL_LICENSE_FOOTER,
        ...extra,
    };
}

function getJsEsmConfig(outDir) {
    return {
        ...baseConfig(),
        experimental: { renderBuiltUrl: renderBuiltAssetUrl },
        base: "/static/build/js/",
        build: {
            ...commonBuildOptions({ mode }),
            outDir,
            // The Makefile clears the *_new dir before the run.
            // Keep false so IIFE outputs survive next to ESM outputs.
            emptyOutDir: false,
            watch: watchOption,
            rolldownOptions: {
                input: { all: resolve(root, "openlibrary/plugins/openlibrary/js/main-entry.js") },
                output: agplOutput({
                    entryFileNames: "[name].js",
                    chunkFileNames: "[name].[hash].js",
                    assetFileNames: "[name].[hash][extname]",
                }),
            },
        },
    };
}

function getJsIifeConfig(name, entryPath, outDir) {
    return {
        ...baseConfig(),
        experimental: { renderBuiltUrl: renderBuiltAssetUrl },
        build: {
            ...commonBuildOptions({ mode }),
            outDir,
            emptyOutDir: false,
            watch: watchOption,
            rolldownOptions: {
                input: { [name]: entryPath },
                output: agplOutput({
                    format: "iife",
                    entryFileNames: "[name].js",
                    chunkFileNames: "[name].[hash].js",
                    assetFileNames: "[name][extname]",
                }),
            },
        },
    };
}

// -----------------------------------------------------------------
// Components: Vue + Lit merged -> static/build/components/production
// -----------------------------------------------------------------
function getVueNames() {
    return readdirSync(join(root, "openlibrary/components"))
        .filter((name) => name.endsWith(".vue"))
        .map((name) => name.replace(/\.vue$/, ""));
}

// In-memory entries for Vue files. No tmp files on disk.
function virtualVuePlugin() {
    return {
        name: "virtual-vue-wc-entries",
        resolveId(id) {
            if (id.startsWith("virtual:vue-wc:")) {
                return id;
            }
            return null;
        },
        load(id) {
            if (id.startsWith("virtual:vue-wc:")) {
                const name = id.replace("virtual:vue-wc:", "");
                return [
                    "import { createWebComponentSimple } from '/openlibrary/components/rollupInputCore.js';",
                    `import rootComponent from '/openlibrary/components/${name}.vue';`,
                    `createWebComponentSimple(rootComponent, '${name}');`,
                    "",
                ].join("\n");
            }
            return null;
        },
    };
}

function getComponentsConfig() {
    const input = { "ol-components": resolve(root, "openlibrary/components/lit/index.js") };
    for (const name of getVueNames()) {
        // Output `[name].js` keeps Vue names as `ol-<Name>.js`
        // and Lit as `ol-components.js`. Both match current output.
        input[`ol-${name}`] = `virtual:vue-wc:${name}`;
    }

    return {
        ...baseConfig(),
        plugins: [vue({ customElement: true }), virtualVuePlugin()],
        build: {
            target: ["es2019", "safari13"],
            outDir: outDirFor("COMPONENTS", "static/build/components/production"),
            emptyOutDir: true,
            copyPublicDir: false,
            chunkSizeWarningLimit: 600,
            minify: true,
            sourcemap: true,
            watch: watchOption,
            rolldownOptions: {
                input,
                output: {
                    entryFileNames: "[name].js",
                    format: "es",
                },
            },
        },
    };
}

async function runCss() {
    await build(getCssConfig());
}

async function runJs() {
    const outDir = outDirFor("JS", "static/build/js");
    // Run ESM first, then IIFE files. They share one outDir.
    // Parallel runs risk one build that clears the dir
    // while the other build writes files.
    await build(getJsEsmConfig(outDir));
    await Promise.all([
        build(getJsIifeConfig("sw", resolve(root, "openlibrary/plugins/openlibrary/js/service-worker.js"), outDir)),
        build(
            getJsIifeConfig("partnerLib", resolve(root, "openlibrary/plugins/openlibrary/js/partner_ol_lib.js"), outDir),
        ),
    ]);
}

async function runComponents() {
    await build(getComponentsConfig());
}

async function run() {
    const jobs = [];
    if (only === null || only === "css") {
        jobs.push(["css", runCss]);
    }
    if (only === null || only === "js") {
        jobs.push(["js", runJs]);
    }
    if (only === null || only === "components") {
        jobs.push(["components", runComponents]);
    }

    console.log(`Build start (mode: ${mode}${isWatch ? ", watch" : ""}): ${jobs.map(([name]) => name).join(", ")}`);

    // Groups use distinct outDirs, so groups can run at the same time.
    await Promise.all(jobs.map(([, fn]) => fn()));

    if (!isWatch) {
        console.log("All builds done.");
    }
}

await run().catch((err) => {
    console.error("Build failed:", err);
    process.exit(1);
});
