import { LitElement, css, html, nothing } from 'lit';
import { translate } from './utils/labels.js';
import { trackEvent } from '../../plugins/openlibrary/js/ol.analytics.js';
import './OlDialog.js';
import './OLButton.js';
import '@internetarchive/elements/ia-otp-form/ia-otp-form';

export const DEFAULT_LABELS = {
    heading: 'Log in or sign up',
    signupPrompt: 'New to Open Library?',
    signup: 'Create a free account',
    orLogIn: 'or log in',
    email: 'Email',
    password: 'Password',
    forgotPassword: 'Forgot your password?',
    rememberMe: 'Remember me',
    logIn: 'Log in',
    iaHint: 'Open Library accounts are Internet Archive accounts: log in with that email and password.',
    useCode: 'Email me a one-time code instead',
    usePassword: 'Use a password instead',
    otpTitle: 'Get a one-time code',
    otpIntro: "Enter your Internet Archive email and we'll send you a login code.",
    sendCode: 'Send code',
    enterCode: 'Enter your code',
    codeSent: 'We sent a 6-digit code to %(email)s.',
    useOtherEmail: 'Use a different email',
    continueOnLoginPage: 'Continue on the login page',
    thirdParty: 'Sign in with a third-party account',
    errorGeneric: 'Something went wrong. Please try again.',
    errorNetwork: 'A network error occurred. Please try again.',
    errorRateLimit: 'Too many attempts. Please wait a moment and try again.',
    errorCodeSend: 'Unable to send code. Please try again.',
    close: 'Close dialog',
    // Read by login-session.js when it swaps the signed-out header controls.
    myBooks: 'My Books'
};

/**
 * Login errors that need the full login page: a verification step, a locked
 * account, two accounts to connect. The dialog shows the message and a way there.
 */
const FULL_PAGE_ERRORS = new Set(['account_not_verified', 'ia_account_not_verified', 'accounts_not_connected', 'account_locked', 'account_blocked']);

/**
 * The in-page login for the moment a signed-out visitor tries something that
 * needs an account: a shelf button, a rating, a follow. It keeps them on the
 * page they were on, says why an account is needed, and offers a big step to
 * sign-up plus the three ways to log in — password, a one-time code by email,
 * and the archive.org third-party buttons (Google and the like) — all without
 * navigating. The sign-up itself stays on the existing `/account/create` page.
 *
 * Open it with `olLogin()` from `login-dialog.js`, which reuses the one
 * `shell/login_dialog.html.jinja` renders for signed-out visitors. The shell
 * element carries the translated labels and the third-party iframe URL, so a
 * page script never has to.
 *
 * On success it writes the reader's key onto `<body data-user-key>` and fires
 * `ol-login-success` at the document, so the surfaces that rendered for a
 * visitor (book-state.js, the header) can catch up without a reload.
 *
 * @element ol-login-dialog
 *
 * @prop {Boolean} open - Whether the dialog is open. Prefer `show()`, which
 *     also resolves with the outcome
 * @prop {String} heading - Dialog title. Default: the `heading` label
 * @prop {String} message - Why an account is needed right now, e.g. "Log in
 *     or sign up to add books to your reading log." Shown first, under the title
 * @prop {String} redirect - Where a sign-up or one-time-code login lands
 *     afterwards. Default: the current path, so the visitor comes back here
 * @prop {String} signupHref - The sign-up page. Default: "/account/create".
 *     Attribute: `signup-href`
 * @prop {String} thirdPartySrc - URL of archive.org's third-party sign-in
 *     frame. Rendered only while the dialog is open; unset hides the row.
 *     Attribute: `third-party-src`
 * @prop {Object} labels - Translated strings, merged over DEFAULT_LABELS
 *
 * @fires ol-login-success - The visitor is now logged in. detail: { userKey,
 *     method: 'password' | 'otp' | 'third-party' }. Bubbles to the document
 */
export class OlLoginDialog extends LitElement {
    static properties = {
        open: { type: Boolean, reflect: true },
        heading: { type: String },
        message: { type: String },
        redirect: { type: String },
        signupHref: { type: String, attribute: 'signup-href' },
        thirdPartySrc: { type: String, attribute: 'third-party-src' },
        labels: { type: Object },
        _view: { state: true },
        _busy: { state: true },
        _error: { state: true },
        _email: { state: true },
        _otpStatus: { state: true },
        _otpResending: { state: true }
    };

