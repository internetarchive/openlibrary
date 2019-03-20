/**
 * Load non-critical CSS file via JavaScript
 * e.g. CSS that depends on JavaScript to work.
 * @param {String} href path to style resource
 */
var loaded = {};
export default function loadStyle(href) {
    // Should only be possible to load once
    if (!loaded[href]) {
        var el = document.createElement('link');
        el.rel = 'stylesheet';
        el.href = href;
        document.head.appendChild(el);
        loaded[href] = true;
    }
}
