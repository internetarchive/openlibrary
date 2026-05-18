import { LitElement, html, css } from 'lit';
import { ifDefined } from 'lit/directives/if-defined.js';
import { repeat } from 'lit/directives/repeat.js';
import './OlPopover.js';

let _idCounter = 0;

/**
 * A single-select trigger button paired with a popover list of options.
 * Selecting any option fires `ol-facet-select-change` and closes the popover.
 *
 * Composes `<ol-popover>` for animation, focus trap, mobile tray, and
 * Escape/outside-click dismissal.
 *
 * Intentionally minimal — no multi-select, no filter input, no SELECTED/
 * SUGGESTIONS grouping. Designed as a sibling primitive to `ol-select-popover`.
 *
 * @element ol-facet-select
 *
 * @prop {Array}  options         - List of `{ value, label }` objects.
 * @prop {String} value           - Currently selected value.
 * @prop {String} accessibleLabel - Accessible label forwarded to the popover dialog.
 *
 * @fires ol-facet-select-change - Fired when the user picks an option.
 *     detail: { value: String, label: String }
 *
 * @example
 * <ol-facet-select
 *   accessible-label="Search by"
 *   .options=${[{value:'all',label:'All'},{value:'title',label:'Title'}]}
 *   value="all"
 * ></ol-facet-select>
 */
export class OlFacetSelect extends LitElement {
    static properties = {
        options: { type: Array },
        value: { type: String },
        accessibleLabel: { type: String, attribute: 'accessible-label' },
        _isOpen: { state: true },
    };

    static styles = css`
        :host {
            display: inline-flex;
            align-items: stretch;
            font-family: var(--font-family-body);
        }

        /* stretch ol-popover to fill the host */
        ol-popover {
            flex: 1;
            align-self: stretch;
        }

        /* ── Trigger button ─────────────────────────────────────── */

        .trigger {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
            padding: var(--ol-trigger-padding, 0 8px);
            height: 100%;
            min-height: var(--ol-trigger-min-height, 34px);
            flex: 1;
            background: var(--ol-trigger-bg, transparent);
            border: none;
            border-right: var(--ol-trigger-border-right, 1px solid var(--color-border-subtle, #ddd));
            border-radius: var(--ol-trigger-border-radius, 0);
            color: var(--darker-grey, #333);
            font: inherit;
            font-size: var(--ol-trigger-font-size, 14px);
            font-weight: 500;
            line-height: 1.4;
            cursor: pointer;
            white-space: nowrap;
            transition: background 100ms ease;
        }

        @media (hover: hover) and (pointer: fine) {
            .trigger:hover {
                background: var(--ol-trigger-bg-hover, var(--lightest-grey, #f5f5f5));
            }
        }

        .trigger:active {
            transform: scale(0.97);
        }

        .trigger:focus {
            outline: none;
        }

        .trigger:focus-visible {
            outline: 2px solid var(--color-focus-ring, #0070b8);
            outline-offset: -2px;
        }

        .trigger-chevron {
            display: inline-block;
            width: 14px;
            height: 14px;
            flex-shrink: 0;
            color: var(--accessible-grey, #666);
            transition: transform 150ms ease-out;
        }

        :host([data-open]) .trigger-chevron {
            transform: rotate(180deg);
        }

        @media (prefers-reduced-motion: reduce) {
            .trigger-chevron { transition: none; }
        }

        /* ── Panel ──────────────────────────────────────────────── */

        .panel {
            min-width: 130px;
        }

        ul {
            list-style: none;
            margin: 0;
            padding: 4px 0;
        }

        li button {
            display: block;
            width: 100%;
            padding: 8px 16px;
            background: transparent;
            border: none;
            color: var(--darker-grey, #333);
            font: inherit;
            font-size: 14px;
            text-align: left;
            cursor: pointer;
        }

        @media (hover: hover) and (pointer: fine) {
            li button:hover {
                background: var(--icon-link-grey, #f0f0f0);
            }
        }

        li button:focus {
            outline: none;
        }

        li button:focus-visible {
            outline: 2px solid var(--color-focus-ring, #0070b8);
            outline-offset: -2px;
        }

        li[aria-selected="true"] button {
            background: hsla(202, 96%, 37%, 0.08);
            color: var(--link-blue, #0070b8);
            font-weight: 600;
        }
    `;

