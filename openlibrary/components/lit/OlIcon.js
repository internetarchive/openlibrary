import { LitElement, html, nothing } from 'lit';

const SIZE_CLASSES = { sm: 'ol-icon--sm', md: 'ol-icon--md', lg: 'ol-icon--lg' };

/**
 * A single icon from the Open Library icon sprite.
 *
 * Renders into the **light DOM** (no shadow root) and references the sprite via
 * a same-document `<use href="#name">`. Both choices are deliberate: the sprite
 * is inlined once per page (see the icon_sprite() helper), and same-document
 * references resolve in every browser OL supports — external references
 * (`file.svg#name`) are unreliable in older Safari/iOS. Same-document `<use>`
 * also cannot cross a shadow boundary, so this element must live in the light
 * DOM; for icons inside another component's shadow root, inline the glyph
 * instead of using <ol-icon>. In the light DOM the glyph also inherits `color`
 * for its `currentColor` strokes, themed by whatever context it sits in.
 *
 * This is the client-side counterpart of the `$:icon()` Templetor macro — both
 * point at the same sprite and share static/css/components/ol-icon.css, so an
 * icon looks identical whether server- or component-rendered. Use this inside
 * Lit components; use the macro in server-rendered templates.
 *
 * Decorative by default (`aria-hidden`). Pass `label` to expose the icon to
 * assistive tech as `role="img"` with that accessible name.
 *
 * @element ol-icon
 *
 * @prop {String} name  - Icon name (a symbol id in the sprite, e.g. "search").
 * @prop {String} size  - "sm" (16px) | "md" (20px, default) | "lg" (24px), or a
 *                        raw pixel number (e.g. "32") for a one-off size.
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

    // Light DOM so the global ol-icon.css applies and the external <use>
    // reference resolves in every supported browser (see class comment).
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

        const named = Object.prototype.hasOwnProperty.call(SIZE_CLASSES, this.size);
        const sizeClass = named ? SIZE_CLASSES[this.size] : SIZE_CLASSES.md;
        const px = !named && /^\d+$/.test(this.size) ? `${this.size}px` : null;
        const labeled = Boolean(this.label && this.label.trim());

        return html`<svg
            class="ol-icon ${sizeClass}"
            style=${px ? `width:${px};height:${px}` : nothing}
            role=${labeled ? 'img' : nothing}
            aria-label=${labeled ? this.label : nothing}
            aria-hidden=${labeled ? nothing : 'true'}
            focusable="false"
        ><use href="#${this.name}"></use></svg>`;
    }
}

customElements.define('ol-icon', OlIcon);