    static styles = css`
        :host {
            display: contents;
            font-family: var(--font-family-body);
        }

        ol-dialog {
            --ol-dialog-padding: var(--spacing-inset-lg);
        }

        .body {
            display: flex;
            flex-direction: column;
            color: var(--color-text);
            font-size: var(--font-size-body-medium);
            text-align: start;
        }

        p {
            margin: 0;
        }

        .message {
            margin-bottom: var(--spacing-stack-md);
            font-size: var(--font-size-body-large);
            text-wrap: pretty;
        }

        .signup {
            display: flex;
            flex-direction: column;
            gap: var(--spacing-stack-sm);
        }

        .signup__prompt {
            color: var(--color-text-secondary);
        }

        /* An overline between two hairlines: the quiet "or" of a login form. */
        .divider {
            display: flex;
            align-items: center;
            gap: var(--spacing-inline-md);
            margin-block: var(--spacing-stack-lg);
            color: var(--color-text-secondary);
            font-size: var(--font-size-overline);
            font-weight: var(--font-weight-overline);
            letter-spacing: var(--letter-spacing-overline);
            text-transform: var(--text-transform-overline);
        }

        .divider::before,
        .divider::after {
            content: '';
            flex: 1;
            border-top: 1px solid var(--color-border-subtle);
        }

        .third-party {
            display: block;
            width: 100%;
            height: 44px;
            margin-bottom: var(--spacing-stack-md);
            border: 0;
        }

        .form {
            display: flex;
            flex-direction: column;
            gap: var(--spacing-stack-md);
        }

        .field {
            display: flex;
            flex-direction: column;
            gap: var(--spacing-stack-xs);
        }

        .field__head {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: var(--spacing-inline-md);
            font-size: var(--font-size-label-large);
        }

        label {
            font-weight: var(--font-weight-medium);
        }

        .input {
            box-sizing: border-box;
            width: 100%;
            height: var(--control-height-large);
            padding: 0 var(--spacing-inset-sm);
            border: var(--border-input);
            border-radius: var(--border-radius-input);
            background: var(--color-surface);
            color: inherit;
            font: inherit;
            /* 16px, not the body size: iOS Safari zooms the page into any
               smaller text field (design.md, Mobile). */
            font-size: 16px;
        }

        .input:focus-visible {
            border: var(--border-input-focused);
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        @media (hover: hover) and (pointer: fine) {
            .input:hover {
                border: var(--border-input-hovered);
            }
        }

        .remember {
            display: flex;
            align-items: center;
            gap: var(--spacing-inline-sm);
            font-weight: var(--font-weight-regular);
        }

        .remember input {
            margin: 0;
        }

        .error {
            padding: var(--spacing-inset-sm);
            border: 1px solid var(--color-error-border);
            border-radius: var(--border-radius-notification);
            background: var(--color-error-bg);
            color: var(--color-error-fg);
        }

        .error a {
            display: block;
            margin-top: var(--spacing-stack-xs);
            color: inherit;
        }

        .hint {
            color: var(--color-text-secondary);
            font-size: var(--font-size-body-small);
            text-wrap: pretty;
        }

        /* The subheading role: a body size, semibold is what sets it apart. */
        .subheading {
            margin: 0 0 var(--spacing-stack-xs);
            font-family: var(--font-family-subheading);
            font-size: var(--font-size-body-large);
            font-weight: var(--font-weight-subheading);
            text-wrap: balance;
        }

        .subheading + .hint {
            margin-bottom: var(--spacing-stack-md);
        }

        .alt {
            margin-top: var(--spacing-stack-md);
            text-align: center;
        }

        a,
        .link {
            color: var(--color-link);
            text-decoration: underline;
        }

        .link {
            padding: 0;
            border: 0;
            background: none;
            font: inherit;
            cursor: pointer;
        }

        a:focus-visible,
        .link:focus-visible {
            border-radius: var(--border-radius-sm);
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        /* stylelint-disable-next-line selector-type-no-unknown -- archive.org's element */
        ia-otp-form {
            --font-size-standard: var(--font-size-body-medium);
            --font-size-lg: var(--font-size-title-large);
            --color-success: var(--color-success-fg);
            --color-danger: var(--color-error-fg);
            --link-color: var(--color-link);
        }
    `;

    constructor() {
        super();
        this.open = false;
        this.heading = '';
        this.message = '';
        this.redirect = '';
        this.signupHref = '/account/create';
        this.thirdPartySrc = '';
        this.labels = {};
        this._view = 'password';
        this._busy = false;
        this._error = null;
        this._email = '';
        this._otpStatus = 'ready';
        this._otpResending = false;
        /** What `show()` resolves with: set on success, null when dismissed. */
        this._result = null;
        this._resolve = null;
        this._onMessage = this._onMessage.bind(this);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        window.removeEventListener('message', this._onMessage);
    }

    t(key, vars) {
        return translate(this.labels, DEFAULT_LABELS, key, vars);
    }

