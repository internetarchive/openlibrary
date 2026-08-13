import { LitElement, html, nothing } from 'lit';

const SIZE_CLASSES = new Map([
    ['sm', 'ol-icon--sm'],
    ['md', 'ol-icon--md'],
    ['lg', 'ol-icon--lg'],
]);

// The hashed sprite URL rides on the <meta name="ol-icon-sprite"> tag. Resolved
// lazily so the module still loads where the tag is absent (tests, fragments).
let spriteUrl = null;
function getSpriteUrl() {
    spriteUrl ??= document.querySelector('meta[name="ol-icon-sprite"]')?.content || '/static/icons/sprite.svg';
    return spriteUrl;
}

/**
 * A single icon from the Open Library icon sprite, referenced via
 * `<use href="…sprite.svg#icon-name">`.
 *
 * Renders into the light DOM so the global ol-icon.css applies and the glyph's
 * `currentColor` strokes inherit from context. The client-side counterpart of
 * the `$:macros.icon()` macro — same sprite, same CSS; prefer the macro in
 * server-rendered templates. Inside another component's shadow root, inline the
 * glyph from icons.generated.js instead: <use> is unreliable there.
 *
 * @element ol-icon
 *
 * @prop {String} name  - Icon name (e.g. "search"); the sprite symbol is "icon-<name>".
 * @prop {String} size  - "sm" (16px) | "md" (20px, default) | "lg" (24px). For a
 *                        one-off, set width/height on the host in CSS instead —
 *                        the inner <svg> fills it and the box is right pre-upgrade.
 * @prop {String} label - Accessible name; exposes the icon as role="img". Without
 *                        it the icon is aria-hidden.
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

    // Light DOM — see class comment.
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
