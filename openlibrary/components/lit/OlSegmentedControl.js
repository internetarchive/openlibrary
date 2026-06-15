import { LitElement, html, css, nothing } from 'lit';

/**
 * OlSegmentedControl - A single-select control styled like ol-button.
 *
 * Renders a row of mutually-exclusive options (a radio group): exactly one is
 * selected at a time. It shares ol-button's height tokens and visual language,
 * so a same-size segmented control and button line up at the same height.
 *
 * Options are declared as light-DOM <ol-segment> children carrying a `value`
 * attribute; their text content is the label. They are read once on connect
 * and re-rendered as accessible radios in the shadow root, so the control needs
 * no per-option wiring from the consuming page.
 *
 * Contains no application logic — the consuming page owns what a selection
 * *does*. Listen for the change event (or read `.value`).
 *
 * @element ol-segmented-control
 *
 * @prop {String}  value           - The selected option's value. Reflected; defaults to the first enabled option.
 * @prop {String}  size            - "small" | "medium" | "large". Default: "medium"
 * @prop {Boolean} disabled        - Disables the whole control.
 * @prop {Boolean} fullWidth       - Stretch to fill the container; options share the width equally.
 * @prop {String}  accessibleLabel - aria-label for the radio group. Default: none.
 *
 * @fires ol-segmented-control-change - Fired on user selection. detail: { value: String }
 *
 * @slot - One or more <ol-segment value="…">Label</ol-segment> option elements.
 *
 * @example
 *   <ol-segmented-control value="list" accessible-label="View">
 *     <ol-segment value="grid">Grid</ol-segment>
 *     <ol-segment value="list">List</ol-segment>
 *   </ol-segmented-control>
 */
export class OlSegmentedControl extends LitElement {
    static properties = {
        value: { type: String, reflect: true },
        size: { type: String, reflect: true },
        disabled: { type: Boolean, reflect: true },
        fullWidth: { type: Boolean, reflect: true, attribute: 'full-width' },
        accessibleLabel: { type: String, attribute: 'accessible-label' },
        _options: { state: true },
    };

    static styles = css`
        :host {
            display: inline-flex;
            vertical-align: middle;
        }

        :host([full-width]) {
            display: flex;
            width: 100%;
        }

        :host([disabled]) {
            opacity: 0.55;
            cursor: not-allowed;
        }

        .track {
            display: inline-flex;
            box-sizing: border-box;
            height: var(--control-height-medium);
            padding: 0;
            border: 1.5px solid var(--color-border-subtle);
            border-radius: var(--border-radius-button);
            background-color: var(--white);
            overflow: hidden;
        }

        :host([full-width]) .track {
            display: flex;
            width: 100%;
        }

        .segment {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            box-sizing: border-box;
            height: 100%;
            padding: 0 var(--spacing-inset-md);
            border: 0;
            background-color: transparent;
            color: var(--dark-grey);
            font-family: var(--font-family-button);
            font-size: var(--font-size-body-medium);
            font-weight: 500;
            line-height: var(--line-height-control);
            white-space: nowrap;
            cursor: pointer;
            user-select: none;
            transition:
                background-color 0.15s,
                color 0.15s;
        }

        :host([full-width]) .segment {
            flex: 1 1 0;
        }

        /* 1px divider between segments, drawn on the left edge of every segment
           after the first. Hidden around the selected segment so the filled
           segment reads as a single solid block. */
        .segment:not(:first-child) {
            border-inline-start: 1px solid var(--color-border-subtle);
        }

        .segment[aria-checked="true"],
        .segment[aria-checked="true"] + .segment {
            border-inline-start-color: transparent;
        }

        @media (hover: hover) and (pointer: fine) {
            .segment:not([aria-checked="true"]):not(:disabled):hover {
                background-color: var(--lightest-grey);
            }
        }

        .segment:active:not(:disabled) {
            transform: scale(0.97);
        }

        .segment[aria-checked="true"] {
            background-color: var(--primary-blue);
            color: var(--white);
        }

        .segment:disabled {
            opacity: 0.45;
            cursor: not-allowed;
        }

        /* Focus ring sits inside the track so it isn't clipped by overflow. */
        .segment:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: -3px;
        }

        /* Sizes — mirror ol-button so same-size controls line up. */
        :host([size="small"]) .track {
            height: var(--control-height-small);
        }

        :host([size="small"]) .segment {
            padding: 0 var(--spacing-md);
            font-size: var(--font-size-label-medium);
        }

        :host([size="large"]) .track {
            height: var(--control-height-large);
        }

        :host([size="large"]) .segment {
            padding: 0 var(--spacing-inset-lg);
            font-size: var(--font-size-body-large);
        }

        @media (prefers-reduced-motion: reduce) {
            .segment {
                transition: none;
            }

            .segment:active:not(:disabled) {
                transform: none;
            }
        }
    `;

