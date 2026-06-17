/**
 * Build the Open Library icon assets from the canonical sources in
 * static/icons/src/{lucide,custom}/ (each a single 24x24 / currentColor SVG).
 *
 * One source, three outputs:
 *   1. <out>/sprite.svg            — a <symbol> sheet referenced by same-document
 *                                    <use href="#name"> (the $:icon() macro and
 *                                    the <ol-icon> component). For the document /
 *                                    light DOM.
 *   2. static/icons/manifest.json  — sorted icon-name list (committed; drives the
 *                                    /developers/design gallery + name lint).
 *   3. openlibrary/components/lit/icons.generated.js — Lit `svg` glyph fragments
 *                                    (committed) for SHADOW-DOM components, which
 *                                    cannot reach the document sprite via <use>
 *                                    and must inline the geometry instead.
 *
 * Usage: node scripts/build_icon_sprite.mjs [--out <dir>]
 *   --out defaults to static/build/icons
 */
import { readFileSync, readdirSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { join, dirname, basename } from "node:path";
import { fileURLToPath } from "node:url";
import { optimize } from "svgo";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const spriteConfig = require("../config/svgo.sprite.config.js");

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SRC_DIR = join(ROOT, "static", "icons", "src");
const SRC_GROUPS = ["lucide", "custom"];
const MANIFEST_PATH = join(ROOT, "static", "icons", "manifest.json");
const JS_MODULE_PATH = join(ROOT, "openlibrary", "components", "lit", "icons.generated.js");

const outArgIndex = process.argv.indexOf("--out");
const OUT_DIR = outArgIndex !== -1 ? process.argv[outArgIndex + 1] : join(ROOT, "static", "build", "icons");

// Presentation/structural attributes worth carrying from the source <svg> onto
// the <symbol>. Everything else (xmlns, width, height, class, style, id, aria-*)
// is dropped — sizing and a11y are decided at the point of use.
const KEEP_ATTRS = new Set([
    "viewBox",
    "fill",
    "stroke",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "fill-rule",
    "clip-rule",
]);

function parseAttrs(openTag) {
    const attrs = {};
    for (const m of openTag.matchAll(/([\w:-]+)\s*=\s*"([^"]*)"/g)) {
        attrs[m[1]] = m[2];
    }
    return attrs;
}

/** kebab-case icon name -> camelCase JS identifier (arrow-left -> arrowLeft). */
function camelCase(name) {
    return name.replace(/-([a-z0-9])/g, (_, c) => c.toUpperCase());
}

/** Pull the optimized <svg> apart into its root attributes and inner markup. */
function parseSvg(svg, name) {
    const open = svg.match(/<svg\b([^>]*)>/);
    if (!open) throw new Error(`No <svg> root in ${name}`);
    const inner = svg.slice(open.index + open[0].length, svg.lastIndexOf("</svg>")).trim();
    const attrs = parseAttrs(open[1]);
    if (!attrs.viewBox) throw new Error(`${name} is missing a viewBox`);
    return { attrs, inner };
}

function toSymbol(name, attrs, inner) {
    const symbolAttrs = [`id="${name}"`];
    for (const [key, value] of Object.entries(attrs)) {
        if (KEEP_ATTRS.has(key)) symbolAttrs.push(`${key}="${value}"`);
    }
    return `<symbol ${symbolAttrs.join(" ")}>${inner}</symbol>`;
}

function collectIcons() {
    const icons = new Map();
    for (const group of SRC_GROUPS) {
        const dir = join(SRC_DIR, group);
        if (!existsSync(dir)) continue;
        for (const file of readdirSync(dir)) {
            if (!file.endsWith(".svg")) continue;
            const name = basename(file, ".svg");
            if (icons.has(name)) {
                throw new Error(`Duplicate icon name "${name}" (found again in ${group}/)`);
            }
            const raw = readFileSync(join(dir, file), "utf8");
            // prefixIds per-glyph so internal ids (gradients, clip-paths) can't
            // collide once every symbol lives in one document.
            const { data } = optimize(raw, {
                path: file,
                ...spriteConfig,
                plugins: [...spriteConfig.plugins, { name: "prefixIds", params: { prefix: name } }],
            });
            const { attrs, inner } = parseSvg(data, name);
            icons.set(name, { symbol: toSymbol(name, attrs, inner), inner });
        }
    }
    return icons;
}

const icons = collectIcons();
const names = [...icons.keys()].sort();

// 1. Sprite sheet (build output, served as a static asset).
const symbols = names.map((n) => icons.get(n).symbol).join("");
const sprite =
    `<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" style="position:absolute;width:0;height:0;overflow:hidden">` +
    `<defs>${symbols}</defs></svg>\n`;
mkdirSync(OUT_DIR, { recursive: true });
writeFileSync(join(OUT_DIR, "sprite.svg"), sprite, "utf8");

// 2. Manifest (committed).
writeFileSync(MANIFEST_PATH, `${JSON.stringify({ icons: names, aliases: {} }, null, 2)}\n`, "utf8");

// 3. Lit glyph module for shadow-DOM components (committed). Each export is a
//    bare `svg` fragment — wrap it in your own <svg> in the component's render():
//      import { x } from './icons.generated.js';
//      html`<svg class="icon" viewBox="0 0 24 24">${x}</svg>`
const jsExports = names
    .map((n) => `export const ${camelCase(n)} = /*#__PURE__*/ svg\`${icons.get(n).inner}\`;`)
    .join("\n");
const jsModule =
    "/* eslint-disable */\n" +
    "// @generated by scripts/build_icon_sprite.mjs from static/icons/src/ — DO NOT EDIT.\n" +
    "// Inline glyph fragments for SHADOW-DOM Lit components (they can't reach the\n" +
    "// document sprite via <use>). Wrap each in your own <svg> in render(); the\n" +
    "// $:icon() macro / <ol-icon> cover the light-DOM/template case.\n" +
    "import { svg } from 'lit';\n\n" +
    `${jsExports}\n`;
writeFileSync(JS_MODULE_PATH, jsModule, "utf8");

console.log(`Built ${names.length} icons:`);
console.log(`  sprite   → ${join(OUT_DIR, "sprite.svg")}`);
console.log(`  manifest → ${MANIFEST_PATH}`);
console.log(`  module   → ${JS_MODULE_PATH}`);
