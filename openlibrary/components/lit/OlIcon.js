import { LitElement, css, nothing } from 'lit';

import { glyphs } from './icons.generated.js';

/**
 * A single icon from the Open Library set.
 *
 * Self-contained: the glyph is inlined from icons.generated.js and styled inside
 * this element's shadow root, so one element works everywhere client-side —
 * plain markup, a Lit template, or another component's shadow DOM (where the
 * sprite's `<use href>` and the global ol-icon.css can't reach). The
 * `$:macros.icon()` macro is the server-rendered counterpart; prefer it in
 * templates, where it paints without waiting on JS.
 *
 * Color follows `currentColor`. Size comes from the `size` attribute, or set
 * width/height on the element to override it; stroke weight follows the size
 * unless `--ol-icon-stroke-width` says otherwise.
 *
 * @element ol-icon
 *
 * @prop {String} name  - Icon name, e.g. "search". See /developers/design#icons.
 * @prop {'sm' | 'md' | 'lg'} size  - "sm" (16px) | "md" (20px, default) | "lg" (24px).
 * @prop {String} label - Accessible name; exposes the icon as role="img". Without
 *                        it the icon is aria-hidden.
 * @prop {Boolean} filled - Paint the glyph's interior in currentColor, for
 *                          on/off states like a saved bookmark or a rated star.
 *
 * @cssprop [--ol-icon-stroke-width] - Stroke weight, overriding the size default.
 *
 * @example
 * <ol-icon name="search"></ol-icon>
 * <ol-icon name="globe" size="lg" label="Language"></ol-icon>
 * <ol-icon name="circle-check" filled></ol-icon>
 */
export class OlIcon extends LitElement {
    static properties = {
        name: { type: String, reflect: true },
        size: { type: String, reflect: true },
        label: { type: String },
        filled: { type: Boolean, reflect: true },
    };

    // The host box is sized here and again in ol-icon.css. The duplication is
    // load-bearing: :host only applies once the element upgrades, so the global
    // rules are what reserve the box beforehand — but they don't cross a shadow
    // boundary, so :host is what sizes the element inside another component.
    // Outer-tree rules beat :host, so a parent can still size it however it likes.
    static styles = css`
        :host {
            display: inline-flex;
            flex-shrink: 0;
            width: var(--icon-size-md);
            height: var(--icon-size-md);
            vertical-align: middle;
        }

        :host([size='sm']) {
            width: var(--icon-size-sm);
            height: var(--icon-size-sm);
        }

        :host([size='lg']) {
            width: var(--icon-size-lg);
            height: var(--icon-size-lg);
        }

        :host([hidden]) {
            display: none;
        }

        svg {
            display: block;
            width: 100%;
            height: 100%;
            stroke-width: var(--ol-icon-stroke-width, var(--icon-stroke-md));
        }

        :host([size='sm']) svg {
            stroke-width: var(--ol-icon-stroke-width, var(--icon-stroke-sm));
        }

        :host([size='lg']) svg {
            stroke-width: var(--ol-icon-stroke-width, var(--icon-stroke-lg));
        }

        /* The source's fill="none" is a presentation attribute, so CSS wins. */
        :host([filled]) svg {
            fill: currentColor;
        }
    `;

    constructor() {
        super();
        this.name = '';
        this.size = 'md';
        this.label = '';
        this.filled = false;
    }

    // Decorative by default; named only when the caller supplies a label. On the
    // host rather than the <svg> so assistive tech doesn't have to pierce the
    // shadow root, and so aria-hidden covers the whole element.
    willUpdate() {
        if (this.label && this.label.trim()) {
            this.setAttribute('role', 'img');
            this.setAttribute('aria-label', this.label);
            this.removeAttribute('aria-hidden');
        } else {
            this.setAttribute('aria-hidden', 'true');
            this.removeAttribute('role');
            this.removeAttribute('aria-label');
        }
    }

    render() {
        if (!this.name) return nothing;

        const glyph = glyphs[this.name];
        if (!glyph) {
            // Silent blanks are the failure mode people waste time on; a typo'd
            // or renamed icon should say so.
            // eslint-disable-next-line no-console
            console.warn(`<ol-icon>: no icon named "${this.name}". See /developers/design/icons for the gallery.`);
            return nothing;
        }
        return glyph;
    }
}

customElements.define('ol-icon', OlIcon);
