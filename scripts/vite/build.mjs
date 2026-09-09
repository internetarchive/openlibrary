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
 *   node scripts/vite/build.mjs --only css[,js,components]
 *   node scripts/vite/build.mjs --watch --mode development
 *   FORCE_POLLING=true node scripts/vite/build.mjs --watch --mode development
 *   node scripts/vite/build.mjs --help
 *
 * Flags accept space or `=` form (`--only css`, `--only=css`).
 * `--only` accepts a comma-separated list (`--only js,css`).
 *
 * One-shot builds stage into static/build/<job>_new and, only after every
 * selected job succeeds, swap each staging dir over its live dir
 * (static/build/<job>). Watch builds write straight to the live dirs.
 */
import { build } from "vite";
import vue from "@vitejs/plugin-vue";
import { readdirSync, renameSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";
import { parseArgs } from "node:util";
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
const mode = values.mode ?? (isWatch ? "development" : "production");
const forcePolling = process.env.FORCE_POLLING === "true";

if (values.help) {
    console.log(`Use: node scripts/vite/build.mjs [--only css[,js,components]] [--watch] [--mode development|production]

Builds all frontend assets. One command builds all groups in parallel.
Groups use distinct outDirs: static/build/css, static/build/js,
static/build/components/production. --only accepts a comma-separated
list to run a subset (e.g. --only js,css).

Env: One-shot builds stage into static/build/<job>_new and swap over the
live dirs only after every selected job succeeds. FORCE_POLLING=true helps file
watchers on bind mounts (see npm run watch-polling).`);
    process.exit(0);
}

const ALL_JOBS = ["css", "js", "components"];
const onlyRaw = values.only
    ? values.only
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
    : null;
if (onlyRaw) {
    const invalid = onlyRaw.filter((j) => !ALL_JOBS.includes(j));
    if (invalid.length > 0) {
        console.error(`Unknown job(s): ${invalid.join(", ")} (valid: ${ALL_JOBS.join(", ")})`);
        process.exit(1);
    }
}
const selectedJobs = new Set(onlyRaw ?? ALL_JOBS);

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

const BUILD_ROOT = join(root, "static/build");

// Staging (<job>_new) and live (<job>) directories per job.
// One-shot builds write to staging. After every selected job succeeds,
// each staging dir is renamed over its live dir. Watch builds write
// straight to the live dirs and never stage, delete, or rename.
const JOBS = {
    css: { staging: join(BUILD_ROOT, "css_new"), live: join(BUILD_ROOT, "css") },
    js: { staging: join(BUILD_ROOT, "js_new"), live: join(BUILD_ROOT, "js") },
    components: { staging: join(BUILD_ROOT, "components_new"), live: join(BUILD_ROOT, "components") },
};

function outDirForJob(job, subdir = "") {
    const base = isWatch ? JOBS[job].live : JOBS[job].staging;
    return subdir ? join(base, subdir) : base;
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
            outDir: outDirForJob("css"),
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
/*
 * AGPLv3 license header/footer (GNU LibreJS magnet comment). Applied via
 * `output.postBanner` / `output.postFooter` so every emitted file carries
 * the license after minification.
 */
const AGPL_LICENSE_HEADER = "// @license magnet:?xt=urn:btih:0b31508aeb0634b347b8270c7bee4d411b5d4109&dn=agpl-3.0.txt AGPL-v3.0";
const AGPL_LICENSE_FOOTER = "\n// @license-end";

/*
 * Options shared by the JS builds. Only the output-shape keys
 * (entryFileNames/chunkFileNames/format/base) are left to the caller.
 */
function commonJsBuildOptions() {
    return {
        copyPublicDir: false,
        sourcemap: true,
        minify: mode !== "development",
        // Mirror package.json's browserslist. The binding constraint is Safari
        // 11.1 / iOS 11.3. Oxc lowers syntax (optional chaining, nullish
        // coalescing, …) to that floor; API polyfills are covered by the explicit
        // core-js import at the top of main.js.
        target: ["safari11.1", "ios11.3"],
        // Vite only warns about big chunks; `bundlesize` (CI) is the real gate.
        chunkSizeWarningLimit: 3000,
    };
}

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
            ...commonJsBuildOptions(),
            outDir,
            // The ESM and IIFE builds share this dir, and staging starts empty.
            // Keep false so the IIFE files survive next to the ESM files, and
            // watch rebuilds never wipe the other build's output.
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
            ...commonJsBuildOptions(),
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

// Vue entries live only in memory.
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
                // Absolute filesystem paths: virtual modules have no location,
                // so root-relative `/...` specifiers rely on Vite's root
                // resolution. Absolute paths resolve deterministically.
                const compDir = join(root, "openlibrary/components");
                return [
                    `import { createWebComponentSimple } from '${join(compDir, "rollupInputCore.js")}';`,
                    `import rootComponent from '${join(compDir, `${name}.vue`)}';`,
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
        // `[name].js` emits Vue as `ol-<Name>.js` and Lit as `ol-components.js`.
        // Pages load those filenames directly, so keep this pattern.
        input[`ol-${name}`] = `virtual:vue-wc:${name}`;
    }

    return {
        ...baseConfig(),
        plugins: [vue({ customElement: true }), virtualVuePlugin()],
        build: {
            target: ["es2019", "safari13"],
            outDir: outDirForJob("components", "production"),
            emptyOutDir: true,
            copyPublicDir: false,
            chunkSizeWarningLimit: 600,
            minify: mode !== "development",
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
    const outDir = outDirForJob("js");
    // Run ESM first, then the IIFE files. The three builds share one
    // outDir, so keep them sequential instead of parallel.
    await build(getJsEsmConfig(outDir));
    const iifeJobs = [
        ["sw", resolve(root, "openlibrary/plugins/openlibrary/js/service-worker.js")],
        ["partnerLib", resolve(root, "openlibrary/plugins/openlibrary/js/partner_ol_lib.js")],
    ];
    const iifeResults = await Promise.allSettled(
        iifeJobs.map(([name, entry]) => build(getJsIifeConfig(name, entry, outDir))),
    );
    const iifeFailures = iifeResults
        .map((res, i) => ({ res, name: iifeJobs[i][0] }))
        .filter(({ res }) => res.status === "rejected");
    if (iifeFailures.length > 0) {
        const detail = iifeFailures.map(({ name, res }) => `[${name}] ${res.reason?.stack ?? res.reason}`).join("\n");
        throw new Error(`js IIFE build(s) failed:\n${detail}`);
    }
}

async function runComponents() {
    await build(getComponentsConfig());
}

async function run() {
    const jobs = [];
    if (selectedJobs.has("css")) {
        jobs.push(["css", runCss]);
    }
    if (selectedJobs.has("js")) {
        jobs.push(["js", runJs]);
    }
    if (selectedJobs.has("components")) {
        jobs.push(["components", runComponents]);
    }

    console.log(`Build start (mode: ${mode}${isWatch ? ", watch" : ""}): ${jobs.map(([name]) => name).join(", ")}`);

    if (isWatch) {
        // Watchers never settle; build straight into the live dirs and keep
        // the process alive. Never stage, delete, or rename in watch mode.
        const results = await Promise.allSettled(jobs.map(([, fn]) => fn()));
        const failed = results.filter((r) => r.status === "rejected");
        if (failed.length) throw new Error(failed.map((r) => r.reason).join("\n"));
        jobs.forEach(([n]) => console.log(`${n} watching...`));
        return;
    }

    // Fresh staging dirs up front; the live tree stays untouched until every
    // selected job has succeeded.
    for (const [name] of jobs) {
        rmSync(JOBS[name].staging, { recursive: true, force: true });
    }

    // Each group writes to its own staging dir, so the groups run in parallel.
    // allSettled waits for every job, so one failure masks no other failure.
    // CI then shows all failures in a single run.
    const results = await Promise.allSettled(jobs.map(([, fn]) => fn()));
    let hasFailure = false;
    results.forEach((res, i) => {
        if (res.status === "rejected") {
            hasFailure = true;
            console.error(`[${jobs[i][0]}] build failed:`, res.reason);
        }
    });
    if (hasFailure) {
        throw new Error("Build failed; live directories left untouched.");
    }

    // All jobs succeeded: swap each staging dir over its live dir.
    for (const [name] of jobs) {
        rmSync(JOBS[name].live, { recursive: true, force: true });
        renameSync(JOBS[name].staging, JOBS[name].live);
    }
    console.log("All builds done.");
}

await run().catch((err) => {
    console.error("Build failed:", err);
    process.exit(1);
});
