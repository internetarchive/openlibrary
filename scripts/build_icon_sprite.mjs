/**
 * Build the icon assets from static/icons/src/<group>/ (24x24, currentColor
 * SVGs; groups are attribution folders, all read identically). Three outputs,
 * all committed so a fresh checkout renders icons without running a build:
 *   1. static/icons/sprite.svg — <symbol> sheet for <use> from the document/light DOM.
 *   2. static/icons/manifest.json — sorted name list.
 *   3. openlibrary/components/lit/icons.generated.js — inline Lit fragments for
 *      shadow-DOM components, which can't reach the sprite.
 *
 * No dependencies, only Node built-ins, so `make icons` and the freshness check
 * run anywhere without an npm install.
 *
 * Usage: node scripts/build_icon_sprite.mjs
 */
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join, dirname, basename } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SRC_DIR = join(ROOT, "static", "icons", "src");
// Source groups are discovered, not hardcoded, so a new library's folder needs
// no edit here. Sorted so the duplicate-name check fails deterministically.
const SRC_GROUPS = readdirSync(SRC_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
const SPRITE_PATH = join(ROOT, "static", "icons", "sprite.svg");
const MANIFEST_PATH = join(ROOT, "static", "icons", "manifest.json");
const JS_MODULE_PATH = join(ROOT, "openlibrary", "components", "lit", "icons.generated.js");

// Namespaces the symbol ids, which are document-wide URL fragments. Callers pass
// bare names; the macro and <ol-icon> add the prefix.
const ID_PREFIX = "icon-";

// A name becomes a JS identifier too, so "3d-view.svg" would emit
// `export const 3dView` and break the build from a generated file.
const NAME_RE = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;

// Carried from the source <svg> onto the <symbol>; everything else is dropped so
// sizing, stroke weight and a11y are decided at the point of use. stroke-width in
// particular: on the symbol it would outrank the inherited value and CSS can't
// select into a <use> shadow tree, so it must come from the referencing <svg>
// (the --icon-stroke-* tokens in static/css/components/ol-icon.css).
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
    // camelCase identifier -> the name that claimed it. Distinct names can still
    // collide ("heading-1" / "heading1"), emitting the same `export const` twice.
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
            // Sources are id-free. An id-bearing glyph (gradient, clip-path)
            // would need its inner ids prefixed here, like ID_PREFIX does.
            const { attrs, inner } = parseSvg(raw, name);
            icons.set(name, { symbol: toSymbol(name, attrs, inner), inner });
        }
    }
    return icons;
}

const icons = collectIcons();
const names = [...icons.keys()].sort();

// 1. Sprite sheet, served as a static asset. One <symbol> per line: the file is
// committed, so a single-line sprite would make every icon change one unreadable
// diff and every concurrent icon PR an unmergeable conflict.
const symbols = names.map((n) => icons.get(n).symbol).join("\n");
const sprite =
    `<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" style="position:absolute;width:0;height:0;overflow:hidden">` +
    `<defs>\n${symbols}\n</defs></svg>\n`;
writeFileSync(SPRITE_PATH, sprite, "utf8");

// 2. Manifest.
writeFileSync(MANIFEST_PATH, `${JSON.stringify({ icons: names, aliases: {} }, null, 2)}\n`, "utf8");

// 3. Lit glyph module for shadow-DOM components. The IIFE puts the
// PURE annotation before a call expression — the only position Rolldown (and
// terser) honor, so unused glyphs tree-shake out.
const jsExports = names
    .map((n) => `export const ${camelCase(n)} = /*#__PURE__*/ (() => svg\`${icons.get(n).inner}\`)();`)
    .join("\n");
const jsModule =
    "/* eslint-disable */\n" +
    "// @generated by scripts/build_icon_sprite.mjs from static/icons/src/ — DO NOT EDIT.\n" +
    "// Inline glyphs for shadow-DOM Lit components; wrap each in your own <svg>.\n" +
    "import { svg } from 'lit';\n\n" +
    `${jsExports}\n`;
writeFileSync(JS_MODULE_PATH, jsModule, "utf8");

console.log(`Built ${names.length} icons:`);
console.log(`  sprite   → ${SPRITE_PATH}`);
console.log(`  manifest → ${MANIFEST_PATH}`);
console.log(`  module   → ${JS_MODULE_PATH}`);
