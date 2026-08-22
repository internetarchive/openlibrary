import { LitElement, css, html, nothing } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { translate } from './utils/labels.js';
import { SHELF, setShelf, redirectToLogin } from './utils/books-api.js';
import { showToast } from './OlToastRegion.js';
import { DEFAULT_LABELS as ACTION_LABELS } from './OlBookActions.js';
import './OlBookActions.js';
import './OlIcon.js';

export const DEFAULT_LABELS = {
    ...ACTION_LABELS,
    save: 'Save %(title)s to your reading log',
    saved: '%(title)s is on your reading log',
    shelfMenu: 'More options for %(title)s',
};

const SHELF_LABEL = {
    [SHELF.WANT_TO_READ]: 'wantToRead',
    [SHELF.CURRENTLY_READING]: 'currentlyReading',
    [SHELF.ALREADY_READ]: 'alreadyRead',
    [SHELF.STOPPED_READING]: 'stoppedReading',
};

/**
 * The control that puts a book on a reading-log shelf, in the two shapes the
 * site needs: a bordered split button for a row (`split`), and a round bookmark
 * that floats over cover art (`icon`).
 *
 * Both open the same `<ol-book-actions>` popover; the split variant adds a main
 * half that toggles between Want to Read and off without opening anything.
 * Signed out, either shape sends the visitor to log in with the intent
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
 * @prop {String} variant - "split" (default) or "icon"
 * @prop {String} workKey - "/works/OL…W", the book this acts on
 * @prop {String} editionKey - "OL…M", recorded with the shelf change when known
 * @prop {String} bookTitle - Used in the accessible labels. Named `book-title`
 *     because a `title` attribute would draw a native browser tooltip
 * @prop {Number} shelf - Current shelf id (1–4), or null when on none
 * @prop {Number} rating - Current rating (1–5), or null. Passed through to the
 *     popover and echoed on every state change
 * @prop {String} userKey - "/people/<username>" when signed in; empty sends the
 *     visitor to log in instead of opening the popover
 * @prop {String} placement - ol-popover placement for the actions panel
 * @prop {Object} labels - Translated strings, merged over DEFAULT_LABELS
 *
 * @fires ol-book-state-change - The shelf or rating changed, optimistically or
 *     rolled back. detail: { key, shelf, rating }
 */
export class OlShelfButton extends LitElement {
    static properties = {
        variant: { type: String, reflect: true },
        workKey: { type: String, attribute: 'work-key' },
        editionKey: { type: String, attribute: 'edition-key' },
        bookTitle: { type: String, attribute: 'book-title' },
        shelf: { type: Number },
        rating: { type: Number },
        userKey: { type: String, attribute: 'user-key' },
        placement: { type: String },
        labels: { type: Object },
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

        .split {
            display: flex;
            border: 1px solid var(--color-border-subtle);
            border-radius: var(--border-radius-button);
            overflow: hidden;
            background: var(--white);
        }

        .split--on {
            border-color: var(--color-control-selected-border);
            background: var(--color-control-selected-bg);
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
            font-weight: 600;
            cursor: pointer;
        }

        .main {
            flex: 1;
            min-width: 0;
            padding: 0 var(--spacing-sm);
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

        .split > ol-book-actions {
            display: flex;
        }

        .more {
            width: 40px;
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

        .main:focus-visible,
        .more:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: -2px;
        }

        /* ── Icon variant ─────────────────────────────────────────── */

        /* An outlined bookmark until the book is on a shelf, then filled. The
           host is positioned by whatever it floats over (ol-book-cover's overlay
           slot), so everything in here stays in flow. */
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

        .save ol-icon {
            position: relative;
            width: 14px;
            height: 14px;
            --ol-icon-stroke-width: 2.5;
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

        /* Saved: the circle stays white; only the bookmark fills, in blue. */
        .save--on {
            color: var(--primary-blue);
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
        this.placement = 'bottom-center';
        this.labels = {};
    }

    t(key, vars) {
        return translate(this.labels, DEFAULT_LABELS, key, vars);
    }

    get _on() {
        return this.shelf !== null && this.shelf !== undefined;
    }

    render() {
        return this.variant === 'icon' ? this._renderIcon() : this._renderSplit();
    }

    /**
     * Wrap a trigger in the actions popover when there is a reader to act for.
     * Signed out the trigger stands alone and its click goes to login.
     */
    _withActions(trigger) {
        if (!this.userKey) return trigger;
        return html`
            <ol-book-actions
                .book=${{ key: this.workKey, title: this.bookTitle, editionKey: this.editionKey }}
                .shelf=${this.shelf}
                .rating=${this.rating}
                .labels=${this.labels}
                user-key=${this.userKey}
                placement=${this.placement}
            >${trigger}</ol-book-actions>
        `;
    }

    _renderIcon() {
        const on = this._on;
        return this._withActions(html`
            <button
                type="button"
                slot="trigger"
                class="save ${classMap({ 'save--on': on })}"
                aria-label=${on ? this.t('saved', { title: this.bookTitle }) : this.t('save', { title: this.bookTitle })}
                @click=${this.userKey ? undefined : this._onLoggedOut}
            ><ol-icon name="bookmark" ?filled=${on}></ol-icon></button>
        `);
    }

    _renderSplit() {
        const on = this._on;
        const label = this.t(SHELF_LABEL[this.shelf ?? SHELF.WANT_TO_READ]);
        return html`
            <div class="split ${classMap({ 'split--on': on })}">
                <button
                    type="button"
                    class="main ${classMap({ 'main--on': on })}"
                    @click=${this._onMainClick}
                >${on ? html`<ol-icon name="check"></ol-icon>` : nothing}<span>${label}</span></button>
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

    _onLoggedOut(e) {
        e.preventDefault();
        redirectToLogin({ action: this.t('wantToRead'), title: this.bookTitle, resumeUrl: this.workKey });
    }

    async _onMainClick(e) {
        if (!this.userKey) return this._onLoggedOut(e);
        const previous = this.shelf ?? null;
        // On a shelf → clicking removes; otherwise → Want to Read.
        const target = previous ?? SHELF.WANT_TO_READ;
        const next = previous === null ? SHELF.WANT_TO_READ : null;
        const rating = this.rating;
        this._emitState(next, rating);
        try {
            await setShelf(this.workKey, target, { editionKey: this.editionKey });
        } catch (error) {
            this._emitState(previous, rating);
            if (error?.status === 401) return this._onLoggedOut(e);
            showToast(this.t('errorGeneric'), { type: 'error' });
        }
    }
}

customElements.define('ol-shelf-button', OlShelfButton);
