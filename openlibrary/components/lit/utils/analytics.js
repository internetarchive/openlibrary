/**
 * Matomo event reporting for the Lit components.
 *
 * Mirror of js/ol.analytics.js `trackEvent` (that bundle can't be imported
 * here). Components render into their shadow root, where Matomo's DOM-based
 * click trigger can't see a `data-ol-link-track` attribute — the event
 * retargets to the host before it reaches the document — so we push onto
 * Matomo's `_paq` queue by hand instead. Same category/action/label keys the
 * attribute would have carried.
 *
 * Guarded so a blocked or absent analytics script can never break the
 * interaction that triggered it.
 *
 * @param {string} category  e.g. 'BookCarousel'
 * @param {string} action    e.g. 'CoverClick'
 * @param {string} [label]   e.g. the carousel's analytics key
 */
export function trackEvent(category, action, label) {
    if (!window._paq) return;
    const event = ['trackEvent', category, action];
    if (label) event.push(label);
    window._paq.push(event);
}
