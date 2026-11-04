import { LitElement, html, css, nothing } from 'lit';
import { getNextKeyboardFocusIndex } from './utils/keyboard-nav.js';
import { hasTabbableElement } from './utils/focus-utils.js';

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
 * `selected` attribute, else the panel marked `data-selected`, else the first.
 * Prefer `data-selected` in server-rendered markup: ol-tabs.css can see it, so
 * the right panel shows before upgrade too. A hash can also point inside a
 * panel as `#panel-id/anything`, which selects that panel and leaves the rest
 * to the page. Later hash changes (an in-page link to a panel, Back/Forward)
 * switch tabs the same way, and an emptied hash restores the default tab.
 *
 * The tab row scrolls sideways rather than wrapping when it overflows, with the
 * selected tab kept in view.
 *
 * @element ol-tabs
 *
 * @prop {String}  selected        - id of the selected panel. Reflected; set it to switch tabs.
 * @prop {Boolean} syncHash        - Write the selected panel's id to the URL hash when the user switches tabs (replaces the history entry, no scroll).
 * @prop {String}  accessibleLabel - aria-label for the tab list. Default: none.
 *
 * @fires ol-tabs-change - Fired when the user switches tabs, by click, keyboard or a hash change. detail: { selected: String }
 *
 * @slot tab - One `<a href="#panel-id">` per panel, in display order.
 * @slot - The panels: elements whose id matches a tab's href. Mark the initial one `data-selected`.
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

        /* Scrolls rather than wraps. The underline spans each label, so the
           row's rhythm is the gap. The track line is an inset shadow so each
           tab's own underline paints over it. */
        [part='tablist'] {
            display: flex;
            gap: var(--spacing-lg);
            overflow-x: auto;
            scrollbar-width: none;
            box-shadow: inset 0 calc(-1 * var(--border-width-divider)) 0 var(--color-border-muted);
        }

        [part='tablist']::-webkit-scrollbar {
            display: none;
        }
    `;

    constructor() {
        super();
        this.syncHash = false;
        this._onHashChange = this._onHashChange.bind(this);
        // Whether the selected panel needs its own tab stop can change after a
        // sync: content arrives later, or the tabs start out in a closed dialog
        // where nothing is visible yet. Recheck when the content or size changes.
        this._contentObserver = new MutationObserver(() => this._syncPanelTabStop());
        this._resizeObserver = typeof ResizeObserver === 'function' ? new ResizeObserver(() => this._syncPanelTabStop()) : null;
    }

    connectedCallback() {
        super.connectedCallback();
        // What Back returns to once the hash no longer names a panel.
        this._defaultSelected = this.selected || this.querySelector(':scope > [data-selected]:not([slot])')?.id;
        this.selected = this._panelIdFromHash() || this._defaultSelected;
        window.addEventListener('hashchange', this._onHashChange);
        this._contentObserver.observe(this, { childList: true, subtree: true });
        this._resizeObserver?.observe(this);
        // Flush the first render within the upgrade task, so the pre-upgrade
        // layout (ol-tabs.css, `:not(:defined)`) hands off with no frame between.
        this.performUpdate();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        window.removeEventListener('hashchange', this._onHashChange);
        this._contentObserver.disconnect();
        this._resizeObserver?.disconnect();
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
        return (tab?.getAttribute('href') || '').replace(/^#/, '');
    }

    /** The panel id named by the URL hash (`#id` or `#id/anything`), if it's one of ours. */
    _panelIdFromHash() {
        const id = window.location.hash.slice(1).split('/')[0];
        return id && this._panelFor(id) ? id : null;
    }

    get _selectedIndex() {
        const tabs = this._tabs;
        const i = this._panelFor(this.selected) ? tabs.findIndex(tab => this._panelIdOf(tab) === this.selected) : -1;
        return i === -1 && tabs.length ? 0 : i;
    }

    updated(changed) {
        this._sync();
        if (changed.has('selected')) this._revealSelectedTab();
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
        this._syncPanelTabStop();
    }

    // A selected panel with nothing focusable inside joins the tab sequence
    // itself, so keyboard users can still reach its content (APG). A frame
    // counts too: Tab enters it, though focus traps don't treat it as a stop.
    _syncPanelTabStop() {
        const panel = this._panelFor(this._panelIdOf(this._tabs[this._selectedIndex]));
        if (!panel) return;
        if (hasTabbableElement(panel) || panel.querySelector('iframe')) panel.removeAttribute('tabindex');
        else panel.tabIndex = 0;
    }

    // Scroll the tab row (never the page) so the selected tab is in view.
    _revealSelectedTab() {
        const tab = this._tabs[this._selectedIndex];
        const tablist = this.shadowRoot?.querySelector('[part="tablist"]');
        if (!tab || !tablist) return;
        const t = tab.getBoundingClientRect();
        const row = tablist.getBoundingClientRect();
        if (t.left < row.left) tablist.scrollLeft += t.left - row.left;
        else if (t.right > row.right) tablist.scrollLeft += t.right - row.right;
    }

    _select(index, { focus = false } = {}) {
        const tab = this._tabs[index];
        if (!tab) return;
        if (focus) tab.focus();
        if (index === this._selectedIndex) return;
        const id = this._panelIdOf(tab);
        this.selected = id;
        if (this.syncHash) history.replaceState(history.state, '', `#${id}`);
        this._emitChange(id);
    }

    _emitChange(id) {
        this.dispatchEvent(new CustomEvent('ol-tabs-change', { bubbles: true, composed: true, detail: { selected: id } }));
    }

    _onHashChange() {
        // A hash naming one of our panels selects it; an empty hash (Back past
        // the first tab switch) restores the default. Other hashes aren't ours.
        const hash = window.location.hash;
        const tabs = this._tabs;
        const id = hash && hash !== '#' ? this._panelIdFromHash() : this._defaultSelected || this._panelIdOf(tabs[0]);
        if (!id || id === this._panelIdOf(tabs[this._selectedIndex])) return;
        this.selected = id;
        this._emitChange(id);
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
        // The row mirrors under RTL, so the arrows follow what's on screen.
        const rtl = getComputedStyle(this).direction === 'rtl';
        const key = rtl ? { ArrowLeft: 'ArrowRight', ArrowRight: 'ArrowLeft' }[e.key] || e.key : e.key;
        const target = getNextKeyboardFocusIndex(key, {
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
