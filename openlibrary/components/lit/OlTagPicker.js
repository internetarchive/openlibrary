import { LitElement, html, css, nothing } from 'lit';
import { ifDefined } from 'lit/directives/if-defined.js';
import { repeat } from 'lit/directives/repeat.js';
import './OlIcon.js';
import './OlPopover.js';
import './OLButton.js';
import './OLChip.js';
import './OLChipGroup.js';
import { FormAssociatedMixin } from './utils/form-associated-mixin.js';
import { getNextKeyboardFocusIndex } from './utils/keyboard-nav.js';

let _idCounter = 0;

// Per-type cache, shared across every picker on the page: each managed Tag type
// has at most a few dozen Tags, so we fetch the whole type once and filter in
// the browser. Keyed by tag_type; the value is the in-flight-or-settled promise,
// so concurrent pickers of the same type share one request.
const _tagCache = new Map();

/**
 * Fetch every Tag of one type, as `{ key, name }` rows, cached per type.
 *
 * `query.json`'s `name~=` prefix match is case-sensitive, so this fetches the
 * whole (small) type and the component filters client-side instead.
 *
 * @param {string} tagType - e.g. "content_formats", "genres".
 * @returns {Promise<Array<{key: string, name: string}>>} Empty on any failure.
 */
function fetchTagsOfType(tagType) {
    if (!_tagCache.has(tagType)) {
        const url = `/query.json?type=/type/tag&tag_type=${encodeURIComponent(tagType)}&name=&key=&limit=1000`;
        const promise = fetch(url)
            .then((r) => {
                if (!r.ok) throw new Error(`query.json returned ${r.status}`);
                return r.json();
            })
            .then((rows) => (Array.isArray(rows) ? rows : []).map((t) => ({ key: t.key, name: t.name })))
            .catch(() => {
                // Don't cache a failure: evict so a later open retries rather than
                // serving an empty list for the page's whole lifetime.
                _tagCache.delete(tagType);
                return [];
            });
        _tagCache.set(tagType, promise);
    }
    return _tagCache.get(tagType);
}

/** Normalise one stored selection to a Tag key string. */
function keyOf(entry) {
    if (typeof entry === 'string') return entry;
    return entry && typeof entry === 'object' ? entry.key : undefined;
}

/** "content_formats" -> "Content Formats"; used for the default trigger label. */
function humanizeType(tagType) {
    return (tagType || '')
        .split(/[_\s]+/)
        .filter(Boolean)
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(' ');
}