    constructor() {
        super();
        this.value = null;
        this.size = 'medium';
        this.disabled = false;
        this.fullWidth = false;
        this.accessibleLabel = null;
        this._options = [];
    }

    connectedCallback() {
        super.connectedCallback();
        this._harvestOptions();
    }

    // Read the declarative <ol-segment> children into a plain options array.
    // The light-DOM children stay in the DOM (hidden via ol-components.css) but
    // are never slotted — the shadow root renders the interactive radios.
    _harvestOptions() {
        this._options = Array.from(this.querySelectorAll('ol-segment')).map((el) => ({
            value: el.getAttribute('value') ?? el.textContent.trim(),
            label: el.textContent.trim(),
            disabled: el.hasAttribute('disabled'),
        }));

        // A segmented control always has a selection. If value is unset or
        // doesn't match an option, fall back to the first enabled option.
        const hasValid = this._options.some((o) => o.value === this.value && !o.disabled);
        if (!hasValid) {
            const firstEnabled = this._options.find((o) => !o.disabled);
            this.value = firstEnabled ? firstEnabled.value : null;
        }
    }

    // Index of the option that owns the roving tabindex / arrow-key focus.
    get _activeIndex() {
        const i = this._options.findIndex((o) => o.value === this.value);
        if (i !== -1) return i;
        return this._options.findIndex((o) => !o.disabled);
    }

    _select(value, { focus = false } = {}) {
        if (value === this.value) return;
        this.value = value;
        this.dispatchEvent(new CustomEvent('ol-segmented-control-change', {
            bubbles: true,
            composed: true,
            detail: { value },
        }));
        if (focus) {
            this.updateComplete.then(() => {
                const btn = this.renderRoot.querySelector('.segment[aria-checked="true"]');
                if (btn) btn.focus();
            });
        }
    }

    // Standard radio-group keyboard model: arrows move selection (and focus)
    // to the previous/next enabled option, wrapping; Home/End jump to the ends.
    _onKeydown(e) {
        const keys = ['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp', 'Home', 'End'];
        if (!keys.includes(e.key)) return;
        e.preventDefault();

        const enabled = this._options.filter((o) => !o.disabled);
        if (enabled.length === 0) return;

        let target;
        if (e.key === 'Home') {
            target = enabled[0];
        } else if (e.key === 'End') {
            target = enabled[enabled.length - 1];
        } else {
            const step = (e.key === 'ArrowRight' || e.key === 'ArrowDown') ? 1 : -1;
            const current = enabled.findIndex((o) => o.value === this.value);
            const base = current === -1 ? 0 : current;
            target = enabled[(base + step + enabled.length) % enabled.length];
        }
        this._select(target.value, { focus: true });
    }

    render() {
        const activeIndex = this._activeIndex;
        return html`
            <div
                class="track"
                role="radiogroup"
                aria-label=${this.accessibleLabel || nothing}
                @keydown=${this._onKeydown}
            >
                ${this._options.map((option, i) => {
                    const checked = option.value === this.value;
                    return html`
                        <button
                            class="segment"
                            type="button"
                            role="radio"
                            aria-checked=${checked ? 'true' : 'false'}
                            tabindex=${i === activeIndex ? '0' : '-1'}
                            ?disabled=${this.disabled || option.disabled}
                            @click=${() => this._select(option.value)}
                        >${option.label}</button>
                    `;
                })}
            </div>
        `;
    }
}

customElements.define('ol-segmented-control', OlSegmentedControl);
