/**
 * Build the Open Library icon assets from the canonical sources in
 * static/icons/src/<group>/ (each a single 24x24 / currentColor SVG). Groups
 * are attribution folders (lucide/, custom/, ...), all read identically — the
 * set is library-agnostic and new folders are picked up automatically.
 *
 * One source, three outputs:
 *   1. <out>/sprite.svg            — a <symbol> sheet served as a hashed static
 *                                    asset and referenced by
 *                                    <use href="…sprite.svg#icon-name"> (the
 *                                    $:macros.icon() macro and the <ol-icon>
 *                                    component). For the document / light DOM.
 *   2. static/icons/manifest.json  — sorted icon-name list (committed; drives the
 *                                    /developers/design gallery + name lint).
 *   3. openlibrary/components/lit/icons.generated.js — Lit `svg` glyph fragments
 *                                    (committed) for SHADOW-DOM components, which
 *                                    cannot reach the document sprite via <use>
 *                                    and must inline the geometry instead.
 *
 * Source SVGs are authored clean (24x24, currentColor, no width/height), so this
 * script has NO dependencies — only Node built-ins. That keeps `make icons` and
 * the freshness check runnable everywhere (CI, containers, fresh checkouts)
 * without installing devDependencies.
 *
 * Usage: node scripts/build_icon_sprite.mjs [--out <dir>]
 *   --out defaults to static/build/icons
 */
import { readFileSync, readdirSync, writeFileSync, mkdirSync } from "node:fs";
import { join, dirname, basename } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SRC_DIR = join(ROOT, "static", "icons", "src");
// Every subdirectory of src/ is a source group; the folder name records where
// the geometry came from and nothing else. Discovered (not hardcoded) so
// adding glyphs from a new library never touches this script; sorted so the
// duplicate-name check fails deterministically.
const SRC_GROUPS = readdirSync(SRC_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
const MANIFEST_PATH = join(ROOT, "static", "icons", "manifest.json");
const JS_MODULE_PATH = join(ROOT, "openlibrary", "components", "lit", "icons.generated.js");

// Symbol ids are addressed from page markup as URL fragments (…#icon-name), so
// they are namespaced to keep the refs self-describing and bare names like
// "search" or "code" free. Callers still use the bare name; the macro and
// <ol-icon> add the prefix when they build the <use href>.
const ID_PREFIX = "icon-";

// A name becomes both a sprite id and a JS identifier in icons.generated.js, so
// it is held to kebab-case starting with a letter. Unchecked, "3d-view.svg" would
// emit `export const 3dView` and break the build from a generated file that names
// no source.
const NAME_RE = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;

const outArgIndex = process.argv.indexOf("--out");
const OUT_DIR = outArgIndex !== -1 ? process.argv[outArgIndex + 1] : join(ROOT, "static", "build", "icons");

// Presentation/structural attributes worth carrying from the source <svg> onto
// the <symbol>. Everything else (xmlns, width, height, class, style, id, aria-*)
// is dropped — sizing, stroke weight and a11y are decided at the point of use.
//
// stroke-width is deliberately NOT kept: a presentation attribute on the
// <symbol> outranks any inherited value, and CSS cannot select into a <use>
// shadow tree, so a baked weight would be unoverridable. Dropped, the geometry
// inherits `stroke-width` from the referencing <svg> — see the --icon-stroke-*
// tokens in static/css/components/ol-icon.css. Shadow-DOM components are
// unaffected: they wrap the icons.generated.js fragments in their own <svg> and
// already set stroke there.
const KEEP_ATTRS = new Set([
    "viewBox",
    "fill",
    "stroke",
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
    const symbolAttrs = [`id="${ID_PREFIX}${name}"`];
    for (const [key, value] of Object.entries(attrs)) {
        if (KEEP_ATTRS.has(key)) symbolAttrs.push(`${key}="${value}"`);
    }
    return `<symbol ${symbolAttrs.join(" ")}>${inner}</symbol>`;
}

function collectIcons() {
    const icons = new Map();
    // camelCase identifier -> the icon name that claimed it. Two different names
    // can collide here even when both are unique ("heading-1" and "heading1"),
    // which would emit the same `export const` twice.
    const identifiers = new Map();
    for (const group of SRC_GROUPS) {
        const dir = join(SRC_DIR, group);
        for (const file of readdirSync(dir)) {
            if (!file.endsWith(".svg")) continue;
            const name = basename(file, ".svg");
            if (!NAME_RE.test(name)) {
                throw new Error(`Invalid icon name "${name}" in ${group}/${file} — use kebab-case starting with a letter, e.g. arrow-left.`);
            }
            if (icons.has(name)) {
                throw new Error(`Duplicate icon name "${name}" (found again in ${group}/)`);
            }
            const identifier = camelCase(name);
            if (identifiers.has(identifier)) {
                throw new Error(
                    `Icon names "${identifiers.get(identifier)}" and "${name}" both map to the JS identifier "${identifier}" in icons.generated.js — rename one.`,
                );
            }
            identifiers.set(identifier, name);
            const raw = readFileSync(join(dir, file), "utf8");
            // Sources are pre-optimized and id-free, so we parse them directly.
            // (If an id-bearing glyph — gradient/clip-path — is ever added, give
            // its inner ids a per-glyph prefix here too, the way symbol ids get
            // ID_PREFIX, so they cannot collide inside the sprite.)
            const { attrs, inner } = parseSvg(raw, name);
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
// The IIFE wrapper puts the PURE annotation before a call expression — the only
// position Rolldown (and terser) honor, so unused glyphs tree-shake out.
const jsExports = names
    .map((n) => `export const ${camelCase(n)} = /*#__PURE__*/ (() => svg\`${icons.get(n).inner}\`)();`)
    .join("\n");
const jsModule =
    "/* eslint-disable */\n" +
    "// @generated by scripts/build_icon_sprite.mjs from static/icons/src/ — DO NOT EDIT.\n" +
    "// Inline glyph fragments for SHADOW-DOM Lit components (they can't reach the\n" +
    "// document sprite via <use>). Wrap each in your own <svg> in render(); the\n" +
    "// $:macros.icon() macro / <ol-icon> cover the light-DOM/template case.\n" +
    "import { svg } from 'lit';\n\n" +
    `${jsExports}\n`;
writeFileSync(JS_MODULE_PATH, jsModule, "utf8");

console.log(`Built ${names.length} icons:`);
console.log(`  sprite   → ${join(OUT_DIR, "sprite.svg")}`);
console.log(`  manifest → ${MANIFEST_PATH}`);
console.log(`  module   → ${JS_MODULE_PATH}`);
