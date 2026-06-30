import { LitElement, html } from 'lit';
import { _ } from './utils/i18n.js';

/**
 * A callout-style announcement banner.
 *
 * Renders into the **light DOM** (no shadow root) so the banner is fully
 * styled at first paint by `static/css/components/ol-banner.css` — before
 * the component JS runs — and degrades gracefully without JavaScript.
 * Banners are server-rendered page chrome, often above the fold, so
 * first-paint fidelity outranks style encapsulation here (see ol-button
 * for the same trade-off and hydration pattern).
 *
 * The announcement content is server-rendered as children — already
 * translated via $_(), visible to search engines. On upgrade, the
 * component captures those children, re-renders them inside its own
 * structure, and adds the variant icon and close button. Its only owned
 * string is the close button label (override via `label-close` for i18n).
 *
 * The component owns no persistence. Dismissing fires `ol-banner-dismiss`
 * (with the optional `dismiss-id` in the detail) and removes the element —
 * what that means is the host application's business. In Open Library:
 *   - Visibility is decided server-side: the template only renders the
 *     banner if its dismissal cookie is absent (see design/banner.html).
 *   - Persistence is handled by a site-level listener (js/banner/index.js)
 *     that POSTs dismissals to /hide_banner.
 *
 * Banners appear on every page view, so there is deliberately no entrance
 * animation (the frequency principle) — only a brief exit transition on
 * dismiss.
 *
 * @element ol-banner
 *
 * @prop {String}  variant     - "neutral" (default) | "success" | "warning" | "danger"
 * @prop {String}  appearance  - "outlined" (default) shows a border and rounded
 *                               corners; "plain" removes both, for banners that
 *                               abut the edges of other UI.
 * @prop {String}  dismissId   - Opaque identifier passed in the dismiss event's
 *                               detail, for the host app's persistence layer.
 * @prop {Boolean} dismissible - Show a close button.
 * @prop {String}  labelClose  - Aria label for the close button (default: "Close")
 *
 * @slot - The (already translated, server-rendered) announcement content.
 * @slot icon - Optional custom icon (a child with slot="icon"), replacing the
 *              variant's built-in one. Light-DOM convention, not a real slot.
 *
 * @fires ol-banner-dismiss - Fired once when the banner is dismissed.
 *                            detail: { dismissId: String }
 *
 * @example
 * <ol-banner variant="warning" dismissible label-close="$_('Close')">
 *   $_("Open Library will be briefly unavailable on June 12 for maintenance.")
 * </ol-banner>
 *
 * @example
 * <!-- Persisted dismissal: server guards rendering, site glue persists -->
 * $if cookies().get('yrg26') != '1':
 *   <ol-banner dismiss-id="yrg26" data-cookie-duration-days="365" dismissible>
 *     <a href="/account/books/already-read/year/2026">$_("Set your 2026 Yearly Reading Goal")</a>
 *   </ol-banner>
 */
export class OlBanner extends LitElement {
    static properties = {
        variant: { type: String, reflect: true },
        appearance: { type: String, reflect: true },
        dismissId: { type: String, attribute: 'dismiss-id' },
        dismissible: { type: Boolean, reflect: true },
        labelClose: { type: String, attribute: 'label-close' },
    };

    // Render into the light DOM so the global stylesheet
    // (static/css/components/ol-banner.css, via ol-components.css) styles
    // the banner before and after hydration — no FOUC, no layout shift.
    createRenderRoot() {
        return this;
    }

    /** "i" glyph shown on neutral banners (the circle is drawn in CSS) */
    static _neutralIcon = html`<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="4.5" x2="12.01" y2="4.5"/><line x1="12" y1="11" x2="12" y2="18"/></svg>`;

    /** Check glyph shown on success banners (the circle is drawn in CSS) */
    static _successIcon = html`<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>`;

    /** Caution-triangle (yield) shown on warning banners: a filled, rounded
     *  triangle in the variant accent with a white exclamation. Self-contained
     *  (its own filled shape, not the CSS circle badge), so the warning icon
     *  reads as a distinct shape from the round danger badge. */
    static _warningIcon = html`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><path style="fill: var(--banner-accent)" d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" d="M12 9v4"/><path fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" d="M12 17h.01"/></svg>`;

    /** Exclamation glyph shown on danger banners (the circle is drawn in CSS) */
    static _dangerIcon = html`<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="6" x2="12" y2="13"/><line x1="12" y1="19.5" x2="12.01" y2="19.5"/></svg>`;

    static _icons = {
        neutral: OlBanner._neutralIcon,
        success: OlBanner._successIcon,
        warning: OlBanner._warningIcon,
        danger: OlBanner._dangerIcon,
    };

    /** Close (X) icon — the stroke-based glyph shared with ol-dialog / ol-toast */
    static _closeIcon = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;

    constructor() {
        super();
        this.variant = 'neutral';
        this.appearance = 'outlined';
        this.dismissId = '';
        this.dismissible = false;
        this.labelClose = _('Close');
        this._closing = false;
    }

    connectedCallback() {
        // Capture the author's children before Lit's first render so we can
        // re-insert them inside the structure we render (same pattern as
        // ol-button's label capture).
        if (!this._content) {
            this._customIcon = this.querySelector(':scope > [slot="icon"]');
            this._customIcon?.remove();
            this._content = document.createElement('span');
            this._content.className = 'ol-banner__content';
            while (this.firstChild) {
                this._content.appendChild(this.firstChild);
            }
        }
        super.connectedCallback();
        // Flush the first render synchronously within the upgrade task so
        // the icon and close button exist before the next paint.
        this.performUpdate();
    }

    firstUpdated() {
        // Signals to CSS that the inner structure is in the DOM, so the
        // pre-hydration icon placeholder can be dropped.
        this.setAttribute('hydrated', '');
    }

    /**
     * Dismiss the banner: fire ol-banner-dismiss, run the exit transition,
     * and remove the element from the DOM. Persistence is the host app's
     * concern — listen for the event (it bubbles) and use detail.dismissId.
     */
    dismiss() {
        if (this._closing) return;
        this._closing = true;
        this.dispatchEvent(new CustomEvent('ol-banner-dismiss', {
            detail: { dismissId: this.dismissId },
            bubbles: true,
            composed: true,
        }));

        // data-closing triggers the exit transition on the host
        this.setAttribute('data-closing', '');

        const finalize = () => this.remove();
        this.addEventListener('transitionend', (e) => {
            if (e.target === this && e.propertyName === 'opacity') finalize();
        });
        // Fallback in case no transition runs (e.g. prefers-reduced-motion)
        setTimeout(finalize, 300);
    }

    render() {
        const icon = OlBanner._icons[this.variant] ?? OlBanner._neutralIcon;
        return html`
            <span class="ol-banner__icon">${this._customIcon ?? icon}</span>
            ${this._content}
            ${this.dismissible ? html`
                <button
                    class="ol-banner__close"
                    aria-label=${this.labelClose}
                    @click=${() => this.dismiss()}
                >${OlBanner._closeIcon}</button>
            ` : ''}
        `;
    }
}

customElements.define('ol-banner', OlBanner);
