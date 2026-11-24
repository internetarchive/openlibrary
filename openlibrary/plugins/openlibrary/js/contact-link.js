/**
 * "Contact Us" mailto links: pre-fill the email body with the page the
 * patron was on, a link to their account page and a little about their browser, so
 * support can tell what a report is about without a round trip.
 *
 * Links opt in with `data-contact-link`. The translated notes come from the
 * link's `data-contact-note` and `data-contact-privacy` attributes, and the
 * signed-in username from `data-contact-username`. The detail labels stay in
 * English because support reads them.
 */

/** English fallbacks for the `data-contact-*` notes. */
export const DEFAULT_NOTE = 'Please write your message above this line.';
export const DEFAULT_PRIVACY = 'The details below help us look into your message. You can delete anything you would rather not share.';

/**
 * The page URL to report. The `#fragment` is dropped, and so is the query
 * string on `/account` pages, where it can carry one-time tokens.
 * @param {{origin: string, pathname: string, search: string}} location
 * @returns {string}
 */
export function pageUrl(location) {
    const search = location.pathname.startsWith('/account') ? '' : location.search;
    return `${location.origin}${location.pathname}${search}`;
}

/**
 * @param {{note: string, privacy: string}} strings
 * @param {object} env
 * @param {string} env.url
 * @param {string} env.account the patron's page URL, empty when signed out
 * @param {string} env.userAgent
 * @param {{width: number, height: number}} env.viewport
 * @returns {string}
 */
export function buildContactBody(strings, env) {
    return [
        '',
        '',
        '',
        `----- ${strings.note} -----`,
        strings.privacy,
        '',
        `Page: ${env.url}`,
        ...(env.account ? [`Account: ${env.account}`] : []),
        `Browser: ${env.userAgent}`,
        `Window size: ${env.viewport.width}x${env.viewport.height}`
    ].join('\r\n');
}

/**
 * Return `href` with its `body` parameter set to `body`, keeping the other
 * mailto parameters (e.g. `subject`).
 * @param {string} href
 * @param {string} body
 * @returns {string}
 */
export function withBody(href, body) {
    const [address, query = ''] = href.split('?');
    const params = query.split('&').filter(param => param && !param.toLowerCase().startsWith('body='));
    params.push(`body=${encodeURIComponent(body)}`);
    return `${address}?${params.join('&')}`;
}

/**
 * @param {NodeList<HTMLAnchorElement>} links
 */
export function initContactLinks(links) {
    for (const link of links) {
        const strings = {
            note: link.dataset.contactNote || DEFAULT_NOTE,
            privacy: link.dataset.contactPrivacy || DEFAULT_PRIVACY
        };
        const username = link.dataset.contactUsername;
        // Build on click so the URL and window size are current.
        link.addEventListener('click', () => {
            const env = {
                url: pageUrl(window.location),
                account: username ? `${window.location.origin}/people/${encodeURIComponent(username)}` : '',
                userAgent: navigator.userAgent,
                viewport: { width: window.innerWidth, height: window.innerHeight }
            };
            link.href = withBody(link.getAttribute('href'), buildContactBody(strings, env));
        });
    }
}
