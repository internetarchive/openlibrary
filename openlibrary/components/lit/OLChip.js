import { LitElement, html, css, nothing } from 'lit';
import { FocusableHostMixin } from './utils/focusable-host-mixin.js';
import './OlIcon.js';

/**
 * OLChip - A pill-shaped interactive chip web component
 *
 * Supports two sizes, a selected state with a close icon,
 * click events, and optional link behavior via href.
 *
 * @prop {Boolean} selected - Whether the chip is in a selected state
 * @prop {"small" | "medium"} size - Default: "medium"
 * @prop {"language" | "subject" | "genre" | "author" | "place" | "neutral"} variant -
 *   Domain category that tints the chip.
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
            --chip-icon-gap: var(--spacing-xs);
            /* The x glyph paints across the middle of its 24-unit viewBox
               (6 -> 18, stroke included), leaving 3/16 of the icon box empty on
               each side. The slack is pulled back out below so the chip spaces
               the painted glyph rather than its box. */
            --_chip-icon-slack: calc(var(--chip-icon-size) * 3 / 16);

            /* Color slots. Default = idle, unselected neutral chip; overridden
               below by [selected] and by each domain [variant]. */
            --_chip-bg: var(--white);
            --_chip-fg: var(--color-text);
            --_chip-border: var(--color-border-subtle);
            --_chip-bg-hover: var(--color-control-hover);
            /* Border darkens in step with the fill on hover, matching
               ol-button[variant="secondary"]. Derived from the resting border
               so every variant tracks its own color: a ~8% mix toward black
               lands the neutral chip exactly on --light-grey (87% → 80%) and
               nudges each domain tint's border down by a proportional amount. */
            --_chip-border-hover: color-mix(in srgb, var(--_chip-border) 92%, black);
            --_chip-count-fg: var(--color-text-muted);
            /* Specular top edge, on ol-button's scale: full on the light tints,
               dialed down on the solid blue fill below. */
            --control-highlight-strength: 35%;

            display: inline-block;
        }

        :host([size="small"]) {
            --chip-padding-block: var(--spacing-2xs);
            --chip-padding-inline: var(--spacing-sm);
            --chip-icon-size: 12px;
            --chip-icon-gap: var(--spacing-2xs);
        }

        .chip {
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
            /* Raised look, matching ol-button. Declared here rather than on
               :host so :hover can retone the highlight and the surface never
               leaks to slotted content; held in a var so :focus-visible can
               layer the focus ring without restating the resting shadow. */
            --control-surface: var(--_chip-bg);
            --_chip-raised-shadow:
                var(--box-shadow-raised),
                inset 0 1px 0
                    color-mix(
                        in srgb,
                        var(--white) var(--control-highlight-strength),
                        var(--control-surface)
                    );
            box-shadow: var(--_chip-raised-shadow);
            cursor: pointer;
            user-select: none;
            text-decoration: none;
        }

        @media (hover: hover) and (pointer: fine) {
            .chip:hover {
                background: var(--_chip-bg-hover);
                border-color: var(--_chip-border-hover);
                /* Track the background, or the highlight stays toned to the
                   resting fill. */
                --control-surface: var(--_chip-bg-hover);
            }
        }

        .chip:active {
            transform: scale(var(--press-scale));
        }

        .chip:focus-visible {
            outline: none;
            box-shadow: var(--box-shadow-focus), var(--_chip-raised-shadow);
        }

        /* Default selected (no domain variant): solid primary-blue fill. */
        :host([selected]:not([variant])) {
            --_chip-bg: var(--color-primary);
            --_chip-fg: var(--white);
            --_chip-border: var(--color-primary);
            --_chip-bg-hover: var(--color-primary);
            /* This chip lightens on hover via a brightness() filter (below)
               rather than darkening its fill, so keep the border color put — the
               filter carries the whole pill, edge included. */
            --_chip-border-hover: var(--_chip-border);
            --_chip-count-fg: #c6e1f0;
            /* A white edge reads much louder on the dark fill than on a tint
               (same 18% as primary buttons). */
            --control-highlight-strength: 18%;
        }

        @media (hover: hover) and (pointer: fine) {
            :host([selected]:not([variant])) .chip:hover {
                filter: brightness(1.1);
            }
        }

        /* ── Domain variants: soft category-colored tint ──────────────────
           The tint is identical whether or not the chip is selected; selecting
           one only adds the close icon, so a selected variant chip reads as a
           removable, category-colored pill. */
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
            --_chip-count-fg: var(--color-text-muted);
        }

        /* Small size */
        :host([size="small"]) .chip {
            font-size: var(--font-size-label-medium);
        }

        /* Close icon for selected state. Negative margins absorb the glyph's
           dead space, so the leading inset and the gap to the label both
           measure from the painted x. */
        .icon-slot {
            display: inline-flex;
            flex: none;
            width: var(--chip-icon-size);
            height: var(--chip-icon-size);
            margin-inline:
                calc(-1 * var(--_chip-icon-slack))
                calc(var(--chip-icon-gap) - var(--_chip-icon-slack));
        }

        .icon {
            width: var(--chip-icon-size);
            height: var(--chip-icon-size);
            --ol-icon-stroke-width: 3;
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
                <ol-icon class="icon" name="x"></ol-icon>
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
