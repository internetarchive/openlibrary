import { LitElement, html, css } from 'lit';

/**
 * OLDeleteBtn - A generic delete button web component with a built-in confirmation dialog.
 *
 * When clicked, shows a native browser confirm() dialog before dispatching
 * a confirmation event. The consuming page is responsible for handling the
 * actual deletion (e.g. form submission).
 *
 * @property {String} label      - Button label text. Default: "Delete"
 * @property {String} itemName   - Name of the item to delete, used in confirm message.
 * @property {Number} itemCount  - Number of linked items affected by deletion. (Optional)
 * @property {String} linkedLabel - What the linked items are called. Default: "linked items" (Optional)
 *
 * @fires ol-delete-btn-confirm - Fired when the user confirms deletion.
 *   detail: { itemCount: Number }
 *
 * @example <caption>Series with linked works</caption>
 * <ol-delete-btn
 *   label="Delete Series"
 *   item-name="The Lord of the Rings"
 *   item-count="5"
 *   linked-label="works"
 * ></ol-delete-btn>
 *
 * @example <caption>Simple item with no linked content</caption>
 * <ol-delete-btn
 *   label="Delete List"
 *   item-name="My Reading List"
 * ></ol-delete-btn>
 */
export class OLDeleteBtn extends LitElement {
    static properties = {
        label: { type: String },
        itemName: { type: String, attribute: 'item-name' },
        itemCount: { type: Number, attribute: 'item-count' },
        linkedLabel: { type: String, attribute: 'linked-label' },
    };

    static styles = css`
        :host {
            display: inline-block;
        }

        .delete-btn {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 0 18px;
            height: 38px;
            border: 1.5px solid var(--danger-red, #A32D2D);
            border-radius: var(--border-radius-chip, 6px);
            font-family: var(--font-family-button);
            font-size: var(--font-size-body-medium);
            font-weight: 500;
            background: transparent;
            color: var(--danger-red, #A32D2D);
            cursor: pointer;
            user-select: none;
            white-space: nowrap;
            transition: background 0.15s, color 0.15s;
        }

        @media (hover: hover) and (pointer: fine) {
            .delete-btn:hover {
                background: var(--danger-red, #A32D2D);
                color: var(--white);
            }

            .delete-btn:hover .icon {
                stroke: var(--white);
            }
        }

        .delete-btn:active {
            transform: scale(0.97);
        }

        .delete-btn:focus-visible {
            outline: none;
            box-shadow: var(--box-shadow-focus);
        }

        .icon {
            width: 15px;
            height: 15px;
            stroke: var(--danger-red, #A32D2D);
            fill: none;
            stroke-width: 2;
            stroke-linecap: round;
            stroke-linejoin: round;
            flex-shrink: 0;
            transition: stroke 0.15s;
        }
    `;

    constructor() {
        super();
        this.label = 'Delete';
        this.itemName = '';
        this.itemCount = 0;
        this.linkedLabel = 'linked items';
    }

    _buildConfirmMessage() {
        const name = this.itemName ? `"${this.itemName}"` : 'this item';
        if (this.itemCount === 1) {
            return `${name} has 1 ${this.linkedLabel.replace(/s$/, '')}. Deleting it will remove this from that item.\n\nAre you sure you want to delete it?`;
        } else if (this.itemCount > 1) {
            return `${name} has ${this.itemCount} ${this.linkedLabel}. Deleting it will remove this from all of them.\n\nAre you sure you want to delete it?`;
        }
        return `Are you sure you want to delete ${name}? This cannot be undone.`;
    }

    _handleClick() {
        if (!confirm(this._buildConfirmMessage())) return;

        this.dispatchEvent(new CustomEvent('ol-delete-btn-confirm', {
            bubbles: true,
            composed: true,
            detail: { itemCount: this.itemCount },
        }));
    }

    _renderIcon() {
        return html`
            <svg
                class="icon"
                aria-hidden="true"
                viewBox="0 0 24 24"
            >
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                <path d="M10 11v6"/>
                <path d="M14 11v6"/>
                <path d="M9 6V4h6v2"/>
            </svg>
        `;
    }

    render() {
        return html`
            <button
                class="delete-btn"
                type="button"
                aria-label="${this.label}${this.itemName ? ` ${this.itemName}` : ''}"
                @click=${this._handleClick}
            >
                ${this._renderIcon()}
                ${this.label}
            </button>
        `;
    }
}

customElements.define('ol-delete-btn', OLDeleteBtn);
