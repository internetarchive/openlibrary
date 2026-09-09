import { LitElement, css, html, nothing } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { ifDefined } from 'lit/directives/if-defined.js';
import { translate } from './utils/labels.js';
import { SHELF, SHELF_LABEL, SHELF_ICON_FILLED, SHELF_EVENT, setShelf, redirectToLogin } from './utils/books-api.js';
import { showToast } from './OlToastRegion.js';
import { trackEvent } from '../../plugins/openlibrary/js/ol.analytics.js';
import { DEFAULT_LABELS as ACTION_LABELS } from './OlShelfActions.js';
import './OlShelfActions.js';
import './OlIcon.js';

export const DEFAULT_LABELS = {
    ...ACTION_LABELS,
    save: 'Save %(title)s to your reading log',
    saved: '%(title)s is on your reading log',
    // The main half's accessible name: the shelf it toggles plus the book, so
    // one of twenty in a list still says which. The shelf name leads because
    // it is the visible label.
    shelfToggle: '%(shelf)s: %(title)s',
    shelfMenu: 'More options for %(title)s',
    addToListFor: 'Add %(title)s to a list',
};

/**
 * The control that puts a book on a reading-log shelf, in the three shapes the
 * site needs: a bordered split button for a row (`split`), a round badge that
 * floats over cover art (`icon`), and that badge's glyph in a bordered square
 * (`outline`) for a row with room for a button but not a label. The badge and
 * the square show an outlined bookmark until the book is on a shelf, then that
 * shelf's own glyph, solid.
 *
 * All three open the same `<ol-shelf-actions>` popover; the split variant adds
 * a main half that toggles Want to Read on and off without opening anything.
 * With `lists-only` the same shapes serve a seed that has no work to shelve
 * (an author, an edition on its own): the split becomes one "Add to list"
 * trigger, the glyph a list-plus, and the popover opens on its lists pane.
 * Once the book is on one of the three reading shelves the main half opens the
 * popover instead: those shelves carry dates, ratings and goal progress, so
 * leaving one goes through the menu, which takes Already Read via its date
 * pane. Signed out, every shape sends the visitor to log in with the intent
 * remembered.
 *
 * **Stateless by design.** It never writes to `shelf` or `rating` itself — it
 * emits `ol-book-state-change` and the surface that owns the book applies it,
 * which then flows back down. That keeps one book's state correct when the same
 * book appears twice on a page, and it means an optimistic update and its
 * rollback are the same code path in both directions.
 *
 * @element ol-shelf-button
 *
 * @prop {String} variant - "split" (default), "icon" or "outline"
 * @prop {String} workKey - "/works/OL…W", the book this acts on. With
 *     `lists-only`, the seed instead: "/authors/OL…A" or "/books/OL…M"
 * @prop {Boolean} listsOnly - No shelf to act on; only the lists pane
 * @prop {String} editionKey - "OL…M", recorded with the shelf change when known
 * @prop {String} bookTitle - Used in the accessible labels. Named `book-title`
 *     because a `title` attribute would draw a native browser tooltip
 * @prop {Number} shelf - Current shelf id (1–4), or null when on none.
 *     Reflected, so the page's CSS can tell a saved book from an unsaved one
 *     (`ol-shelf-button[shelf]`) — a carousel keeps the saved mark visible
 *     and shows the rest on hover
 * @prop {Number} rating - Current rating (1–5), or null. Passed through to the
 *     popover and echoed on every state change
 * @prop {String} readDate - Check-in date, whole or partial, shown on the
 *     popover's Already Read row. Applied by the surface, like shelf and rating
 * @prop {Number} eventId - Id of that check-in, so editing the date amends it
 * @prop {String} userKey - "/people/<username>" when signed in; empty sends the
 *     visitor to log in instead of opening the popover
 * @prop {Boolean} pending - The reader's state is not known yet. The button
 *     looks unshelved and the popover holds its rows: posting a shelf the book
 *     is already on removes it, so a guess could undo a save
 * @prop {String} placement - ol-popover placement for the actions panel;
 *     unset uses its default
 * @prop {Boolean} hideRating - Always drop the popover's stars. Without it
 *     the popover drops them itself while a visible star form for the same
 *     book is on the page
 * @prop {Object} labels - Translated strings, merged over DEFAULT_LABELS
 *
 * @fires ol-book-state-change - The shelf or rating changed, optimistically or
 *     rolled back. detail: { key, shelf, rating }
 * @fires ol-book-check-in - Re-fired from the popover when a finish date is
 *     saved. detail: { key, date, eventId }
 *
 * @attr {Boolean} open - Present while the actions popover is open. Set by the
 *     component, never by the page: focus inside a top-layer popover does not
 *     register as `:focus-within` on the host, so a hover-revealed trigger
 *     needs this to stay visible under its own menu
 */