    static _chevronIcon = html`
        <svg class="trigger-chevron" xmlns="http://www.w3.org/2000/svg"
             viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
             aria-hidden="true">
            <path d="m6 9 6 6 6-6"/>
        </svg>`;

    constructor() {
        super();
        this.options = [];
        this.value = '';
        this.accessibleLabel = '';
        this._isOpen = false;
        this._panelId = `ol-facet-select-${++_idCounter}`;
    }

    get _selectedLabel() {
        const match = (this.options || []).find(o => o.value === this.value);
        return match?.label ?? this.value;
    }

    render() {
        return html`
            <ol-popover
                placement="bottom-start"
                aria-label=${this.accessibleLabel || 'Select option'}
                @ol-popover-open=${this._onOpen}
                @ol-popover-close=${this._onClose}
            >
                <button
                    slot="trigger"
                    type="button"
                    class="trigger"
                    aria-haspopup="listbox"
                    aria-expanded=${this._isOpen}
                    aria-controls=${this._panelId}
                    aria-label=${ifDefined(this.accessibleLabel
        ? `${this.accessibleLabel}: ${this._selectedLabel}`
        : undefined)}
                >
                    ${this._selectedLabel}
                    ${OlFacetSelect._chevronIcon}
                </button>

                <div
                    class="panel"
                    role="listbox"
                    id=${this._panelId}
                    aria-label=${this.accessibleLabel || 'Select option'}
                    @keydown=${this._onKeydown}
                >
                    <ul>
                        ${repeat(this.options || [], o => o.value, o => html`
                            <li role="option" aria-selected=${o.value === this.value}>
                                <button
                                    type="button"
                                    data-value=${o.value}
                                    @click=${this._onSelect}
                                >${o.label}</button>
                            </li>
                        `)}
                    </ul>
                </div>
            </ol-popover>
        `;
    }

    // ── Event handlers ───────────────────────────────────────────

    _onOpen() {
        this._isOpen = true;
        this.setAttribute('data-open', '');
        // Focus current selection (desktop only; skip on mobile to avoid keyboard popup)
        if (!window.matchMedia('(max-width: 767px)').matches) {
            requestAnimationFrame(() => {
                const activeBtn = this.shadowRoot?.querySelector('li[aria-selected="true"] button');
                const firstBtn = this.shadowRoot?.querySelector('li button');
                (activeBtn || firstBtn)?.focus();
            });
        }
    }

    _onClose() {
        this._isOpen = false;
        this.removeAttribute('data-open');
    }

    _onSelect(e) {
        const value = e.currentTarget.dataset.value;
        const opt = (this.options || []).find(o => o.value === value);
        if (!opt) return;

        this.value = value;
        this.dispatchEvent(new CustomEvent('ol-facet-select-change', {
            bubbles: true, composed: true,
            detail: { value: opt.value, label: opt.label },
        }));

        // Close the popover
        const popover = this.shadowRoot?.querySelector('ol-popover');
        if (popover) popover.open = false;
    }

    _onKeydown(e) {
        const btns = Array.from(this.shadowRoot?.querySelectorAll('li button') || []);
        if (!btns.length) return;
        const active = this.shadowRoot?.activeElement;
        const idx = btns.indexOf(active);

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            btns[Math.min(idx + 1, btns.length - 1)]?.focus();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            btns[Math.max(idx - 1, 0)]?.focus();
        } else if (e.key === 'Home') {
            e.preventDefault();
            btns[0]?.focus();
        } else if (e.key === 'End') {
            e.preventDefault();
            btns[btns.length - 1]?.focus();
        }
    }
}

customElements.define('ol-facet-select', OlFacetSelect);
