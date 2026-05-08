import { LitElement, html, css, nothing } from 'lit';
import '@internetarchive/elements/ia-otp-form/ia-otp-form';

/**
 * OTP login flow for Open Library.
 *
 * Renders a trigger button that opens a modal dialog. The modal walks the
 * patron through two steps:
 *   1. Enter email  → POST /account/login/otp/issue
 *   2. Enter code   → POST /account/login/otp/redeem  (via ia-otp-form)
 *
 * On success the page navigates to the server-sanitized redirect URL.
 *
 * Usage:
 *   <ol-otp-login></ol-otp-login>
 *   <ol-otp-login redirect="/account/books"></ol-otp-login>
 *
 * @prop {String} redirect - Hint for post-login destination; sanitized server-side
 */
export class OpenLibraryOTP extends LitElement {
    static properties = {
        redirect: { type: String },
        _open: { type: Boolean, state: true },
        _step: { type: String, state: true },
        _email: { type: String, state: true },
        _submitting: { type: Boolean, state: true },
        _issueError: { type: String, state: true },
        _validationStatus: { type: String, state: true },
        _newCodeSending: { type: Boolean, state: true },
    };

    constructor() {
        super();
        this.redirect = '/account/books';
        this._open = false;
        this._step = 'email';
        this._email = '';
        this._submitting = false;
        this._issueError = '';
        this._validationStatus = 'ready';
        this._newCodeSending = false;
        this._previousFocus = null;
    }

    static styles = css`
        :host {
            display: inline-block;
        }

        .trigger-btn {
            background: var(--ia-button-primary-bg, #4b4bdf);
            color: var(--ia-button-primary-color, #fff);
            border: none;
            border-radius: 4px;
            padding: 8px 16px;
            font-size: 1rem;
            font-family: inherit;
            cursor: pointer;
            width: fit-content;
        }
        .trigger-btn:hover,
        .trigger-btn:focus {
            background: var(--ia-button-primary-bg-hover, #3a3abf);
            outline: 2px solid currentColor;
            outline-offset: 2px;
        }

        .overlay {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.5);
            z-index: 1000;
            align-items: center;
            justify-content: center;
        }
        .overlay[open] {
            display: flex;
        }

        .dialog {
            background: #fff;
            border-radius: 8px;
            padding: 2rem;
            max-width: 400px;
            width: 90%;
            position: relative;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        }

        .close-btn {
            position: absolute;
            top: 0.75rem;
            right: 0.75rem;
            background: none;
            border: none;
            font-size: 1.5rem;
            cursor: pointer;
            line-height: 1;
            color: inherit;
        }

        h2 {
            margin: 0 0 0.5rem;
            font-size: 1.25rem;
        }
        p {
            margin: 0 0 1rem;
            font-size: 0.95rem;
        }

        .email-form {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }
        .email-form label {
            font-size: 0.9rem;
            font-weight: bold;
        }
        .email-form input[type='email'] {
            padding: 8px;
            font-size: 1rem;
            border: 1px solid #ccc;
            border-radius: 4px;
            width: 100%;
            box-sizing: border-box;
        }
        .email-form button[type='submit'] {
            padding: 8px 16px;
            background: var(--ia-button-primary-bg, #4b4bdf);
            color: var(--ia-button-primary-color, #fff);
            border: none;
            border-radius: 4px;
            font-size: 1rem;
            font-family: inherit;
            cursor: pointer;
            align-self: flex-start;
        }
        .email-form button[type='submit']:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        .error {
            color: var(--color-danger, #c00);
            font-size: 0.9rem;
            margin: 0;
        }

        ia-otp-form {
            --font-size-standard: 0.95rem;
            --font-size-lg: 1.5rem;
            --color-success: #008000;
            --color-danger: #c00;
            --link-color: #4b4bdf;
            margin-top: 0.5rem;
        }

        /* Visually-hidden focus sentinels used for focus-trapping */
        .focus-sentinel {
            position: absolute;
            width: 1px;
            height: 1px;
            overflow: hidden;
            clip: rect(0 0 0 0);
            white-space: nowrap;
        }
    `;

    render() {
        return html`
            <button class="trigger-btn" @click=${this._openModal}>
                Sign in with a one-time code
            </button>

            <div
                class="overlay"
                ?open=${this._open}
                @click=${this._handleOverlayClick}
                @keydown=${this._handleKeydown}
            >
                <div
                    class="dialog"
                    role="dialog"
                    aria-modal="true"
                    aria-label="Sign in with a one-time code"
                    tabindex="-1"
                >
                    <!-- Focus sentinel: catches Shift+Tab past the first element -->
                    <div
                        class="focus-sentinel"
                        tabindex="0"
                        @focus=${this._focusLast}
                    ></div>

                    <button
                        class="close-btn"
                        @click=${this._closeModal}
                        aria-label="Close"
                    >
                        &times;
                    </button>
                    ${this._step === 'email'
        ? this._emailTemplate
        : this._codeTemplate}

                    <!-- Focus sentinel: catches Tab past the last element -->
                    <div
                        class="focus-sentinel"
                        tabindex="0"
                        @focus=${this._focusFirst}
                    ></div>
                </div>
            </div>
        `;
    }