export class OlShelfButton extends LitElement {
    /** A shelf change is in flight. Deliberately not reactive: it gates the
        second click, it does not change how the button looks. */
    _pending = false;

    static properties = {
        variant: { type: String, reflect: true },
        workKey: { type: String, attribute: 'work-key' },
        editionKey: { type: String, attribute: 'edition-key' },
        bookTitle: { type: String, attribute: 'book-title' },
        shelf: { type: Number, reflect: true },
        rating: { type: Number },
        readDate: { type: String, attribute: 'read-date' },
        eventId: { type: Number, attribute: 'event-id' },
        userKey: { type: String, attribute: 'user-key' },
        placement: { type: String },
        labels: { type: Object },
        hideRating: { type: Boolean, attribute: 'hide-rating' },
        listsOnly: { type: Boolean, attribute: 'lists-only', reflect: true },
        pending: { type: Boolean, reflect: true },
        _announce: { state: true },
    };

    static styles = css`
        :host {
            display: block;
            font-family: var(--font-family-body);
        }

        ol-icon {
            width: 16px;
            height: 16px;
            flex: 0 0 16px;
        }

        /* ── Split variant ────────────────────────────────────────── */

        /* The two halves are one fused shape, so the container carries the
           secondary ol-button treatment: raised shadow, inset specular edge,
           and the press-scale (:active propagates up from either half). */
        .split {
            display: flex;
            border: 1px solid var(--color-border-subtle);
            border-radius: var(--border-radius-button);
            overflow: hidden;
            background: var(--white);
            --control-highlight-strength: 35%;
            box-shadow:
                var(--box-shadow-raised),
                inset 0 1px 0
                    color-mix(
                        in srgb,
                        var(--white) var(--control-highlight-strength),
                        var(--control-surface)
                    );
            transition: transform 0.08s;
        }

        .split:active {
            transform: scale(0.97);
        }

        .split--on {
            border-color: var(--color-control-selected-border);
            background: var(--color-control-selected-bg);
            /* Opaque twin of the tint, so the specular edge tones to it. */
            --control-surface: var(--color-control-selected-surface);
        }

        .main,
        .more {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
            height: calc(var(--control-height-medium) - 2px);
            border: 0;
            background: none;
            color: var(--color-text);
            font-family: var(--font-family-button);
            font-size: var(--font-size-body-medium);
            cursor: pointer;
        }

        .main {
            flex: 1;
            min-width: 0;
            padding: 0 var(--spacing-xs);
            white-space: nowrap;
            overflow: hidden;
        }

        .main span {
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .main--on {
            color: var(--color-link);
        }

        .split > ol-shelf-actions {
            display: flex;
        }

        /* Lists-only: the trigger is the whole button. */
        .split--list > ol-shelf-actions {
            flex: 1;
            min-width: 0;
        }

        .more {
            width: 32px;
            border-left: 1px solid var(--color-border-subtle);
        }

        .split--on .more {
            border-left-color: var(--color-control-selected-border);
            color: var(--color-link);
        }

        .main:hover,
        .more:hover {
            background: var(--color-hover-overlay);
        }

        /* When on, hover deepens the blue tint instead of graying it. */
        .split--on .main:hover,
        .split--on .more:hover {
            background: var(--color-control-selected-bg-hover);
        }

        .main:focus-visible,
        .more:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: -2px;
        }

        /* ── Icon variant ─────────────────────────────────────────── */

        /* An outlined bookmark until the book is on a shelf, then the shelf's
           glyph in blue. The host is positioned by whatever it floats over
           (ol-book-cover's overlay slot), so everything in here stays in flow. */
        .save {
            position: relative;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 32px;
            height: 32px;
            padding: 0;
            border: 0;
            background: transparent;
            color: var(--color-text);
            cursor: pointer;
            --control-highlight-strength: 35%;
            transition: transform 0.08s;
        }

        /* The visible circle is smaller than the 32px hit target. Same inset
           specular edge as ol-button; the drop shadow is heavier since it floats
           over cover art. */
        .save::before {
            content: "";
            position: absolute;
            inset: 4px;
            border-radius: var(--border-radius-circle);
            background: var(--white);
            box-shadow:
                0 1px 4px var(--boxshadow-black),
                inset 0 1px 0
                    color-mix(
                        in srgb,
                        var(--white) var(--control-highlight-strength),
                        var(--control-surface)
                    );
        }

        /* The circle stays white; only the glyph turns blue once shelved. */
        .glyph {
            position: relative;
            width: 14px;
            height: 14px;
            color: var(--primary-blue);
            --ol-icon-stroke-width: 2.5;
        }

        .glyph[name="bookmark"] {
            color: var(--color-text);
        }

        .save:hover {
            transform: scale(1.08);
        }

        .save:active {
            transform: scale(0.95);
        }

        .save:focus-visible {
            outline: none;
        }

        .save:focus-visible::before {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        /* ── Outline variant ──────────────────────────────────────── */

        /* The split button's bordered, raised shape at icon width. No circle or
           drop shadow, and the hover is a tint, not a grow. */
        :host([variant="outline"]) .save {
            box-sizing: border-box;
            width: var(--control-height-medium);
            height: var(--control-height-medium);
            border: 1px solid var(--color-border-subtle);
            border-radius: var(--border-radius-button);
            background: var(--white);
            box-shadow:
                var(--box-shadow-raised),
                inset 0 1px 0
                    color-mix(
                        in srgb,
                        var(--white) var(--control-highlight-strength),
                        var(--control-surface)
                    );
        }

        :host([variant="outline"]) .save::before {
            content: none;
        }

        :host([variant="outline"]) .glyph {
            width: 16px;
            height: 16px;
            --ol-icon-stroke-width: 2;
        }

        :host([variant="outline"]) .save--on {
            border-color: var(--color-control-selected-border);
            background: var(--color-control-selected-bg);
            --control-surface: var(--color-control-selected-surface);
        }

        :host([variant="outline"]) .save:hover {
            transform: none;
            background: var(--color-hover-overlay);
        }

        :host([variant="outline"]) .save--on:hover {
            background: var(--color-control-selected-bg-hover);
        }

        :host([variant="outline"]) .save:active {
            transform: scale(0.97);
        }

        :host([variant="outline"]) .save:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: -2px;
        }

        /* Live region: read out, never laid out. */
        .sr-only {
            position: absolute;
            width: 1px;
            height: 1px;
            padding: 0;
            margin: -1px;
            overflow: hidden;
            clip-path: inset(50%);
            white-space: nowrap;
        }
    `;

