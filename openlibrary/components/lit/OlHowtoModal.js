import { LitElement, html, css } from 'lit';

/**
 * Modal dialog showing the OL search help page in an iframe.
 *
 * @element ol-howto-modal
 * @prop {Boolean} open - when true the overlay is visible
 * @fires close - fired when the user dismisses the modal
 */
export class OlHowtoModal extends LitElement {
    static properties = {
        open: { type: Boolean },
    };

    constructor() {
        super();
        this.open = false;
        this._onKey = e => { if (this.open && e.key === 'Escape') this._close(); };
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('keydown', this._onKey);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('keydown', this._onKey);
    }

    _close() {
        this.dispatchEvent(new CustomEvent('close', { bubbles: true, composed: true }));
    }

    static styles = css`
        .overlay {
            position: fixed; inset: 0;
            background: rgba(0,0,0,.52);
            z-index: 9000;
            display: flex; align-items: center; justify-content: center;
        }
        .modal {
            background: white; border-radius: 10px;
            width: min(820px, 92vw); height: 82vh;
            display: flex; flex-direction: column;
            box-shadow: 0 24px 72px rgba(0,0,0,.35);
            overflow: hidden;
        }
        .modal-head {
            display: flex; align-items: center; justify-content: space-between;
            padding: 12px 16px; border-bottom: 1px solid hsl(0,0%,90%);
            flex-shrink: 0;
        }
        .modal-title {
            font-size: 14px; font-weight: 600;
            color: hsl(202,96%,28%);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }
        .close-btn {
            background: none; border: none; cursor: pointer;
            font-size: 20px; color: hsl(0,0%,45%); padding: 2px 7px;
            border-radius: 4px; line-height: 1; font-family: inherit;
        }
        .close-btn:hover { background: hsl(0,0%,94%); color: hsl(0,0%,20%); }
        iframe { flex: 1; border: none; width: 100%; }
    `;

    render() {
        if (!this.open) return html``;
        return html`
            <div class="overlay" @click=${this._close}>
                <div class="modal" @click=${e => e.stopPropagation()}>
                    <div class="modal-head">
                        <span class="modal-title">⚙️ Search Help &amp; Advanced Syntax</span>
                        <button class="close-btn" @click=${this._close} aria-label="Close">×</button>
                    </div>
                    <iframe
                        src="/search/howto"
                        title="Open Library Search Help"
                        loading="lazy">
                    </iframe>
                </div>
            </div>`;
    }
}

customElements.define('ol-howto-modal', OlHowtoModal);
