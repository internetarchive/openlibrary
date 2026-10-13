import { LitElement, html, css, nothing } from 'lit';
import { getNextKeyboardFocusIndex } from './utils/keyboard-nav.js';

/**
 * OlTabs - Switches between panels of server-rendered content.
 *
 * Tabs are `<a slot="tab" href="#panel-id">` links and panels are the other
 * direct children, matched to their tab by id. Both stay in the light DOM, so
 * the ARIA id references resolve, form fields inside a hidden panel still
 * submit with an enclosing `<form>`, and without JavaScript the tabs are plain
 * in-page links to sections that are all visible.
 *
 * On upgrade the component wires up the ARIA tabs pattern itself (tab/tabpanel
 * roles, aria-selected, aria-controls, aria-labelledby, roving tabindex) and
 * hides every panel but the selected one with the `hidden` attribute. The tabs
 * and panels are styled from static/css/components/ol-tabs.css, which also
 * covers the moment before upgrade.
 *
 * The initially selected tab is the one named by the URL hash, else the
 * `selected` attribute, else the first. A hash can also point inside a panel as
 * `#panel-id/anything`, which selects that panel and leaves the rest to the
 * page.
 *
 * @element ol-tabs
 *
 * @prop {String}  selected        - id of the selected panel. Reflected; set it to switch tabs.
 * @prop {Boolean} syncHash        - Write the selected panel's id to the URL hash when the user switches tabs (replaces the history entry, no scroll).
 * @prop {String}  accessibleLabel - aria-label for the tab list. Default: none.
 *
 * @fires ol-tabs-change - Fired when the user switches tabs. detail: { selected: String }
 *
 * @slot tab - One `<a href="#panel-id">` per panel, in display order.
 * @slot - The panels: elements whose id matches a tab's href.
 *
 * @csspart tablist - The row of tabs.
 *
 * @example
 *   <ol-tabs sync-hash>
 *     <a slot="tab" href="#humans">By Humans</a>
 *     <a slot="tab" href="#bots">By Bots</a>
 *     <div id="humans">…</div>
 *     <div id="bots">…</div>
 *   </ol-tabs>
 */
export class OlTabs extends LitElement {
    static properties = {
        selected: { type: String, reflect: true },
        syncHash: { type: Boolean, attribute: 'sync-hash' },
        accessibleLabel: { type: String, attribute: 'accessible-label' }
    };

    // Only the row layout lives here. The tabs and panels are light DOM, and
    // page link styles beat ::slotted(), so they're styled from ol-tabs.css.
    static styles = css`
        :host {
            display: block;
        }

        [part='tablist'] {
            display: flex;
            flex-wrap: wrap;
            gap: var(--spacing-3xs);
        }
    `;

    constructor() {
        super();
        this.syncHash = false;
    }

    connectedCallback() {
        super.connectedCallback();
        const fromHash = window.location.hash.slice(1).split('/')[0];
        if (fromHash && this._panelFor(fromHash)) this.selected = fromHash;
        // Flush the first render within the upgrade task, so the pre-upgrade
        // layout (ol-tabs.css, `:not(:defined)`) hands off with no frame between.
        this.performUpdate();
    }

    /** @returns {HTMLAnchorElement[]} */
    get _tabs() {
        return Array.from(this.children).filter(el => el.slot === 'tab');
    }

    /** The direct-child panel with this id, so nested ol-tabs stay separate. */
    _panelFor(id) {
        return Array.from(this.children).find(el => !el.slot && el.id === id) || null;
    }

    _panelIdOf(tab) {
        return (tab.getAttribute('href') || '').replace(/^#/, '');
    }

    get _selectedIndex() {
        const tabs = this._tabs;
        const i = this._panelFor(this.selected) ? tabs.findIndex(tab => this._panelIdOf(tab) === this.selected) : -1;
        return i === -1 && tabs.length ? 0 : i;
    }

    updated() {
        this._sync();
    }

    // Apply roles, ids, selection and visibility to the light-DOM tabs and panels.
    _sync() {
        const tabs = this._tabs;
        const selectedIndex = this._selectedIndex;
        tabs.forEach((tab, i) => {
            const panel = this._panelFor(this._panelIdOf(tab));
            const isSelected = i === selectedIndex;
            tab.setAttribute('role', 'tab');
            tab.setAttribute('aria-selected', String(isSelected));
            tab.tabIndex = isSelected ? 0 : -1;
            if (!panel) return;
            tab.id ||= `${panel.id}-tab`;
            tab.setAttribute('aria-controls', panel.id);
            panel.setAttribute('role', 'tabpanel');
            panel.setAttribute('aria-labelledby', tab.id);
            panel.hidden = !isSelected;
        });
    }

    _select(index, { focus = false } = {}) {
        const tab = this._tabs[index];
        if (!tab) return;
        if (focus) tab.focus();
        if (index === this._selectedIndex) return;
        const id = this._panelIdOf(tab);
        this.selected = id;
        if (this.syncHash) history.replaceState(history.state, '', `#${id}`);
        this.dispatchEvent(new CustomEvent('ol-tabs-change', { bubbles: true, composed: true, detail: { selected: id } }));
    }

    _onClick(e) {
        // Let modified clicks (open in new tab, etc.) behave like the link they are.
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        const index = this._tabs.indexOf(e.target.closest('[slot="tab"]'));
        if (index === -1) return;
        e.preventDefault();
        this._select(index);
    }

    _onKeydown(e) {
        // Leave browser shortcuts alone (Alt+Arrow is Back/Forward).
        if (e.altKey || e.ctrlKey || e.metaKey) return;
        const target = getNextKeyboardFocusIndex(e.key, {
            count: this._tabs.length,
            current: this._selectedIndex,
            orientation: 'horizontal',
            wrap: true
        });
        if (target === -1) return;
        e.preventDefault();
        this._select(target, { focus: true });
    }

    render() {
        return html`
            <div part="tablist" role="tablist" aria-label=${this.accessibleLabel || nothing} @click=${this._onClick} @keydown=${this._onKeydown}>
                <slot name="tab" @slotchange=${this._sync}></slot>
            </div>
            <slot @slotchange=${this._sync}></slot>
        `;
    }
}

customElements.define('ol-tabs', OlTabs);