/**
 * A type-ahead picker for the managed Tags of a single Tag type. A trigger opens
 * a popover whose combobox input filters the type's Tags by name
 * (case-insensitively), and picking one adds it as a removable chip. The chips
 * sit outside the popover, so several can be added in a row. It only ever
 * *selects* existing Tags — it never creates them.
 *
 * Composes `<ol-popover>` for the overlay (animation, focus handling, mobile
 * tray, Escape / outside-click dismissal), `<ol-chip>` / `<ol-chip-group>` for
 * the selections, and the WAI-ARIA combobox + listbox pattern for the search.
 *
 * Form participation is via `ElementInternals` (FormAssociatedMixin): when
 * `name` is set, each selected Tag key submits with the enclosing `<form>` as a
 * repeated `name` entry, mirroring a native `<select multiple>`.
 *
 * @element ol-tag-picker
 *
 * @prop {String} tagType - The Tag type to pick from, e.g. "content_formats" or
 *     "genres". Scopes both the trigger label and the fetch. Attribute:
 *     `tag-type`. Works unchanged for any managed type.
 * @prop {Array} options - The pickable Tags, as `{ key, name }` objects. When
 *     supplied, no network fetch happens. When omitted and `tagType` is set,
 *     the component fetches every Tag of that type once and caches it. Settable
 *     as a JSON attribute or a property.
 * @prop {Array} value - The current selection. Accepts BOTH stored shapes on
 *     input — plain key strings (`"/tags/OL120T"`) and refs
 *     (`{"key":"/tags/OL120T"}`), mixed freely — and normalises to key strings.
 *     Settable as a JSON attribute or a property.
 * @prop {String} name - Form field name. When set, each selected key submits
 *     with the enclosing `<form>` as a repeated `name` entry (FormAssociatedMixin).
 * @prop {String} label - Trigger text. Defaults to `+ Add <Type>` derived from
 *     `tagType` (e.g. "+ Add Content Formats").
 * @prop {String} placeholder - Combobox input placeholder (default "Search…").
 * @prop {String} chipVariant - `ol-chip` colour variant for the selection chips
 *     (default "subject"). Attribute: `chip-variant`.
 * @prop {String} noMatchesLabel - Empty-state text when the filter matches
 *     nothing (default "No matches"). Attribute: `no-matches-label`.
 * @prop {String} loadingLabel - Text shown beside the spinner while fetching
 *     (default "Loading…"). Attribute: `loading-label`.
 *
 * @attr aria-label - Accessible name for the popover dialog and the combobox.
 *     Falls back to `label`.
 *
 * @fires ol-tag-picker-change - Fires when the selection changes.
 *     detail: { value: String[], added: String|null, removed: String|null }
 *
 * @slot trigger - Optional custom trigger element. When omitted, a default
 *     `<ol-button>` labelled by `label` is injected.
 *
 * @example
 * <ol-tag-picker
 *     tag-type="content_formats"
 *     name="content_formats"
 *     value='["/tags/OL136T"]'
 * ></ol-tag-picker>
 *
 * @example
 * <!-- Demo / no-network: supply options directly -->
 * <ol-tag-picker
 *     tag-type="content_formats"
 *     .options=${[{key: '/tags/OL136T', name: 'Novel'}]}
 *     @ol-tag-picker-change=${e => console.log(e.detail.value)}
 * ></ol-tag-picker>
 */
// NOT a FocusableHostMixin host: like OlSelectPopover, the focusable trigger is
// the light-DOM slotted element, not an element in this shadow root.
export class OlTagPicker extends FormAssociatedMixin(LitElement) {
    static properties = {
        tagType: { type: String, attribute: 'tag-type' },
        options: { type: Array },
        value: { type: Array },
        label: { type: String },
        placeholder: { type: String },
        chipVariant: { type: String, attribute: 'chip-variant' },
        noMatchesLabel: { type: String, attribute: 'no-matches-label' },
        loadingLabel: { type: String, attribute: 'loading-label' },
        loading: { type: Boolean, reflect: true },
        _query: { state: true },
        _activeIndex: { state: true },
        _resolvedOptions: { state: true },
    };

