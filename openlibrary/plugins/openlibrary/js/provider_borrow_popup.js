/**
 * Borrow a book held by another library without leaving the book page (#13688).
 *
 * The CTA's href already borrows correctly on its own: it is
 * `/books/<olid>/-/borrow?action=borrow`, which renders the interstitial and
 * then runs Open Library's OAuth handshake with the lending node. All this
 * module does is put that same navigation in a popup window, so the page the
 * patron started on is still there when the loan is made, and refresh it.
 *
 * ## A popup, not an iframe
 *
 * This is the part to read before "simplifying" it. A popup is a top-level
 * browsing context, so the lending node's cookies are first-party inside it.
 * An iframe would make them third-party, and the flow does not survive that:
 *
 * 1. The node refuses to be framed at all. Its consent screen sends
 *    `X-Frame-Options: DENY` and `Content-Security-Policy: frame-ancestors
 *    'none'` (ArchiveLabs/lenny `lenny/routes/oauth2.py:289-290` at
 *    `origin/main` = 75b0906, pinned by `tests/test_oauth2_endpoints.py:798`).
 *    The frame renders nothing, in every browser.
 * 2. Even unframed-by-policy, the session cookie the node sets during sign-in
 *    is `SameSite=Lax` (`lenny/routes/oauth.py:232`, and five more places), so
 *    a browser would never send it back from a cross-site frame. That is every
 *    browser, not only Safari's ITP -- and that cookie is the one thing the
 *    node's reader accepts, so losing it means a loan the patron cannot open.
 *
 * The converse is what makes the popup work and is worth stating because it is
 * a property of a header nobody has set: neither openlibrary.org nor the node
 * sends `Cross-Origin-Opener-Policy` (checked live 2026-09-20; nothing in
 * `docker/*.conf`, nothing in the node's repo). `same-origin` on either side
 * would swap the browsing context group when the popup navigates to the node,
 * and `window.opener` below would be null on the way back. If this stops
 * working, check for that header first.
 *
 * See `ol-kb/wiki/lenny-oauth.md`.
 */

/**
 * Providers whose borrow Open Library runs itself.
 *
 * An allow-list rather than "every borrow CTA", because `read_button.html`'s
 * borrow branch also serves `DirectProvider`, whose URL is a third-party site
 * that belongs in a tab and not in a 520px window.
 */
const OAUTH_BORROW_PROVIDERS = new Set(['lenny']);

/** Must match `lenny.POPUP_MESSAGE_TYPE` in openlibrary/plugins/upstream/lenny.py. */
const MESSAGE_TYPE = 'ol-provider-borrow';

const POPUP_NAME = 'ol-provider-borrow';
const POPUP_FEATURES = 'popup=yes,width=520,height=700';
const CLEANUP_POLL_MS = 500;

/**
 * @param {NodeListOf<HTMLAnchorElement>|HTMLAnchorElement[]} links
 * @param {() => void} [refresh] Reload the page the patron is on.
 *   A parameter for one reason: it is the thing this module exists to do, and
 *   it cannot be observed otherwise. `window.location` is `[LegacyUnforgeable]`,
 *   so under jsdom both it and `location.reload` report
 *   `configurable: false, writable: false` and neither can be replaced by a
 *   test. Callers pass one argument.
 */
export function initProviderBorrowPopup(links, refresh = () => window.location.reload()) {
    for (const link of links) {
        if (OAUTH_BORROW_PROVIDERS.has(link.dataset.olProvider)) {
            link.addEventListener('click', (event) => onBorrowClick(event, refresh));
        }
    }
}

/**
 * @param {MouseEvent} event
 * @param {() => void} refresh
 */
function onBorrowClick(event, refresh) {
    // A patron who middle-clicks or holds a modifier asked for a tab. Let them
    // have it; the href works on its own.
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return;
    }

    // Opened before preventDefault, so a blocked popup falls through to the
    // anchor's own target="_blank". That path still borrows -- it just has no
    // opener, so the callback ends on its own page instead of refreshing this
    // one. Opening inside the click keeps the user activation the browser
    // requires; a popup opened later, from the interstitial's countdown, would
    // be blocked.
    const popup = window.open(event.currentTarget.href, POPUP_NAME, POPUP_FEATURES);
    if (!popup) {
        return;
    }
    event.preventDefault();
    awaitLoan(popup, refresh);
}

/**
 * Refresh this page once the popup reports a loan.
 *
 * Only an explicit success refreshes. A popup that simply closes is a patron
 * who backed out -- most often at the interstitial's Cancel -- and refreshing
 * them is churn with nothing to show. The cost of that choice: if the message
 * is ever lost while the loan succeeded, this page stays stale until the next
 * navigation. That is recoverable by clicking Borrow again, and the node
 * treats a second borrow of a book already on loan as the existing loan.
 *
 * @param {Window} popup
 * @param {() => void} refresh
 */
function awaitLoan(popup, refresh) {
    const onMessage = (event) => {
        if (event.origin !== window.location.origin) {
            return;
        }
        const data = event.data;
        if (!data || data.type !== MESSAGE_TYPE || !data.ok) {
            return;
        }
        stop();
        // Closed from here as well as by the popup itself: the reload below
        // discards this handle, and a popup whose own close() did not take
        // would be left orphaned with nobody holding it.
        try {
            popup.close();
        } catch {
            // Cross-origin at the moment of closing; the popup closes itself.
        }
        refresh();
    };

    const poll = setInterval(() => {
        if (popup.closed) {
            stop();
        }
    }, CLEANUP_POLL_MS);

    function stop() {
        clearInterval(poll);
        window.removeEventListener('message', onMessage);
    }

    window.addEventListener('message', onMessage);
}
