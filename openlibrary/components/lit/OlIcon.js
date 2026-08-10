import { LitElement, html, nothing } from 'lit';

const SIZE_CLASSES = new Map([
    ['sm', 'ol-icon--sm'],
    ['md', 'ol-icon--md'],
    ['lg', 'ol-icon--lg'],
]);

// The hashed sprite URL travels on the <meta name="ol-icon-sprite"> tag in
// <head>. Resolved lazily (not at module scope) so the module loads in
// documents without the tag — tests, fragments — falling back to the
// unhashed path.
let spriteUrl = null;
function getSpriteUrl() {
    spriteUrl ??= document.querySelector('meta[name="ol-icon-sprite"]')?.content || '/static/build/icons/sprite.svg';
    return spriteUrl;
}

/**
 * A single icon from the Open Library icon sprite.
 *
 * Renders into the **light DOM** (no shadow root) and references the sprite
 * asset via `<use href="…sprite.svg#icon-name">`. The sprite is one external
 * file, content-hashed and cached sitewide; its URL is carried by the
 * `<meta name="ol-icon-sprite">` tag emitted in site/head. Light DOM is
 * deliberate: the global ol-icon.css applies, and the glyph inherits `color`
 * for its `currentColor` strokes, themed by whatever context it sits in. For
 * icons inside another component's shadow root, inline the glyph from
 * icons.generated.js instead of using <ol-icon> — shadow icons stay
 * fetch-independent and paint with the component.
 *
 * This is the client-side counterpart of the `$:macros.icon()` Templetor macro — both
 * point at the same sprite and share static/css/components/ol-icon.css, so an
 * icon looks identical whether server- or component-rendered. Use this inside
 * Lit components; use the macro in server-rendered templates.
 *
 * Decorative by default (`aria-hidden`). Pass `label` to expose the icon to
 * assistive tech as `role="img"` with that accessible name.
 *
 * @element ol-icon
 *
 * @prop {String} name  - Icon name (e.g. "search"); the sprite symbol is "icon-<name>".
 * @prop {String} size  - "sm" (16px) | "md" (20px, default) | "lg" (24px). For a
 *                        one-off size, set width/height on the host in CSS — the
 *                        inner <svg> fills it, and unlike an attribute the box is
 *                        right before the component upgrades.
 * @prop {String} label - Accessible name. When set, the icon is exposed as
 *                        role="img"; when omitted, it is aria-hidden.
 *
 * @example
 * <ol-icon name="search"></ol-icon>
 * <ol-icon name="globe" size="lg" label="Language"></ol-icon>
 */
export class OlIcon extends LitElement {
    static properties = {
        name: { type: String, reflect: true },
        size: { type: String, reflect: true },
        label: { type: String },
    };

    // Light DOM so the global ol-icon.css applies and currentColor inherits
    // (see class comment).
    createRenderRoot() {
        return this;
    }

    constructor() {
        super();
        this.name = '';
        this.size = 'md';
        this.label = '';
    }

    render() {
        if (!this.name) return nothing;

        const sizeClass = SIZE_CLASSES.get(this.size) ?? SIZE_CLASSES.get('md');
        const labeled = Boolean(this.label && this.label.trim());

        return html`<svg
            class="ol-icon ${sizeClass}"
            role=${labeled ? 'img' : nothing}
            aria-label=${labeled ? this.label : nothing}
            aria-hidden=${labeled ? nothing : 'true'}
            focusable="false"
        ><use href="${getSpriteUrl()}#icon-${this.name}"></use></svg>`;
    }
}

customElements.define('ol-icon', OlIcon);