    static styles = css`
        :host {
            display: inline-block;
            font-family: var(--font-family-body);

            /* Declared here rather than on .panel: the panel is slotted into
               <ol-popover>, whose tray clears these, so an override only reaches
               it by inheriting past the tray. */
            --ol-popover-content-max-width: 320px;
            --ol-popover-content-max-height: min(60vh, 360px);
        }

        .chips {
            margin-bottom: var(--spacing-inset-sm);
        }

        /* ── Panel layout ────────────────────────────────────────── */

        .panel {
            display: flex;
            flex-direction: column;
            min-width: 240px;
            max-width: var(--ol-popover-content-max-width);
            max-height: var(--ol-popover-content-max-height);
        }

        /* ── Combobox input ──────────────────────────────────────── */

        .filter {
            position: relative;
            padding: var(--spacing-inset-sm);
            border-bottom: var(--border-divider);
        }

        .filter-input {
            box-sizing: border-box;
            width: 100%;
            padding: var(--spacing-inset-sm) var(--spacing-inset-sm) var(--spacing-inset-sm) 32px;
            background: var(--white);
            border: 1px solid var(--color-border-subtle);
            border-radius: var(--border-radius-input);
            font: inherit;
            font-size: var(--font-size-body-medium);
            color: inherit;
        }

        .filter-input::placeholder {
            color: var(--color-text-muted);
        }

        .filter-input:focus {
            outline: none;
            border-color: var(--color-border-focused);
            box-shadow: 0 0 0 1px var(--color-border-focused);
        }

        /* iOS zooms in on focus when the input font is < 16px; bump it up on
           mobile to suppress that. */
        @media (max-width: 767px) {
            .filter-input { font-size: var(--font-size-body-large); }
        }

        .filter-icon {
            position: absolute;
            top: 50%;
            left: calc(var(--spacing-inset-sm) + 10px);
            width: 14px;
            height: 14px;
            color: var(--color-text-muted);
            pointer-events: none;
            transform: translateY(-50%);
        }

        /* ── Listbox ─────────────────────────────────────────────── */

        .listbox {
            flex: 1;
            overflow-y: auto;
            min-height: 0;
            list-style: none;
            margin: 0;
            padding: var(--menu-row-inset) 0;
        }

        .option {
            display: flex;
            align-items: center;
            box-sizing: border-box;
            min-height: var(--menu-row-height);
            margin-inline: var(--menu-row-inset);
            padding-block: var(--spacing-inset-xs);
            padding-inline: var(--menu-row-padding-inline);
            border-radius: var(--border-radius-menu-row);
            font-size: var(--font-size-body-medium);
            line-height: var(--line-height-control);
            cursor: pointer;
            user-select: none;
        }

        .option-label {
            flex: 1;
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        @media (hover: hover) and (pointer: fine) {
            .option:hover {
                background: var(--color-hover-overlay);
            }
        }

        /* Active option (aria-activedescendant). Focus stays in the input, so
           this is the only cue to which option Enter will choose. */
        .option--active {
            background: var(--color-hover-overlay);
        }

        .empty-state {
            padding: var(--spacing-inset-md);
            text-align: center;
            color: var(--color-text-muted);
            font-size: var(--font-size-body-medium);
        }

        /* ── Loading state ───────────────────────────────────────── */

        @keyframes ol-tp-spin {
            to { transform: rotate(360deg); }
        }

        .loading-row {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: var(--spacing-inline-sm);
            padding: var(--spacing-inset-md);
            color: var(--color-text-muted);
            font-size: var(--font-size-body-medium);
        }

        .loading-spinner {
            width: 14px;
            height: 14px;
            border: 2px solid var(--color-border-subtle);
            border-top-color: var(--color-text-muted);
            border-radius: 50%;
            flex-shrink: 0;
            animation: ol-tp-spin var(--duration-spin) linear infinite;
        }

        @media (prefers-reduced-motion: reduce) {
            .loading-spinner { animation: none; opacity: 0.5; }
        }
    `;

    static _searchIcon = html`<ol-icon class="filter-icon" name="search"></ol-icon>`;

    constructor() {
        super();
        this.tagType = '';
        this.options = null;
        this.value = [];
        this.label = '';
        this.placeholder = 'Search…';
        this.chipVariant = 'subject';
        this.noMatchesLabel = 'No matches';
        this.loadingLabel = 'Loading…';
        this.loading = false;
        this._query = '';
        this._activeIndex = -1;
        this._resolvedOptions = null;
        this._listboxId = `ol-tag-picker-${++_idCounter}`;
        this._fetchedType = null;
    }

    connectedCallback() {
        super.connectedCallback();
        // role="group" permits aria-label on the host (axe: aria-prohibited-attr).
        if (!this.getAttribute('role')) this.setAttribute('role', 'group');
        if (!this._hasConsumerTrigger() && !this._defaultTrigger) this._createDefaultTrigger();
    }

