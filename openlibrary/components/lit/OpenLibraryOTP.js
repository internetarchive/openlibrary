import { LitElement, html, css } from 'lit';
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
 * The overlay is appended directly to document.body (a "portal") and managed
 * imperatively so that it escapes any ancestor stacking contexts. Lit's
 * declarative render() is only used for the trigger button inside the shadow DOM.
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

        // Bound references kept for addEventListener / removeEventListener symmetry
        this._boundHandleOverlayClick = this._handleOverlayClick.bind(this);
        this._boundHandleKeydown = this._handleKeydown.bind(this);
        this._boundFocusFirst = this._focusFirst.bind(this);
        this._boundFocusLast = this._focusLast.bind(this);
        this._boundCloseModal = this._closeModal.bind(this);
        this._boundHandleEmailInput = (e) => { this._email = e.target.value; };
        this._boundHandleEmailSubmit = this._handleEmailSubmit.bind(this);
        this._boundHandleCodeSubmitted = this._handleCodeSubmitted.bind(this);
        this._boundHandleResend = this._handleResend.bind(this);

        this._buildPortal();
    }

    // ---------------------------------------------------------------------------
    // Portal construction — runs once; produces stable DOM that we mutate later
    // ---------------------------------------------------------------------------

    _buildPortal() {
        const style = document.createElement('style');
        style.textContent = `
            .ol-otp-overlay {
                display: none;
                position: fixed;
                inset: 0;
                background: rgba(0, 0, 0, 0.5);
                z-index: 1000;
                align-items: center;
                justify-content: center;
            }
            .ol-otp-overlay[open] {
                display: flex;
            }
            .ol-otp-dialog {
                background: #fff;
                border-radius: 8px;
                padding: 2rem;
                max-width: 400px;
                width: 90%;
                position: relative;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
                font-family: inherit;
            }
            .ol-otp-close-btn {
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
            .ol-otp-dialog h2 {
                margin: 0 0 0.5rem;
                font-size: 1.25rem;
            }
            .ol-otp-dialog p {
                margin: 0 0 1rem;
                font-size: 0.95rem;
            }
            .ol-otp-email-form {
                display: flex;
                flex-direction: column;
                gap: 0.75rem;
            }
            .ol-otp-email-form label {
                font-size: 0.9rem;
                font-weight: bold;
            }
            .ol-otp-email-form input[type='email'] {
                padding: 8px;
                font-size: 1rem;
                border: 1px solid #ccc;
                border-radius: 4px;
                width: 100%;
                box-sizing: border-box;
            }
            .ol-otp-email-form button[type='submit'] {
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
            .ol-otp-email-form button[type='submit']:disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }
            .ol-otp-error {
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
            .ol-otp-focus-sentinel {
                position: absolute;
                width: 1px;
                height: 1px;
                overflow: hidden;
                clip: rect(0 0 0 0);
                white-space: nowrap;
            }
        `;

        // Overlay
        this._overlay = document.createElement('div');
        this._overlay.className = 'ol-otp-overlay';

        // Dialog
        this._dialog = document.createElement('div');
        this._dialog.className = 'ol-otp-dialog';
        this._dialog.setAttribute('role', 'dialog');
        this._dialog.setAttribute('aria-modal', 'true');
        this._dialog.setAttribute('aria-label', 'Sign in with a one-time code');
        this._dialog.setAttribute('tabindex', '-1');

        // Focus sentinels
        this._sentinelStart = document.createElement('div');
        this._sentinelStart.className = 'ol-otp-focus-sentinel';
        this._sentinelStart.setAttribute('tabindex', '0');

        this._sentinelEnd = document.createElement('div');
        this._sentinelEnd.className = 'ol-otp-focus-sentinel';
        this._sentinelEnd.setAttribute('tabindex', '0');

        // Close button
        this._closeBtn = document.createElement('button');
        this._closeBtn.className = 'ol-otp-close-btn';
        this._closeBtn.setAttribute('aria-label', 'Close');
        this._closeBtn.innerHTML = '&times;';

        // Content container — swapped between email and code step
        this._contentContainer = document.createElement('div');

        this._dialog.append(
            this._sentinelStart,
            this._closeBtn,
            this._contentContainer,
            this._sentinelEnd,
        );
        this._overlay.appendChild(this._dialog);

        // Portal container
        this._portal = document.createElement('div');
        this._portal.setAttribute('data-ol-otp-portal', '');
        this._portal.append(style, this._overlay);

        // Wire permanent listeners (these never need to be re-added)
        this._overlay.addEventListener('click', this._boundHandleOverlayClick);
        this._overlay.addEventListener('keydown', this._boundHandleKeydown);
        this._closeBtn.addEventListener('click', this._boundCloseModal);
        this._sentinelStart.addEventListener('focus', this._boundFocusLast);
        this._sentinelEnd.addEventListener('focus', this._boundFocusFirst);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._portal.remove();
    }

    // ---------------------------------------------------------------------------
    // Shadow DOM — trigger button only
    // ---------------------------------------------------------------------------

    static styles = css`
        :host { display: inline-block; }

        .trigger-btn {
            background: var(--primary-blue, hsl(202, 96%, 37%));
            color: var(--ia-button-primary-color, #fff);
            border: none;
            border-radius: 4px;
            padding: 8px 16px;
            font-size: var(--font-size-label-large, 14px);
            font-family: inherit;
            cursor: pointer;
            width: 100%;
            margin-top: 10px;
        }
        .trigger-btn:hover,
        .trigger-btn:focus {
            background: hsl(202, 96%, 17%);
            outline: 2px solid currentColor;
            outline-offset: 2px;
        }
    `;

    render() {
        return html`
            <button class="trigger-btn" @click=${this._openModal}>
                Sign in with a one-time code
            </button>
        `;
    }

    // ---------------------------------------------------------------------------
    // Imperative portal updates — called whenever state changes
    // ---------------------------------------------------------------------------

    updated() {
        if (!this._portal.isConnected) {
            document.body.appendChild(this._portal);
        }

        // Toggle overlay visibility
        this._overlay.toggleAttribute('open', this._open);

        // Render the correct step content
        if (this._open) {
            if (this._step === 'email') {
                this._renderEmailStep();
            } else {
                this._renderCodeStep();
            }
        }
    }

    _renderEmailStep() {
        // Only rebuild if we're not already showing the email step
        if (this._contentContainer.dataset.step === 'email') {
            // Just patch the dynamic parts in place
            const submitBtn = this._contentContainer.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = this._submitting;
                submitBtn.textContent = this._submitting ? 'Sending…' : 'Send me a code';
            }
            const emailInput = this._contentContainer.querySelector('input[type="email"]');
            if (emailInput && emailInput !== document.activeElement) {
                emailInput.value = this._email;
            }
            // Error message
            let errorEl = this._contentContainer.querySelector('.ol-otp-error');
            if (this._issueError) {
                if (!errorEl) {
                    errorEl = document.createElement('p');
                    errorEl.className = 'ol-otp-error';
                    const submitBtn = this._contentContainer.querySelector('button[type="submit"]');
                    this._contentContainer.querySelector('.ol-otp-email-form').insertBefore(errorEl, submitBtn);
                }
                errorEl.textContent = this._issueError;
            } else if (errorEl) {
                errorEl.remove();
            }
            return;
        }

        // Full rebuild of email step
        this._teardownCodeStep();
        this._contentContainer.dataset.step = 'email';
        this._contentContainer.innerHTML = '';

        const h2 = document.createElement('h2');
        h2.textContent = 'Sign in with a one-time code';

        const p = document.createElement('p');
        p.textContent = 'Enter your Internet Archive email and we\'ll send you a login code.';

        const form = document.createElement('form');
        form.className = 'ol-otp-email-form';

        const label = document.createElement('label');
        label.setAttribute('for', 'otp-email');
        label.textContent = 'Email';

        const input = document.createElement('input');
        input.type = 'email';
        input.id = 'otp-email';
        input.value = this._email;
        input.setAttribute('autocomplete', 'email');
        input.required = true;
        input.addEventListener('input', this._boundHandleEmailInput);

        const submitBtn = document.createElement('button');
        submitBtn.type = 'submit';
        submitBtn.disabled = this._submitting;
        submitBtn.textContent = this._submitting ? 'Sending…' : 'Send me a code';

        form.append(label, input, submitBtn);
        form.addEventListener('submit', this._boundHandleEmailSubmit);

        if (this._issueError) {
            const errorEl = document.createElement('p');
            errorEl.className = 'ol-otp-error';
            errorEl.textContent = this._issueError;
            form.insertBefore(errorEl, submitBtn);
        }

        this._contentContainer.append(h2, p, form);
    }

    _renderCodeStep() {
        if (this._contentContainer.dataset.step === 'code') {
            // Patch ia-otp-form properties in place
            const otpForm = this._contentContainer.querySelector('ia-otp-form');
            if (otpForm) {
                otpForm.validationStatus = this._validationStatus;
                otpForm.newCodeSending = this._newCodeSending;
            }
            return;
        }

        this._teardownEmailStep();
        this._contentContainer.dataset.step = 'code';
        this._contentContainer.innerHTML = '';

        const h2 = document.createElement('h2');
        h2.textContent = 'Enter your code';

        const p = document.createElement('p');
        p.innerHTML = `We sent a 6-digit code to <strong>${this._email}</strong>.`;

        const otpForm = document.createElement('ia-otp-form');
        otpForm.validationStatus = this._validationStatus;
        otpForm.newCodeSending = this._newCodeSending;
        otpForm.addEventListener('codeSubmitted', this._boundHandleCodeSubmitted);
        otpForm.addEventListener('newCodeRequested', this._boundHandleResend);

        this._contentContainer.append(h2, p, otpForm);
    }

    _teardownEmailStep() {
        const form = this._contentContainer.querySelector('.ol-otp-email-form');
        form?.removeEventListener('submit', this._boundHandleEmailSubmit);
        const input = this._contentContainer.querySelector('input[type="email"]');
        input?.removeEventListener('input', this._boundHandleEmailInput);
    }

    _teardownCodeStep() {
        const otpForm = this._contentContainer.querySelector('ia-otp-form');
        otpForm?.removeEventListener('codeSubmitted', this._boundHandleCodeSubmitted);
        otpForm?.removeEventListener('newCodeRequested', this._boundHandleResend);
    }

    // ---------------------------------------------------------------------------
    // Modal lifecycle
    // ---------------------------------------------------------------------------

    _openModal() {
        this._previousFocus = document.activeElement;
        this._open = true;
        this._step = 'email';
        this._issueError = '';
        this._validationStatus = 'ready';

        requestAnimationFrame(() => {
            const first = this._contentContainer.querySelector(
                'input, button:not(.ol-otp-close-btn)'
            );
            (first || this._dialog).focus();
        });
    }

    _closeModal() {
        this._open = false;
        if (this._step === 'email') this._teardownEmailStep();
        else this._teardownCodeStep();
        this._contentContainer.innerHTML = '';
        delete this._contentContainer.dataset.step;

        if (this._previousFocus) {
            this._previousFocus.focus();
            this._previousFocus = null;
        }
    }

    _handleOverlayClick(e) {
        // Keep the modal open while the user is entering their code — they are
        // likely switching back from their email client and an accidental click
        // should not lose their place in the flow.
        if (this._step === 'code') return;
        if (e.target === e.currentTarget) this._closeModal();
    }

    _handleKeydown(e) {
        if (e.key === 'Escape') this._closeModal();
    }

    /** Redirect Tab-past-end back to the first focusable element */
    _focusFirst() {
        const el = this._dialog.querySelector(
            'button.ol-otp-close-btn, input, button:not([disabled])'
        );
        el?.focus();
    }

    /** Redirect Shift+Tab-past-start back to the last focusable element */
    _focusLast() {
        const candidates = this._dialog.querySelectorAll(
            'button:not([disabled]), input:not([disabled])'
        );
        candidates[candidates.length - 1]?.focus();
    }

    // ---------------------------------------------------------------------------
    // Fetch handlers
    // ---------------------------------------------------------------------------

    async _handleEmailSubmit(e) {
        e.preventDefault();
        this._submitting = true;
        this._issueError = '';
        try {
            const resp = await fetch('/account/login/otp/issue', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: new URLSearchParams({ email: this._email }),
            });
            const data = await resp.json();
            if (data.success) {
                this._step = 'code';
                this._validationStatus = 'ready';
            } else if (resp.status === 429) {
                this._issueError = 'Too many attempts. Please wait a moment and try again.';
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
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
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
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: new URLSearchParams({ email: this._email }),
            });
        } finally {
            this._newCodeSending = false;
        }
    }
}

customElements.define('ol-otp-login', OpenLibraryOTP);
