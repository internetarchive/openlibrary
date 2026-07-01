import { LitElement, html, css, nothing } from 'lit';
import { FocusableHostMixin } from './utils/focusable-host-mixin.js';

/**
 * OLChip - A pill-shaped interactive chip web component
 *
 * Supports two sizes, a selected state with a close icon,
 * click events, and optional link behavior via href.
 *
 * @prop {Boolean} selected - Whether the chip is in a selected state
 * @prop {String} size - Chip size: "small" or "medium" (default)
 * @prop {String} variant - Domain category that tints the chip:
 *   "language" | "subject" | "genre" | "author" | "place" | "neutral".
 *   Omit for the default (white / solid-blue-when-selected) chip. The chip
 *   maps the variant to a soft-tint palette internally (see colors.css); a
 *   variant chip keeps its tint when `selected` and just gains a close icon.
 * @prop {String} href - When set, the chip renders as a link
 * @prop {String} count - Optional count displayed to the right of the label
 * @prop {String} accessibleLabel - Override aria-label on the inner interactive element
 *
 * @fires ol-chip-select - Fired on click. detail: { selected: Boolean }
 *
 * @slot - The chip's label content
 *
 * @example
 * <ol-chip>Fiction</ol-chip>
 *
 * @example
 * <ol-chip selected>History</ol-chip>
 *
 * @example
 * <!-- Removable, category-colored filter pill -->
 * <ol-chip variant="language" selected>English</ol-chip>
 *
 * @example
 * <ol-chip size="small" count="76" href="/subjects/fiction">Fiction</ol-chip>
 */
export class OLChip extends FocusableHostMixin(LitElement) {
    static properties = {
        selected: { type: Boolean, reflect: true },
        size: { type: String, reflect: true },
        variant: { type: String, reflect: true },
        href: { type: String },
        count: { type: String },
        accessibleLabel: { type: String, attribute: 'accessible-label' },
    };

    static styles = css`
        :host {
            --chip-padding-block: var(--spacing-xs);
            --chip-padding-inline: var(--spacing-md);
            --chip-icon-size: 14px;
            --chip-icon-gap: var(--spacing-2xs);

            /* Color slots. Default = idle, unselected neutral chip; overridden
               below by [selected] and by each domain [variant]. */
            --_chip-bg: var(--white);
            --_chip-fg: var(--dark-grey);
            --_chip-border: var(--color-border-subtle);
            --_chip-bg-hover: var(--lightest-grey);
            /* Border darkens in step with the fill on hover, matching
               ol-button[variant="secondary"]. Derived from the resting border
               so every variant tracks its own color: a ~8% mix toward black
               lands the neutral chip exactly on --light-grey (87% → 80%) and
               nudges each domain tint's border down by a proportional amount. */
            --_chip-border-hover: color-mix(in srgb, var(--_chip-border) 92%, black);
            --_chip-count-fg: #777;

            display: inline-block;
        }

        :host([size="small"]) {
            --chip-padding-block: var(--spacing-2xs);
            --chip-padding-inline: var(--spacing-sm);
            --chip-icon-size: 12px;
        }

        .chip {
            position: relative;
            display: inline-flex;
            align-items: center;
            padding: var(--chip-padding-block) var(--chip-padding-inline);
            border: var(--border-width) solid var(--_chip-border);
            border-radius: var(--border-radius-chip);
            font-family: var(--font-family-button);
            font-size: var(--font-size-body-medium);
            line-height: var(--line-height-chip);
            background: var(--_chip-bg);
            color: var(--_chip-fg);
            cursor: pointer;
            user-select: none;
            text-decoration: none;
        }

        @media (hover: hover) and (pointer: fine) {
            .chip:hover {
                background: var(--_chip-bg-hover);
                border-color: var(--_chip-border-hover);
            }
        }

        .chip:active {
            transform: scale(0.97);
        }

        .chip:focus-visible {
            outline: none;
            box-shadow: var(--box-shadow-focus);
        }

        /* Default selected (no domain variant): solid primary-blue fill. */
        :host([selected]:not([variant])) {
            --_chip-bg: var(--primary-blue);
            --_chip-fg: var(--white);
            --_chip-border: var(--primary-blue);
            --_chip-bg-hover: var(--primary-blue);
            /* This chip lightens on hover via a brightness() filter (below)
               rather than darkening its fill, so keep the border color put — the
               filter carries the whole pill, edge included. */
            --_chip-border-hover: var(--_chip-border);
            --_chip-count-fg: #c6e1f0;
        }

        @media (hover: hover) and (pointer: fine) {
            :host([selected]:not([variant])) .chip:hover {
                filter: brightness(1.1);
            }
        }

        /* Selected chips reserve room for the leading close icon (all variants). */
        :host([selected]) .chip {
            padding-inline-start: calc(var(--chip-padding-inline) + var(--chip-icon-size) + var(--chip-icon-gap));
        }

        /* ── Domain variants: soft category-colored tint ──────────────────
           The tint is identical whether or not the chip is selected; the
           [selected] rule above only reserves space for the close icon, so a
           selected variant chip reads as a removable, category-colored pill. */
        :host([variant="language"]) {
            --_chip-bg: var(--color-chip-language-bg);
            --_chip-fg: var(--color-chip-language-fg);
            --_chip-border: var(--color-chip-language-border);
            --_chip-bg-hover: var(--color-chip-language-bg-hover);
            --_chip-count-fg: var(--color-chip-language-fg);
        }

        :host([variant="subject"]) {
            --_chip-bg: var(--color-chip-subject-bg);
            --_chip-fg: var(--color-chip-subject-fg);
            --_chip-border: var(--color-chip-subject-border);
            --_chip-bg-hover: var(--color-chip-subject-bg-hover);
            --_chip-count-fg: var(--color-chip-subject-fg);
        }

        :host([variant="genre"]) {
            --_chip-bg: var(--color-chip-genre-bg);
            --_chip-fg: var(--color-chip-genre-fg);
            --_chip-border: var(--color-chip-genre-border);
            --_chip-bg-hover: var(--color-chip-genre-bg-hover);
            --_chip-count-fg: var(--color-chip-genre-fg);
        }

        :host([variant="author"]) {
            --_chip-bg: var(--color-chip-author-bg);
            --_chip-fg: var(--color-chip-author-fg);
            --_chip-border: var(--color-chip-author-border);
            --_chip-bg-hover: var(--color-chip-author-bg-hover);
            --_chip-count-fg: var(--color-chip-author-fg);
        }

        :host([variant="place"]) {
            --_chip-bg: var(--color-chip-place-bg);
            --_chip-fg: var(--color-chip-place-fg);
            --_chip-border: var(--color-chip-place-border);
            --_chip-bg-hover: var(--color-chip-place-bg-hover);
            --_chip-count-fg: var(--color-chip-place-fg);
        }

        :host([variant="neutral"]) {
            --_chip-bg: var(--color-chip-neutral-bg);
            --_chip-fg: var(--color-chip-neutral-fg);
            --_chip-border: var(--color-chip-neutral-border);
            --_chip-bg-hover: var(--color-chip-neutral-bg-hover);
            --_chip-count-fg: var(--accessible-grey);
        }

        /* Small size */
        :host([size="small"]) .chip {
            font-size: var(--font-size-label-medium);
        }

        /* Close icon for selected state */
        .icon-slot {
            position: absolute;
            inset-inline-start: var(--chip-padding-inline);
            top: 50%;
            transform: translateY(-50%);
            width: var(--chip-icon-size);
            height: var(--chip-icon-size);
        }

        .icon {
            width: var(--chip-icon-size);
            height: var(--chip-icon-size);
        }

        /* Count */
        .count {
            margin-inline-start: var(--spacing-2xs);
            color: var(--_chip-count-fg);
            font-size: 0.85em;
            font-variant-numeric: tabular-nums;
        }
    `;

