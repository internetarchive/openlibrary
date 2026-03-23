#!/usr/bin/env node
/**
 * Builds an SVG sprite sheet from Lucide icons and custom icons.
 *
 * Usage: node scripts/build-icons.js
 *
 * Reads icon names from the ICONS list below, pulls SVG content from
 * node_modules/lucide-static/icons/, and also includes any custom
 * SVGs from static/icons/custom/. Outputs static/icons/sprite.svg.
 */

const fs = require('fs');
const path = require('path');

// Icons to include in the sprite. Add names here as migration proceeds.
// Names must match filenames in node_modules/lucide-static/icons/ (without .svg).
const ICONS = [
    // Navigation
    'menu',
    'search',
    'x',
    'chevron-right',
    'chevron-down',
    'chevron-left',
    'chevron-up',
    'arrow-left',
    'arrow-right',
    'arrow-up-down',
    'external-link',

    // Actions
    'edit',
    'trash-2',
    'share',
    'download',
    'copy',
    'plus',
    'check',
    'check-circle',

    // Content
    'book-open',
    'book-marked',
    'bookmark',
    'library',
    'heart',
    'star',
    'list',
    'tag',

    // Status/Feedback
    'alert-triangle',
    'alert-circle',
    'info',
    'lock',
    'eye',
    'eye-off',
    'circle-help',
    'loader',

    // Communication
    'message-square',

    // Misc
    'globe',
    'map-pin',
    'scan-barcode',
    'merge',
    'hand-helping',
    'headphones',
    'qr-code',
];

const LUCIDE_ICONS_DIR = path.join(__dirname, '..', 'node_modules', 'lucide-static', 'icons');
const CUSTOM_ICONS_DIR = path.join(__dirname, '..', 'static', 'icons', 'custom');
const OUTPUT_FILE = path.join(__dirname, '..', 'static', 'icons', 'sprite.svg');

function extractSvgContent(svgString) {
    // Remove XML declaration and comments
    let content = svgString
        .replace(/<\?xml[^?]*\?>\s*/g, '')
        .replace(/<!--[\s\S]*?-->\s*/g, '');

    // Extract inner content between <svg> tags
    const match = content.match(/<svg[^>]*>([\s\S]*)<\/svg>/);
    if (!match) {
        throw new Error('Could not parse SVG content');
    }
    return match[1].trim();
}

function buildSymbol(id, innerContent) {
    return `  <symbol id="${id}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">\n    ${innerContent}\n  </symbol>`;
}

function main() {
    const symbols = [];
    let errors = 0;

    // Process Lucide icons
    for (const name of ICONS) {
        const filePath = path.join(LUCIDE_ICONS_DIR, `${name}.svg`);
        if (!fs.existsSync(filePath)) {
            console.error(`Warning: Lucide icon "${name}" not found at ${filePath}`);
            errors++;
            continue;
        }
        const svg = fs.readFileSync(filePath, 'utf8');
        const inner = extractSvgContent(svg);
        symbols.push(buildSymbol(name, inner));
    }

    // Process custom icons
    if (fs.existsSync(CUSTOM_ICONS_DIR)) {
        const customFiles = fs.readdirSync(CUSTOM_ICONS_DIR).filter(f => f.endsWith('.svg'));
        for (const file of customFiles) {
            const name = path.basename(file, '.svg');
            const svg = fs.readFileSync(path.join(CUSTOM_ICONS_DIR, file), 'utf8');
            const inner = extractSvgContent(svg);
            symbols.push(buildSymbol(name, inner));
            console.log(`  Custom icon: ${name}`);
        }
    }

    // Build sprite
    const sprite = `<svg xmlns="http://www.w3.org/2000/svg" style="display:none">\n<defs>\n${symbols.join('\n')}\n</defs>\n</svg>\n`;

    // Ensure output directory exists
    const outputDir = path.dirname(OUTPUT_FILE);
    fs.mkdirSync(outputDir, { recursive: true });

    fs.writeFileSync(OUTPUT_FILE, sprite);
    console.log(`Built sprite with ${symbols.length} icons → ${OUTPUT_FILE}`);

    if (errors > 0) {
        console.error(`${errors} icon(s) not found — check names against lucide-static`);
        process.exit(1);
    }
}

main();