    /**
     * Open the dialog and wait for the outcome.
     * @param {{heading?: string, message?: string, redirect?: string}} [options]
     * @returns {Promise<{userKey: string, method: string}|null>} The login, or
     *     null when the dialog was dismissed.
     */
    show({ heading, message, redirect } = {}) {
        if (heading !== undefined) this.heading = heading;
        if (message !== undefined) this.message = message;
        if (redirect !== undefined) this.redirect = redirect;
        this._view = 'password';
        this._error = null;
        this._busy = false;
        this._otpStatus = 'ready';
        this._result = null;
        // A second show() while open joins the first.
        this._pending ??= new Promise(resolve => {
            this._resolve = resolve;
        });
        this.open = true;
        return this._pending;
    }

    updated(changed) {
        if (!changed.has('open')) return;
        if (this.open) {
            window.addEventListener('message', this._onMessage);
            trackEvent('LoginDialog', 'Open');
        } else {
            window.removeEventListener('message', this._onMessage);
        }
    }

    /** Where to come back to: the page the visitor is on unless told otherwise. */
    get _returnTo() {
        return this.redirect || window.location.pathname + window.location.search;
    }

    get _signupUrl() {
        return this.signupHref;
    }

    get _loginPageUrl() {
        return `/account/login?redirect=${encodeURIComponent(this._returnTo)}`;
    }

    /** ol-dialog closed itself (Escape, backdrop, close button) or we closed it. */
    _onAfterClose(e) {
        if (e.target !== e.currentTarget) return;
        this.open = false;
        const resolve = this._resolve;
        this._resolve = null;
        this._pending = null;
        resolve?.(this._result);
    }

