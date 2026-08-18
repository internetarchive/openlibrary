import { html, svg } from 'lit';

/**
 * Lucide glyphs used by the books-display components, inlined until the
 * shared <ol-icon> system (PR #12955) lands — then swap these for it.
 * Each is a bare <svg> path set; the wrapping <svg> attrs live in `icon()`.
 */
const PATHS = {
    plus: svg`<path d="M5 12h14"/><path d="M12 5v14"/>`,
    check: svg`<path d="M20 6 9 17l-5-5"/>`,
    bookmark: svg`<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>`,
    'book-open': svg`<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>`,
    'circle-check': svg`<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>`,
    'circle-pause': svg`<circle cx="12" cy="12" r="10"/><line x1="10" x2="10" y1="15" y2="9"/><line x1="14" x2="14" y1="15" y2="9"/>`,
    'list-plus': svg`<path d="M11 12H3"/><path d="M16 6H3"/><path d="M16 18H3"/><path d="M18 9v6"/><path d="M21 12h-6"/>`,
    'chevron-right': svg`<path d="m9 18 6-6-6-6"/>`,
    'chevron-left': svg`<path d="m15 18-6-6 6-6"/>`,
    'chevron-down': svg`<path d="m6 9 6 6 6-6"/>`,
    'arrow-up-right': svg`<path d="M7 7h10v10"/><path d="M7 17 17 7"/>`,
    // Not Lucide: two portrait cover thumbnails, for the carousel view.
    // Two (not three) so the gaps survive at 14px.
    'covers-row': svg`<rect width="7" height="14" x="3" y="5" rx="1"/><rect width="7" height="14" x="14" y="5" rx="1"/>`,
    list: svg`<path d="M3 12h.01"/><path d="M3 18h.01"/><path d="M3 6h.01"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M8 6h13"/>`,
    star: svg`<path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/>`,
    loader: svg`<path d="M12 2v4"/><path d="m16.2 7.8 2.9-2.9"/><path d="M18 12h4"/><path d="m16.2 16.2 2.9 2.9"/><path d="M12 18v4"/><path d="m4.9 19.1 2.9-2.9"/><path d="M2 12h4"/><path d="m4.9 4.9 2.9 2.9"/>`,
};

/**
 * @param {keyof typeof PATHS} name
 * @param {{fill?: string, strokeWidth?: number, cls?: string}} [opts]
 */
export function icon(name, { fill = 'none', strokeWidth = 2, cls = 'obd-icon' } = {}) {
    return html`<svg class=${cls} viewBox="0 0 24 24" fill=${fill} stroke="currentColor" stroke-width=${strokeWidth} stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PATHS[name]}</svg>`;
}

export const ICON_NAMES = Object.keys(PATHS);