    firstUpdated() {
        // Capture the authored default selection for <form>.reset() here rather
        // than in connectedCallback: the common init order sets `value` as a
        // property right AFTER insertion (synchronously, before this first
        // render), and connectedCallback would have captured the empty default.
        if (this._defaultValue === undefined) this._defaultValue = [...(this.value || [])];
        this._resolveOptions();
        this._syncFormValue();
    }

    willUpdate(changed) {
        super.willUpdate?.(changed);
        // A runtime switch to a *different* type must drop selections from the old
        // type — those keys may not belong to the new type. Done here (before
        // render) rather than in updated() so it lands in this same update cycle.
        // The initial set (old value falsy) must not clear an authored initial value.
        if (changed.has('tagType') && changed.get('tagType')) this.value = [];
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('options') || changed.has('tagType')) this._resolveOptions();
        if (changed.has('label') || changed.has('tagType')) this._updateDefaultTriggerLabel();
        if (changed.has('value') || changed.has('tagType')) this._syncFormValue();
    }

    // ── Selection model ──────────────────────────────────────────

    /** Current selection as a de-duplicated list of key strings (both shapes in). */
    get _selectedKeys() {
        const seen = new Set();
        const keys = [];
        for (const entry of this.value || []) {
            const key = keyOf(entry);
            if (key && !seen.has(key)) {
                seen.add(key);
                keys.push(key);
            }
        }
        return keys;
    }

    /** All resolved options as `{ key, name }`, from `options` or the fetch. */
    get _allOptions() {
        if (Array.isArray(this.options)) return this.options;
        return this._resolvedOptions || [];
    }

    /** Display name for a key, falling back to the key itself until loaded. */
    _nameOf(key) {
        return this._allOptions.find((o) => o.key === key)?.name ?? key;
    }

    /** Options not yet selected, filtered by the (case-insensitive) query. */
    get _filteredOptions() {
        const selected = new Set(this._selectedKeys);
        const query = this._query.trim().toLowerCase();
        return this._allOptions.filter(
            (o) => !selected.has(o.key) && (query === '' || (o.name || '').toLowerCase().includes(query)),
        );
    }

    // ── Data ─────────────────────────────────────────────────────

    /**
     * Resolve the option list: prefer a directly-supplied `options`; otherwise
     * fetch the whole type once (cached) when `tagType` is set.
     *
     * @returns {void}
     */
    _resolveOptions() {
        if (Array.isArray(this.options)) return; // direct options win; no fetch
        if (!this.tagType || this._fetchedType === this.tagType) return;
        const type = this.tagType;
        this._fetchedType = type;
        this.loading = true;
        fetchTagsOfType(type).then((rows) => {
            this._resolvedOptions = rows;
            this.loading = false;
            // fetchTagsOfType evicts the cache on failure; if it's gone, the fetch
            // failed, so clear our guard to let the next open retry.
            if (!_tagCache.has(type)) this._fetchedType = null;
        });
    }

    // ── Trigger ──────────────────────────────────────────────────

    _hasConsumerTrigger() {
        return Array.from(this.children).some(
            (el) => el !== this._defaultTrigger && el.getAttribute?.('slot') === 'trigger',
        );
    }

    /** Default trigger text: `label`, else "+ Add <Type>". */
    get _triggerLabel() {
        if (this.label) return this.label;
        const type = humanizeType(this.tagType);
        return type ? `+ Add ${type}` : '+ Add';
    }

    _createDefaultTrigger() {
        const btn = document.createElement('ol-button');
        btn.setAttribute('slot', 'trigger');
        btn.setAttribute('variant', 'secondary');
        // This is an "+ Add …" action trigger, not a value-selection dropdown:
        // the "+" is the affordance, so suppress ol-button's disclosure chevron
        // (which otherwise reads as a cramped "+ Add …⌄" beside the plus).
        btn.setAttribute('no-chevron', '');
        btn.textContent = this._triggerLabel;
        this._defaultTrigger = btn;
        this.appendChild(btn);
    }

    _updateDefaultTriggerLabel() {
        if (this._defaultTrigger) this._defaultTrigger.textContent = this._triggerLabel;
    }

    // ── Render ───────────────────────────────────────────────────

    render() {
        const ariaLabel = this.getAttribute('aria-label') || this.label || this._triggerLabel;
        return html`
            ${this._renderChips()}
            <ol-popover
                aria-label=${ifDefined(ariaLabel || undefined)}
                @ol-popover-open=${this._onPopoverOpen}
            >
                <slot name="trigger" slot="trigger"></slot>
                ${this._renderPanel(ariaLabel)}
            </ol-popover>
        `;
    }

    _renderChips() {
        const keys = this._selectedKeys;
        if (keys.length === 0) return nothing;
        return html`
            <ol-chip-group class="chips" gap="small" @ol-chip-select=${this._onChipSelect}>
                ${repeat(
        keys,
        (key) => key,
        (key) => html`
                        <ol-chip
                            variant=${this.chipVariant}
                            size="small"
                            selected
                            accessible-label="Remove ${this._nameOf(key)}"
                            data-key=${key}
                        >${this._nameOf(key)}</ol-chip>
                    `,
    )}
            </ol-chip-group>
        `;
    }

    _renderPanel(ariaLabel) {
        const options = this._filteredOptions;
        const query = this._query.trim();
        const activeId =
            this._activeIndex >= 0 && this._activeIndex < options.length
                ? `${this._listboxId}-opt-${this._activeIndex}`
                : undefined;
        // A listbox must own at least one option (axe: aria-required-children),
        // so when nothing matches we collapse the combobox and show the
        // empty-state as a live region instead of an empty listbox.
        const hasOptions = options.length > 0;
        return html`
            <div class="panel">
                <div class="filter">
                    ${OlTagPicker._searchIcon}
                    <input
                        type="text"
                        class="filter-input"
                        role="combobox"
                        aria-label=${ifDefined(ariaLabel || undefined)}
                        aria-expanded=${hasOptions ? 'true' : 'false'}
                        aria-autocomplete="list"
                        aria-controls=${ifDefined(hasOptions ? this._listboxId : undefined)}
                        aria-activedescendant=${ifDefined(activeId)}
                        autocomplete="off"
                        placeholder=${this.placeholder}
                        .value=${this._query}
                        @input=${this._onQueryInput}
                        @keydown=${this._onComboKeydown}
                    />
                </div>
                ${this.loading
        ? html`
                    <div class="loading-row" role="status" aria-live="polite">
                        <span class="loading-spinner" aria-hidden="true"></span>
                        <span>${this.loadingLabel}</span>
                    </div>`
        : hasOptions
            ? html`
                    <ul class="listbox" role="listbox" id=${this._listboxId} aria-label=${ifDefined(ariaLabel || undefined)}>
                        ${repeat(
        options,
        (o) => o.key,
        (o, i) => html`
                                    <li
                                        class="option ${i === this._activeIndex ? 'option--active' : ''}"
                                        role="option"
                                        id="${this._listboxId}-opt-${i}"
                                        aria-selected=${i === this._activeIndex}
                                        @mousedown=${this._onOptionMousedown}
                                        @mouseenter=${() => { this._activeIndex = i; }}
                                        @click=${() => this._selectKey(o.key)}
                                    >
                                        <span class="option-label">${o.name}</span>
                                    </li>
                                `,
    )}
                    </ul>`
            : query
                ? html`<div class="empty-state" role="status" aria-live="polite">${this.noMatchesLabel}</div>`
                : nothing}
            </div>
        `;
    }

    // ── Events ───────────────────────────────────────────────────

    _onPopoverOpen() {
        this._query = '';
        this._activeIndex = -1;
        this._resolveOptions();
        // Desktop: focus the combobox so the user can type immediately. Skipped
        // on mobile so the soft keyboard doesn't shrink the visible list.
        if (!window.matchMedia('(max-width: 767px)').matches) {
            this.updateComplete.then(() => {
                this.shadowRoot?.querySelector('.filter-input')?.focus();
            });
        }
    }

    _onQueryInput(e) {
        this._query = e.target.value;
        // Reset the active option to the first match so Enter picks something
        // sensible; -1 (nothing active) when there are no matches.
        this._activeIndex = this._filteredOptions.length > 0 ? 0 : -1;
    }

    _onComboKeydown(e) {
        if (e.key === 'Enter') {
            const options = this._filteredOptions;
            if (this._activeIndex >= 0 && this._activeIndex < options.length) {
                e.preventDefault();
                this._selectKey(options[this._activeIndex].key);
            }
            return;
        }
        if (e.key === 'Backspace' && this._query === '') {
            const keys = this._selectedKeys;
            if (keys.length > 0) {
                e.preventDefault();
                this._removeKey(keys[keys.length - 1]);
            }
            return;
        }
        // Only the vertical arrows move the active option. Home/End/PageUp/etc.
        // are deliberately left to the text input's native caret editing — the
        // WAI-ARIA list-autocomplete combobox pattern reserves them for the
        // textbox, so intercepting them would break "jump to start/end of query".
        // Escape is likewise left to ol-popover, which closes and restores focus
        // to the trigger (and manages nested-popover Escape ordering).
        if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
        const next = getNextKeyboardFocusIndex(e.key, {
            count: this._filteredOptions.length,
            current: this._activeIndex,
            orientation: 'vertical',
            wrap: true,
        });
        if (next !== -1) {
            e.preventDefault();
            this._activeIndex = next;
        }
    }

    // Keep focus in the input when an option is clicked, so the popover stays
    // open and typing can continue for the next pick.
    _onOptionMousedown(e) {
        e.preventDefault();
    }

    _onChipSelect(e) {
        // A selected chip's close icon fires ol-chip-select with selected:false.
        if (e.detail?.selected !== false) return;
        const key = e.target?.getAttribute?.('data-key');
        if (key) this._removeKey(key);
    }

    // ── Mutations ────────────────────────────────────────────────

    _selectKey(key) {
        if (!key || this._selectedKeys.includes(key)) return;
        const next = [...this._selectedKeys, key];
        this._commit(next, key, null);
        // Clear the query and keep focus in the input so another can be added.
        this._query = '';
        this._activeIndex = this._filteredOptions.length > 0 ? 0 : -1;
        this.updateComplete.then(() => {
            this.shadowRoot?.querySelector('.filter-input')?.focus();
        });
    }

    _removeKey(key) {
        if (!this._selectedKeys.includes(key)) return;
        const next = this._selectedKeys.filter((k) => k !== key);
        this._commit(next, null, key);
    }

    _commit(nextKeys, added, removed) {
        this.value = nextKeys;
        this._syncFormValue();
        this.dispatchEvent(
            new CustomEvent('ol-tag-picker-change', {
                bubbles: true,
                composed: true,
                detail: { value: nextKeys, added, removed },
            }),
        );
    }

    // ── Form association ─────────────────────────────────────────

    /**
     * @override
     * @returns {FormData|null} One `name` entry per selected key, mirroring a
     *   native `<select multiple>`; nothing when empty or unnamed.
     */
    get formAssociatedValue() {
        const keys = this._selectedKeys;
        if (keys.length === 0 || !this.name) return null;
        const data = new FormData();
        for (const key of keys) data.append(this.name, key);
        return data;
    }

    /**
     * @override
     * @returns {void}
     */
    formAssociatedReset() {
        this.value = [...(this._defaultValue || [])];
    }
}

if (!customElements.get('ol-tag-picker')) {
    customElements.define('ol-tag-picker', OlTagPicker);
}