    constructor() {
        super();
        this.variant = 'split';
        this.workKey = '';
        this.editionKey = '';
        this.bookTitle = '';
        this.shelf = null;
        this.rating = null;
        this.userKey = '';
        this.labels = {};
        this.hideRating = false;
        this.listsOnly = false;
        this.pending = false;
        this._announce = '';
    }

    /** The badge's glyph: the shelf's own once shelved, a list-plus in lists-only mode. */
    get _icon() {
        return this.listsOnly ? 'list-plus' : this._on ? SHELF_ICON_FILLED[this.shelf] : 'bookmark';
    }

    t(key, vars) {
        return translate(this.labels, DEFAULT_LABELS, key, vars);
    }

    /** Read `message` out through the live region; cleared first so a repeat is still a change. */
    async _say(message) {
        this._announce = '';
        await this.updateComplete;
        this._announce = message;
    }

    get _on() {
        return this.shelf !== null && this.shelf !== undefined;
    }

    /** The badge and the square share one trigger: a glyph, no label. */
    get _glyphShaped() {
        return this.variant === 'icon' || this.variant === 'outline';
    }

    render() {
        return this._glyphShaped ? this._renderIcon() : this._renderSplit();
    }

    /**
     * Wrap a trigger in the actions popover when there is a reader to act for.
     * Signed out the trigger stands alone and its click goes to login.
     */
    _withActions(trigger) {
        if (!this.userKey) return trigger;
        return html`
            <ol-shelf-actions
                .book=${{ key: this.workKey, title: this.bookTitle, editionKey: this.editionKey }}
                .shelf=${this.shelf}
                .rating=${this.rating}
                .readDate=${this.readDate}
                .eventId=${this.eventId}
                .labels=${this.labels}
                user-key=${this.userKey}
                placement=${ifDefined(this.placement)}
                ?hide-rating=${this.hideRating}
                ?lists-only=${this.listsOnly}
                ?pending=${this.pending}
                @ol-popover-open=${this._onPopoverOpen}
                @ol-popover-close=${this._onPopoverClose}
            >${trigger}</ol-shelf-actions>
        `;
    }

