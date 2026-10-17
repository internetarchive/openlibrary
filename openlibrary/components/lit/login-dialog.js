/**
 * Promise-based login on top of <ol-login-dialog>, for the moment a signed-out
 * visitor tries something that needs an account.
 *
 *     const login = await olLogin({ message: i18n.loginToShelve });
 *     if (login) { ... login.userKey ... }
 *
 * Reuses the <ol-login-dialog> that shell/login_dialog.html.jinja renders for
 * signed-out visitors — it carries the translated labels and the third-party
 * sign-in frame — and creates a bare one when a page has none. Like
 * alert-dialog.js, it creates the element rather than importing the class so
 * page scripts don't bundle a second copy; ol-components.js registers it.
 */

/** The page's login dialog, created on first use when the shell rendered none. */
export function loginDialog() {
    let dialog = document.querySelector('ol-login-dialog');
    if (!dialog) {
        dialog = document.createElement('ol-login-dialog');
        document.body.append(dialog);
    }
    return dialog;
}

/**
 * Opens the login dialog and waits for the outcome. Already logged in (the
 * body carries a reader key) it resolves at once, so callers can be
 * unconditional.
 *
 * @param {Object} [options]
 * @param {String} [options.message] - Translated; why an account is needed
 *     right now, e.g. "Log in or sign up to add books to your reading log."
 * @param {String} [options.heading] - Translated dialog title; defaults to
 *     the dialog's own.
 * @param {String} [options.redirect] - Where a sign-up or one-time-code login
 *     lands afterwards; defaults to the current page.
 * @returns {Promise<{userKey: String, method: String}|null>} The login, or
 *     null when the visitor dismissed the dialog.
 */
export async function olLogin({ message, heading, redirect } = {}) {
    const userKey = document.body.dataset.userKey;
    if (userKey) return { userKey, method: 'session' };
    await customElements.whenDefined('ol-login-dialog');
    return loginDialog().show({ message, heading, redirect });
}
