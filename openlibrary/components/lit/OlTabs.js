import { LitElement, html, css, nothing } from 'lit';
import { getNextKeyboardFocusIndex } from './utils/keyboard-nav.js';

/**
 * OlTabs - A row of underlined tabs that switch the content below them.
 *
 * Options are declared as light-DOM <ol-tab> children carrying a `value`
 * attribute; their text is the label. Children are read once on connect and
 * re-rendered as accessible tabs in the shadow root. The selected tab goes bold
 * over an underline sitting on the row's divider; the row scrolls sideways
 * rather than wrapping.
 *
 * Contains no application logic — the consuming page owns the panel and what a
 * selection *does*. Listen for the change event (or read `.value`).
 *
 * For a setting that toggles in place (a view, a unit), use ol-segmented-control.
 *
 * @element ol-tabs
 *
 * @prop {String}  value           - The selected tab's value. Reflected; defaults to the first tab.
 * @prop {String}  accessibleLabel - aria-label for the tab list. Default: none.
 *
 * @fires ol-tabs-change - Fired on user selection. detail: { value: String }
 *
 * @slot - One or more <ol-tab value="…">Label</ol-tab> elements.
 *
 * @example
 *   <ol-tabs value="all" accessible-label="Sci-Fi subgenres">
 *     <ol-tab value="all">All Sci-Fi</ol-tab>
 *     <ol-tab value="space-opera">Space Opera</ol-tab>
 *   </ol-tabs>
 */
export class OlTabs extends LitElement {
    static properties = {
        value: { type: String, reflect: true },
        accessibleLabel: { type: String, attribute: 'accessible-label' },
        _tabs: { state: true },
    };

    static styles = css`
        :host {
            display: block;
        }

        /* Scrolls rather than wraps; a scrollbar under a tab row reads as a second divider. */
        .tablist {
            display: flex;
            overflow-x: auto;
            scrollbar-width: none;
            /* The divider is a shadow, not a border: the scroll clip would cut off any part of
               a tab's underline that overlapped a border. */
            box-shadow: inset 0 -1px 0 var(--color-border-subtle);
        }

        .tablist::-webkit-scrollbar {
            display: none;
        }

        /* A large control's height with ol-button's padding, and no gap between tabs, so each
           underline runs past its label to meet the next tab's. */
        .tab {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            box-sizing: border-box;
            height: var(--control-height-large);
            padding: 0 var(--spacing-md);
            background: none;
            border: none;
            border-bottom: 2px solid transparent;
            color: var(--color-text-secondary);
            font: inherit;
            font-size: var(--font-size-body-medium);
            line-height: var(--line-height-control);
            white-space: nowrap;
            cursor: pointer;
        }

        /* Hidden bold twin reserves width so the selected tab goes bold without reflow. */
        .ghost {
            height: 0;
            overflow: hidden;
            visibility: hidden;
            font-weight: var(--font-weight-semibold);
        }

        /* A lighter bar than the selected tab's, so a hovered neighbour reads as a preview. */
        @media (hover: hover) and (pointer: fine) {
            .tab:not([aria-selected="true"]):hover {
                color: var(--color-text);
                border-bottom-color: var(--color-border-muted);
            }
        }

        /* Inset, so the scrolling row's overflow doesn't clip it. */
        .tab:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: -2px;
            border-radius: var(--border-radius-sm);
        }

        .tab[aria-selected="true"] {
            color: var(--color-text);
            border-bottom-color: var(--color-text);
            font-weight: var(--font-weight-semibold);
        }
    `;

    constructor() {
        super();
        this.value = null;
        this.accessibleLabel = null;
        this._tabs = [];
    }

    connectedCallback() {
        super.connectedCallback();
        this._harvestTabs();
    }

    // The light-DOM <ol-tab> children stay in the DOM (hidden via ol-components.css)
    // but are never slotted; the shadow root renders the interactive tabs.
    _harvestTabs() {
        this._tabs = Array.from(this.querySelectorAll('ol-tab')).map((el) => {
            const label = el.textContent.trim();
            return { value: el.getAttribute('value') ?? label, label };
        });
        if (!this._tabs.some((t) => t.value === this.value)) {
            this.value = this._tabs[0]?.value ?? null;
        }
    }

    _select(value, { focus = false } = {}) {
        if (value === this.value) return;
        this.value = value;
        this.dispatchEvent(new CustomEvent('ol-tabs-change', {
            bubbles: true,
            composed: true,
            detail: { value },
        }));
        if (focus) {
            this.updateComplete.then(() => {
                const tab = this.renderRoot.querySelector('.tab[aria-selected="true"]');
                tab?.focus();
                tab?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
            });
        }
    }

    // Arrows and Home/End move the selection, and focus follows it; arrows follow the reading
    // direction. Auto-repeat is dropped: each selection usually fetches, so a held arrow would fetch per tab.
    _onKeydown(e) {
        if (e.repeat) return;
        const flip = { ArrowLeft: 'ArrowRight', ArrowRight: 'ArrowLeft' };
        // Read, not `matches(':dir(rtl)')`: that selector throws on Safari < 16.4 and Chrome < 120.
        const rtl = getComputedStyle(this).direction === 'rtl';
        const key = rtl ? flip[e.key] ?? e.key : e.key;
        const target = getNextKeyboardFocusIndex(key, {
            count: this._tabs.length,
            current: this._tabs.findIndex((t) => t.value === this.value),
            orientation: 'horizontal',
            wrap: true,
        });
        if (target === -1) return;
        e.preventDefault();
        this._select(this._tabs[target].value, { focus: true });
    }

    render() {
        return html`
            <div class="tablist" role="tablist" aria-label=${this.accessibleLabel || nothing} @keydown=${this._onKeydown}>
                ${this._tabs.map((tab) => {
        const selected = tab.value === this.value;
        return html`
                        <button
                            class="tab"
                            type="button"
                            role="tab"
                            aria-selected=${selected ? 'true' : 'false'}
                            tabindex=${selected ? '0' : '-1'}
                            @click=${() => this._select(tab.value)}
                        >
                            <span>${tab.label}</span>
                            <span class="ghost" aria-hidden="true">${tab.label}</span>
                        </button>
                    `;
    })}
            </div>
        `;
    }
}

customElements.define('ol-tabs', OlTabs);