    get _emailTemplate() {
        return html`
            <h2>Sign in with a one-time code</h2>
            <p>
                Enter your Internet Archive email and we'll send you a login
                code.
            </p>
            <form class="email-form" @submit=${this._handleEmailSubmit}>
                <label for="otp-email">Email</label>
                <input
                    type="email"
                    id="otp-email"
                    .value=${this._email}
                    @input=${(e) => (this._email = e.target.value)}
                    autocomplete="email"
                    required
                />
                ${this._issueError
        ? html`<p class="error">${this._issueError}</p>`
        : nothing}
                <button type="submit" ?disabled=${this._submitting}>
                    ${this._submitting ? 'Sending…' : 'Send me a code'}
                </button>
            </form>
        `;
    }

    get _codeTemplate() {
        return html`
            <h2>Enter your code</h2>
            <p>
                We sent a 6-digit code to
                <strong>${this._email}</strong>.
            </p>
            <ia-otp-form
                .validationStatus=${this._validationStatus}
                .newCodeSending=${this._newCodeSending}
                @codeSubmitted=${this._handleCodeSubmitted}
                @newCodeRequested=${this._handleResend}
            ></ia-otp-form>
        `;
    }

    updated(changedProperties) {
        if (!changedProperties.has('_open')) return;
        if (this._open) {
            // Focus the first interactive element once the dialog renders
            requestAnimationFrame(() => {
                const first = this.shadowRoot.querySelector(
                    '.dialog input, .dialog button:not(.close-btn)'
                );
                (first || this.shadowRoot.querySelector('.dialog')).focus();
            });
        } else if (this._previousFocus) {
            this._previousFocus.focus();
            this._previousFocus = null;
        }
    }

    _openModal() {
        this._previousFocus = document.activeElement;
        this._open = true;
        this._step = 'email';
        this._issueError = '';
        this._validationStatus = 'ready';
    }

    _closeModal() {
        this._open = false;
    }

    _handleOverlayClick(e) {
        if (e.target === e.currentTarget) this._closeModal();
    }

    _handleKeydown(e) {
        if (e.key === 'Escape') this._closeModal();
    }

    /** Redirect Tab-past-end back to the first focusable element */
    _focusFirst() {
        const el = this.shadowRoot.querySelector(
            '.dialog button.close-btn, .dialog input, .dialog button:not([disabled])'
        );
        el?.focus();
    }

    /** Redirect Shift+Tab-past-start back to the last focusable element */
    _focusLast() {
        const candidates = this.shadowRoot.querySelectorAll(
            '.dialog button:not([disabled]), .dialog input:not([disabled])'
        );
        candidates[candidates.length - 1]?.focus();
    }

    async _handleEmailSubmit(e) {
        e.preventDefault();
        this._submitting = true;
        this._issueError = '';
        try {
            const resp = await fetch('/account/login/otp/issue', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams({ email: this._email }),
            });
            const data = await resp.json();
            if (data.success) {
                this._step = 'code';
                this._validationStatus = 'ready';
            } else if (resp.status === 429) {
                this._issueError =
                    'Too many attempts. Please wait a moment and try again.';
            } else {
                this._issueError = 'Unable to send code. Please try again.';
            }
        } catch {
            this._issueError = 'A network error occurred. Please try again.';
        } finally {
            this._submitting = false;
        }
    }

    async _handleCodeSubmitted(e) {
        this._validationStatus = 'loading';
        try {
            const resp = await fetch('/account/login/otp/redeem', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams({
                    email: this._email,
                    otp: e.detail,
                    redirect: this.redirect,
                }),
            });
            const data = await resp.json();
            if (data.success) {
                this._validationStatus = 'success';
                // Navigate to server-sanitized redirect (never raw this.redirect)
                window.location.href = data.redirect;
            } else {
                this._validationStatus = 'error';
            }
        } catch {
            this._validationStatus = 'error';
        }
    }

    async _handleResend() {
        this._newCodeSending = true;
        try {
            await fetch('/account/login/otp/issue', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams({ email: this._email }),
            });
        } finally {
            this._newCodeSending = false;
        }
    }
}

customElements.define('ol-otp-login', OpenLibraryOTP);
