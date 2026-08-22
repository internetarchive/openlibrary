/**
 * Event reporting for the book components.
 *
 * Matomo's click trigger matches on `data-ol-link-track` attributes, which it
 * cannot see inside a shadow root — events retarget to the host on the way out.
 * So we push onto Matomo's `_paq` queue directly, the same path that trigger
 * ends up using. Mirrors `js/ol.analytics.js`'s `trackEvent`; that module lives
 * in the webpack bundle, which this one cannot import.
 *
 * Guarded so a blocked or absent analytics script can never break the
 * interaction that reported it.
 *
 * @param {string} category e.g. 'ReadingLog'
 * @param {string} action   e.g. 'WantToRead'
 * @param {string} [label]
 */
export function trackEvent(category, action, label) {
    if (!window._paq) return;
    const event = ['trackEvent', category, action];
    if (label) event.push(label);
    window._paq.push(event);
}