    _renderIcon() {
        const on = this._on;
        const title = this.bookTitle;
        const label = this.listsOnly ? this.t('addToListFor', { title }) : on ? this.t('saved', { title }) : this.t('save', { title });
        return this._withActions(html`
            <button
                type="button"
                slot="trigger"
                class="save ${classMap({ 'save--on': on })}"
                aria-label=${label}
                @click=${this.userKey ? undefined : this._onLoggedOut}
            ><ol-icon class="glyph" name=${this._icon}></ol-icon></button>
        `);
    }

    _renderSplit() {
        // Lists-only: one labelled trigger in the split's frame, no main half.
        if (this.listsOnly) {
            const label = this.t('addToList');
            return html`
                <div class="split split--list">
                    ${this._withActions(html`
                        <button
                            type="button"
                            slot="trigger"
                            class="main"
                            aria-label=${this.t('shelfToggle', { shelf: label, title: this.bookTitle })}
                            @click=${this.userKey ? undefined : this._onLoggedOut}
                        ><ol-icon name="list-plus"></ol-icon><span>${label}</span></button>
                    `)}
                </div>
            `;
        }
        const on = this._on;
        const label = this.t(SHELF_LABEL[this.shelf ?? SHELF.WANT_TO_READ]);
        return html`
            <div class="split ${classMap({ 'split--on': on })}">
                <!-- A toggle: the label names the shelf, pressed means the book
                     is on it. The tint and check say the same thing on screen. -->
                <button
                    type="button"
                    class="main ${classMap({ 'main--on': on })}"
                    aria-pressed=${on ? 'true' : 'false'}
                    aria-label=${this.t('shelfToggle', { shelf: label, title: this.bookTitle })}
                    @click=${this._onMainClick}
                >${on ? html`<ol-icon name="check"></ol-icon>` : nothing}<span>${label}</span></button>
                <span class="sr-only" role="status">${this._announce}</span>
                ${this._withActions(html`
                    <button
                        type="button"
                        slot="trigger"
                        class="more"
                        aria-label=${this.t('shelfMenu', { title: this.bookTitle })}
                        @click=${this.userKey ? undefined : this._onLoggedOut}
                    ><ol-icon name="chevron-down"></ol-icon></button>
                `)}
            </div>
        `;
    }

    _emitState(shelf, rating = this.rating) {
        this.dispatchEvent(new CustomEvent('ol-book-state-change', {
            bubbles: true,
            composed: true,
            detail: { key: this.workKey, shelf, rating },
        }));
    }

    _openActions() {
        this.shadowRoot.querySelector('ol-shelf-actions')?.open();
    }

    _onPopoverOpen() {
        this.toggleAttribute('open', true);
    }

    /** A close the panel cancels (Escape stepping back a pane) is not a close. */
    _onPopoverClose(e) {
        if (!e.defaultPrevented) this.toggleAttribute('open', false);
    }

    _onLoggedOut(e) {
        e.preventDefault();
        // No resumeUrl: come back to the page they were on. On a book page that
        // is the same thing, but from a list of results it is not — the legacy
        // dropper returned them to their results too.
        redirectToLogin({ action: this.t(this.listsOnly ? 'addToList' : 'wantToRead'), title: this.bookTitle });
    }

    async _onMainClick(e) {
        if (!this.userKey) return this._onLoggedOut(e);
        // The shelf we emit only comes back down as a property a tick later, so
        // a second click before the request lands would toggle twice on the
        // server while the button shows one change. Unknown state is the same risk.
        if (this._pending || this.pending) return;
        const previous = this.shelf ?? null;
        if (previous !== null && previous !== SHELF.WANT_TO_READ) return this._openActions();
        // Want to Read is a bookmark: one tap on, one tap off.
        const target = SHELF.WANT_TO_READ;
        const next = previous === null ? SHELF.WANT_TO_READ : null;
        this._emitState(next);
        // The pressed state flips when the surface hands the shelf back down;
        // this says what happened in words, whether or not the reader's screen
        // reader announces state changes on a focused button.
        this._say(next === null ? this.t('removedFromShelf') : this.t('addedToShelf', { shelf: this.t(SHELF_LABEL[next]) }));
        this._pending = true;
        try {
            await setShelf(this.workKey, target, { editionKey: this.editionKey });
            trackEvent('ReadingLog', SHELF_EVENT[next]);
        } catch (error) {
            this._emitState(previous);
            if (error?.status === 401) return this._onLoggedOut(e);
            showToast(this.t('errorGeneric'), { type: 'error' });
        } finally {
            this._pending = false;
        }
    }
}

customElements.define('ol-shelf-button', OlShelfButton);