    /**
     * POST the login form and read the JSON answer: the same /account/login
     * the login page submits, asking for JSON so the page is kept.
     * @param {URLSearchParams} params
     * @param {'password' | 'third-party'} method
     */
    async _login(params, method) {
        this._busy = true;
        this._error = null;
        params.set('redirect', this._returnTo);
        try {
            const response = await fetch('/account/login', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { Accept: 'application/json', 'Content-Type': 'application/x-www-form-urlencoded' },
                body: params
            });
            let data = {};
            try {
                data = await response.json();
            } catch {
                // A non-JSON answer (a proxy page, a gateway error) is the generic error below.
            }
            if (response.ok && data.success) return this._succeed(data.user_key, method);
            this._error = { message: data.errorDisplayString || this.t('errorGeneric'), fullPage: FULL_PAGE_ERRORS.has(data.error) };
        } catch {
            this._error = { message: this.t('errorNetwork') };
        } finally {
            this._busy = false;
        }
    }

    /**
     * Tell the page, then close: book-state.js and the header catch up while
     * the dialog is still fading out, and show() resolves once it is gone.
     */
    _succeed(userKey, method) {
        this._result = { userKey: userKey || '', method };
        if (userKey) document.body.dataset.userKey = userKey;
        trackEvent('LoginDialog', 'Success', method);
        this.dispatchEvent(new CustomEvent('ol-login-success', { bubbles: true, composed: true, detail: this._result }));
        this.open = false;
    }

    _onSubmit(e) {
        e.preventDefault();
        const data = new FormData(e.target);
        // Kept so the one-time-code form opens with the same email.
        this._email = data.get('username') || this._email;
        this._login(new URLSearchParams(data), 'password');
    }

    /**
     * archive.org's frame answers a third-party sign-in with S3 keys, which
     * log in through the same form POST; it also reports its height.
     */
    _onMessage(e) {
        if (!/[./]archive\.org$/.test(e.origin)) return;
        const data = e.data || {};
        if (data.type === 'resize') {
            const frame = this.renderRoot.querySelector('.third-party');
            if (frame && data.height) frame.style.height = `${data.height}px`;
        } else if (data.type === 's3-keys' && data.s3) {
            this._login(new URLSearchParams({ access: data.s3.access, secret: data.s3.secret }), 'third-party');
        }
    }

    async _issueCode() {
        const response = await fetch('/account/login/otp/issue', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ email: this._email })
        });
        let data = {};
        try {
            data = await response.json();
        } catch {
            // Reported as a failed send below.
        }
        return { ok: Boolean(data.success), status: response.status };
    }

    async _onSendCode(e) {
        e.preventDefault();
        // From the form, not the input events: a password manager's fill sends none.
        this._email = new FormData(e.target).get('email') || this._email;
        this._busy = true;
        this._error = null;
        try {
            const { ok, status } = await this._issueCode();
            if (ok) {
                this._view = 'otp-code';
                this._otpStatus = 'ready';
            } else {
                this._error = { message: this.t(status === 429 ? 'errorRateLimit' : 'errorCodeSend') };
            }
        } catch {
            this._error = { message: this.t('errorNetwork') };
        } finally {
            this._busy = false;
        }
    }

    async _onCodeSubmitted(e) {
        this._otpStatus = 'loading';
        try {
            const response = await fetch('/account/login/otp/redeem', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: new URLSearchParams({ email: this._email, otp: e.detail, redirect: this._returnTo })
            });
            const data = await response.json();
            if (data.success) {
                this._otpStatus = 'success';
                this._succeed(data.user_key, 'otp');
            } else {
                this._otpStatus = 'error';
            }
        } catch {
            this._otpStatus = 'error';
        }
    }

    async _onResend() {
        this._otpResending = true;
        try {
            await this._issueCode();
        } catch {
            // ia-otp-form shows its own state; nothing to add.
        } finally {
            this._otpResending = false;
        }
    }

    _switchView(view) {
        this._view = view;
        this._error = null;
    }

    _renderError() {
        if (!this._error) return nothing;
        return html`
            <p class="error" role="alert">
                ${this._error.message} ${this._error.fullPage ? html`<a href=${this._loginPageUrl}>${this.t('continueOnLoginPage')}</a>` : nothing}
            </p>
        `;
    }

    _renderPassword() {
        return html`
            <div class="signup">
                <p class="signup__prompt">${this.t('signupPrompt')}</p>
                <ol-button variant="primary" full-width href=${this._signupUrl} @click=${() => trackEvent('LoginDialog', 'Signup')}
                    >${this.t('signup')}</ol-button
                >
            </div>
            <div class="divider" role="separator">${this.t('orLogIn')}</div>
            ${this.thirdPartySrc ? html`<iframe class="third-party" title=${this.t('thirdParty')} src=${this.thirdPartySrc} scrolling="no"></iframe>` : nothing}
            <form class="form" @submit=${this._onSubmit}>
                <div class="field">
                    <div class="field__head"><label for="login-email">${this.t('email')}</label></div>
                    <input
                        id="login-email"
                        class="input"
                        type="email"
                        name="username"
                        autocomplete="username"
                        autocapitalize="off"
                        required
                        .value=${this._email}
                        @input=${e => (this._email = e.target.value)}
                    />
                </div>
                <div class="field">
                    <div class="field__head">
                        <label for="login-password">${this.t('password')}</label>
                        <a href="https://archive.org/forgot-password" target="_blank" rel="noopener">${this.t('forgotPassword')}</a>
                    </div>
                    <input id="login-password" class="input" type="password" name="password" autocomplete="current-password" required />
                </div>
                <label class="remember"><input type="checkbox" name="remember" value="true" /> ${this.t('rememberMe')}</label>
                ${this._renderError()}
                <ol-button type="submit" variant="primary" full-width ?loading=${this._busy}>${this.t('logIn')}</ol-button>
                <p class="hint">${this.t('iaHint')}</p>
            </form>
            <p class="alt"><button type="button" class="link" @click=${() => this._switchView('otp-email')}>${this.t('useCode')}</button></p>
        `;
    }

    _renderOtpEmail() {
        return html`
            <h3 class="subheading">${this.t('otpTitle')}</h3>
            <p class="hint">${this.t('otpIntro')}</p>
            <form class="form" @submit=${this._onSendCode}>
                <div class="field">
                    <div class="field__head"><label for="otp-email">${this.t('email')}</label></div>
                    <input
                        id="otp-email"
                        class="input"
                        type="email"
                        name="email"
                        autocomplete="username"
                        autocapitalize="off"
                        required
                        .value=${this._email}
                        @input=${e => (this._email = e.target.value)}
                    />
                </div>
                ${this._renderError()}
                <ol-button type="submit" variant="primary" full-width ?loading=${this._busy}>${this.t('sendCode')}</ol-button>
            </form>
            <p class="alt"><button type="button" class="link" @click=${() => this._switchView('password')}>${this.t('usePassword')}</button></p>
        `;
    }

    _renderOtpCode() {
        return html`
            <h3 class="subheading">${this.t('enterCode')}</h3>
            <p class="hint">${this.t('codeSent', { email: this._email })}</p>
            <ia-otp-form
                .validationStatus=${this._otpStatus}
                .newCodeSending=${this._otpResending}
                @codeSubmitted=${this._onCodeSubmitted}
                @newCodeRequested=${this._onResend}
            ></ia-otp-form>
            <p class="alt"><button type="button" class="link" @click=${() => this._switchView('otp-email')}>${this.t('useOtherEmail')}</button></p>
        `;
    }

    render() {
        const views = { password: this._renderPassword, 'otp-email': this._renderOtpEmail, 'otp-code': this._renderOtpCode };
        return html`
            <ol-dialog
                label=${this.heading || this.t('heading')}
                label-close=${this.t('close')}
                width="small"
                .open=${this.open}
                @ol-after-close=${this._onAfterClose}
            >
                <div class="body">
                    ${this.message ? html`<p class="message">${this.message}</p>` : nothing} ${(views[this._view] ?? this._renderPassword).call(this)}
                </div>
            </ol-dialog>
        `;
    }
}

customElements.define('ol-login-dialog', OlLoginDialog);
