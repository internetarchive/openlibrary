import { LitElement, html, css, nothing } from 'lit';
import './OlAutocomplete.js';
import './OlPopover.js';

/**
 * Inline edit popover for languages on the edition view page.
 *
 * @element ol-language-edit
 *
 * @prop {String} editionKey - Edition key (e.g. `/books/OL1234M`)
 * @prop {String} languages - JSON string of languages: `[{"key":"/languages/eng","name":"English"}]`
 *
 * @fires ol-language-edit-save - Fired after a successful save. detail: { languages, comment }
 */
export class OlLanguageEdit extends LitElement {
    static properties = {
        editionKey: { type: String, attribute: 'edition-key' },
        languages: { type: String },
        _isOpen: { type: Boolean, state: true },
        _editLanguages: { type: Array, state: true },
        _comment: { type: String, state: true },
        _isSaving: { type: Boolean, state: true },
        _error: { type: String, state: true },
    };

    static styles = css`
        :host {
            display: inline-flex;
            align-items: center;
            text-align: left;
        }

        .display-text {
            cursor: default;
        }

        .trigger {
            background: none;
            border: none;
            cursor: pointer;
            padding: 2px 4px;
            margin-left: 4px;
            opacity: 0;
            transition: opacity 0.15s;
            color: var(--grey, hsl(0, 0%, 40%));
            font-size: 14px;
            line-height: 1;
            border-radius: var(--border-radius-sm, 2px);
        }

        .trigger:hover {
            color: var(--primary-blue, hsl(202, 96%, 37%));
        }

        .trigger:active {
            transform: scale(0.97);
        }

        @media (hover: hover) and (pointer: fine) {
            :host(:hover) .trigger,
            .trigger:focus-visible {
                opacity: 1;
            }
        }

        @media not all and (hover: hover) {
            .trigger {
                opacity: 1;
            }
        }

        .popover-body {
            padding: 16px;
            min-width: 300px;
            max-width: 400px;
        }

        .language-row {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 8px;
        }

        .language-row ol-autocomplete {
            flex: 1;
        }

        .remove-btn {
            background: none;
            border: none;
            cursor: pointer;
            padding: 4px 6px;
            font-size: 18px;
            line-height: 1;
            color: var(--grey, hsl(0, 0%, 40%));
            border-radius: var(--border-radius-sm, 2px);
        }

        .remove-btn:hover {
            color: var(--red, hsl(8, 78%, 49%));
        }

        .remove-btn:active {
            transform: scale(0.97);
        }

        .remove-btn:disabled {
            opacity: 0.3;
            cursor: default;
        }

        .add-btn {
            background: none;
            border: none;
            cursor: pointer;
            color: var(--primary-blue, hsl(202, 96%, 37%));
            font: inherit;
            font-size: 13px;
            padding: 4px 0;
            margin-bottom: 12px;
        }

        .add-btn:hover {
            text-decoration: underline;
        }

        .add-btn:active {
            transform: scale(0.97);
        }

        .comment-input {
            width: 100%;
            box-sizing: border-box;
            padding: 6px 8px;
            border: var(--border-input, 1px solid hsl(0, 0%, 87%));
            border-radius: var(--border-radius-input, 4px);
            font: inherit;
            font-size: 13px;
            margin-bottom: 12px;
            outline: none;
        }

        .comment-input:focus {
            border-color: var(--color-border-focused, hsl(202, 96%, 37%));
            box-shadow: var(--box-shadow-focus, 0 0 0 2px hsl(202, 96%, 37%));
        }

        .action-bar {
            display: flex;
            justify-content: flex-end;
            gap: 8px;
        }

        .cancel-btn,
        .save-btn {
            padding: 6px 14px;
            border-radius: var(--border-radius-button, 4px);
            font: inherit;
            font-size: 13px;
            cursor: pointer;
            border: 1px solid transparent;
        }

        .cancel-btn {
            background: var(--white, #fff);
            border-color: var(--color-border-subtle, hsl(0, 0%, 87%));
            color: inherit;
        }

        .cancel-btn:hover {
            background: var(--lightest-grey, hsl(0, 0%, 93%));
        }

        .cancel-btn:active {
            transform: scale(0.97);
        }

        .save-btn {
            background: var(--primary-blue, hsl(202, 96%, 37%));
            color: var(--white, #fff);
        }

        .save-btn:hover {
            opacity: 0.9;
        }

        .save-btn:active {
            transform: scale(0.97);
        }

        .save-btn:disabled {
            opacity: 0.5;
            cursor: default;
        }

        .error {
            color: var(--red, hsl(8, 78%, 49%));
            font-size: 12px;
            margin-bottom: 8px;
        }

        .pencil-icon {
            width: 14px;
            height: 14px;
            vertical-align: middle;
        }
    `;

    constructor() {
        super();
        this.editionKey = '';
        this.languages = '[]';
        this._isOpen = false;
        this._editLanguages = [];
        this._comment = '';
        this._isSaving = false;
        this._error = '';
    }

    get _parsedLanguages() {
        if (this._parsedLangsCache?.src === this.languages) {
            return this._parsedLangsCache.val;
        }
        let val;
        try {
            val = JSON.parse(this.languages);
        } catch {
            val = [];
        }
        this._parsedLangsCache = { src: this.languages, val };
        return val;
    }