    constructor() {
        super();
        this.selected = false;
        this.size = 'medium';
        this.variant = null;
        this.href = null;
        this.count = null;
        this.accessibleLabel = null;
    }

    _handleClick() {
        this.dispatchEvent(new CustomEvent('ol-chip-select', {
            bubbles: true,
            composed: true,
            detail: { selected: !this.selected },
        }));
    }

    _renderIcons() {
        if (!this.selected) return nothing;

        return html`
            <span class="icon-slot">
                <svg
                    class="icon"
                    aria-hidden="true"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="3"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                >
                    <path d="M18 6 6 18"/><path d="m6 6 12 12"/>
                </svg>
            </span>
        `;
    }

    _renderCount() {
        if (this.count === null) return nothing;

        return html`<span class="count">${this.count}</span>`;
    }

    render() {
        // The <span class="label"> wrapping <slot> fixes issue #12488:
        // .chip is display: inline-flex, so without a wrapper each
        // slotted node (e.g. a text node followed by an <em> highlight)
        // becomes its own flex item, and per the Flexbox spec
        // leading/trailing whitespace inside a flex item is collapsed.
        // The wrapper makes slotted content a single flex item that
        // lays out as normal inline text, preserving spaces around
        // <em>. No styling on .label is needed (and adding it could
        // block useful inheritance such as white-space: nowrap from
        // callers).
        const content = html`
            ${this._renderIcons()}
            <span class="label"><slot></slot></span>
            ${this._renderCount()}
        `;

        if (this.href) {
            return html`
                <a class="chip" href=${this.href}
                    aria-label=${this.accessibleLabel || nothing}
                    @click=${this._handleClick}>
                    ${content}
                </a>
            `;
        }

        return html`
            <button class="chip" type="button"
                aria-label=${this.accessibleLabel || nothing}
                aria-pressed=${this.selected}
                @click=${this._handleClick}>
                ${content}
            </button>
        `;
    }
}

if (!customElements.get('ol-chip')) {
    customElements.define('ol-chip', OLChip);
}
