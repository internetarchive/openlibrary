/**
 * Site-level glue for banner dismissals.
 *
 * The <ol-banner> component is generic: dismissing fires an
 * `ol-banner-dismiss` event and removes the element, nothing more. This
 * module is the Open Library-specific persistence layer — it listens for
 * those events and POSTs to /hide_banner, which sets a truthy cookie named
 * after the banner's dismiss-id (and, server-side, syncs yrg* dismissals to
 * the user's account preferences). Templates then guard rendering on that
 * cookie, so dismissed banners are never served again.
 *
 * Per-banner cookie TTL rides on the element as data-cookie-duration-days —
 * an OL convention, not part of the component's API.
 */

/**
 * Persist a banner dismissal by POSTing to /hide_banner.
 *
 * @param {string} cookieName
 * @param {number} cookieDurationDays
 * @returns {Promise<Response>}
 */
function setBannerCookie(cookieName, cookieDurationDays) {
    return fetch('/hide_banner', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
        },
        body: JSON.stringify({
            'cookie-name': cookieName,
            'cookie-duration-days': cookieDurationDays,
        }),
    });
}

/**
 * Listen document-wide for <ol-banner> dismissals and persist them.
 * Banners without a dismiss-id are page-only and left alone.
 */
export function initOlBannerDismissals() {
    document.addEventListener('ol-banner-dismiss', (e) => {
        const dismissId = e.detail?.dismissId;
        if (!dismissId) return;
        const days = Number(e.target?.dataset?.cookieDurationDays) || 30;
        setBannerCookie(dismissId, days).catch(() => {});
    });
}

/**
 * Add click listeners to all legacy banner dismiss buttons.
 *
 * @param {NodeList<HTMLElement>} banners
 */
export function initDismissibleBanners(banners) {
    for (const banner of banners) {
        const cookieName = banner.dataset.cookieName;
        const cookieDurationDays = banner.dataset.cookieDurationDays;

        const dismissButton = banner.querySelector('.page-banner--dismissable-close');
        dismissButton.addEventListener('click', () => {
            setBannerCookie(cookieName, cookieDurationDays)
                .then((res) => {
                    if (res.ok) banner.remove();
                })
                .catch(() => {});
        });
    }
}