    get _displayText() {
        return this._parsedLanguages.map(l => l.name).join(', ') || '';
    }

    get _canSave() {
        return !this._isSaving && this._editLanguages.length > 0 &&
            this._editLanguages.every(l => l.key);
    }

    render() {
        return html`
            <span class="display-text" itemprop="inLanguage">${this._displayText}</span>
            <ol-popover
                ?open="${this._isOpen}"
                label="Edit languages"
                @ol-popover-close="${this._close}"
                @ol-popover-open="${this._onPopoverOpen}"
            >
                <button
                    slot="trigger"
                    class="trigger"
                    aria-label="Edit languages"
                    @click="${this._open}"
                >
                    <svg class="pencil-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
                        <path d="m15 5 4 4"/>
                    </svg>
                </button>
                <div class="popover-body">
                    <div class="language-list">
                        ${this._editLanguages.map((lang, i) => html`
                            <div class="language-row">
                                <ol-autocomplete
                                    source-url="/languages/_autocomplete"
                                .clearable="${false}"
                                    .value="${lang.name || ''}"
                                    .selectedKey="${lang.key || ''}"
                                    placeholder="Search for a language"
                                    @ol-autocomplete-select="${(e) => this._onLangSelect(i, e)}"
                                    @ol-autocomplete-clear="${() => this._onLangClear(i)}"
                                ></ol-autocomplete>
                                <button
                                    class="remove-btn"
                                    aria-label="Remove language"
                                    ?disabled="${this._editLanguages.length <= 1}"
                                    @click="${() => this._removeLang(i)}"
                                >&times;</button>
                            </div>
                        `)}
                    </div>
                    <button class="add-btn" @click="${this._addLang}">+ Add another language</button>
                    <input
                        class="comment-input"
                        type="text"
                        placeholder="Describe your edit"
                        .value="${this._comment}"
                        @input="${(e) => this._comment = e.target.value}"
                    />
                    ${this._error ? html`<div class="error">${this._error}</div>` : nothing}
                    <div class="action-bar">
                        <button class="cancel-btn" @click="${this._close}">Cancel</button>
                        <button
                            class="save-btn"
                            ?disabled="${!this._canSave}"
                            @click="${this._save}"
                        >${this._isSaving ? 'Saving…' : 'Save'}</button>
                    </div>
                </div>
            </ol-popover>
        `;
    }

    _open() {
        this._editLanguages = this._parsedLanguages.map(l => ({ ...l }));
        if (this._editLanguages.length === 0) {
            this._editLanguages = [{ key: '', name: '' }];
        }
        this._comment = '';
        this._error = '';
        this._isOpen = true;
    }

    _onPopoverOpen() {
        // Focus first autocomplete after popover animation starts
        this.updateComplete.then(() => {
            const popover = this.shadowRoot.querySelector('ol-popover');
            const autocomplete = popover?.querySelector('ol-autocomplete');
            autocomplete?.focusInput();
        });
    }

    _close() {
        this._isOpen = false;
        this._error = '';
        // Return focus to trigger
        this.updateComplete.then(() => {
            const trigger = this.shadowRoot.querySelector('.trigger');
            trigger?.focus();
        });
    }

    _updateLang(index, updates) {
        this._editLanguages = this._editLanguages.map((l, i) =>
            i === index ? { ...l, ...updates } : l
        );
    }

    _onLangSelect(index, e) {
        const { key, name } = e.detail;
        this._updateLang(index, { key, name });
    }

    _onLangClear(index) {
        this._updateLang(index, { key: '', name: '' });
    }

    _addLang() {
        this._editLanguages = [...this._editLanguages, { key: '', name: '' }];
        this.updateComplete.then(() => {
            const autocompletes = this.shadowRoot.querySelectorAll('ol-autocomplete');
            const last = autocompletes[autocompletes.length - 1];
            last?.focusInput();
        });
    }

    _removeLang(index) {
        if (this._editLanguages.length <= 1) return;
        this._editLanguages = this._editLanguages.filter((_, i) => i !== index);
    }

    async _save() {
        if (!this._canSave) return;
        this._isSaving = true;
        this._error = '';

        try {
            // Fetch current edition data
            const getResp = await fetch(`${this.editionKey}.json`);
            if (!getResp.ok) throw new Error('Failed to load edition data');
            const edition = await getResp.json();

            // Update languages
            edition.languages = this._editLanguages.map(l => ({ key: l.key }));

            // Save
            const putResp = await fetch(`${this.editionKey}.json`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    Opt: '"http://openlibrary.org/dev/docs/api"; ns=42',
                    '42-comment': this._comment || 'Update languages',
                },
                body: JSON.stringify(edition),
            });

            if (!putResp.ok) throw new Error('Failed to save changes');

            // Update the source data
            this.languages = JSON.stringify(this._editLanguages);

            this.dispatchEvent(new CustomEvent('ol-language-edit-save', {
                bubbles: true, composed: true,
                detail: {
                    languages: this._editLanguages,
                    comment: this._comment,
                },
            }));

            this._close();
        } catch (err) {
            this._error = err.message || 'Something went wrong';
        } finally {
            this._isSaving = false;
        }
    }
}

customElements.define('ol-language-edit', OlLanguageEdit);
