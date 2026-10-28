/**
 * showToast(), the imperative way to show an <ol-toast>.
 *
 * Creates the elements rather than importing OlToast/OlToastRegion, so page
 * scripts don't bundle a second copy of Lit; ol-components.js registers both
 * elements on every page and upgrades them in place.
 */

/**
 * Show a toast in the shared fixed bottom-center stack, creating the
 * <ol-toast-region> on first use.
 *
 * The common case passes a string, set as the `message` attribute — always
 * rendered as text, never HTML — so callers can safely pass user- or
 * server-derived strings. Pass already-translated strings (e.g. from the
 * page's i18nStrings payload).
 *
 * For rich content, author the markup in a page template — where $_() i18n
 * extraction works — inside an inert <template> element, and pass that
 * element; its content is cloned into the toast's slot:
 *
 *     <template id="save-error-toast">
 *       $_("Could not save.") <a href="/help">$_("Get help")</a>
 *     </template>
 *
 *     showToast(document.querySelector('#save-error-toast'), { type: 'error' });
 *
 * Nodes built in JS (or an array of Nodes and strings) also work; strings in
 * the array become text nodes. No path ever parses a runtime string as HTML.
 *
 * @param {String|HTMLTemplateElement|Node|Array<Node|String>} content -
 *     Already-translated message text, a <template> whose content is cloned
 *     in, or rich slot content as Node(s)
 * @param {Object} [options]
 * @param {String} [options.description] - Optional secondary line (smaller, muted).
 *     Only applies when content is a string; slotted content replaces it.
 * @param {String} [options.type] - "info" | "success" | "error"
 * @param {Boolean} [options.persistent] - Stay until explicitly closed
 * @param {Number} [options.timeout] - Auto-dismiss delay in ms
 * @param {String} [options.labelClose] - Translated close button label
 * @returns {import('./OlToast.js').OlToast} The toast element (call .close() to dismiss early)
 */
export function showToast(content, options = {}) {
    let region = document.querySelector('ol-toast-region');
    if (!region) {
        region = document.createElement('ol-toast-region');
        document.body.appendChild(region);
    }
    const toast = document.createElement('ol-toast');
    if (typeof content === 'string') {
        toast.setAttribute('message', content);
    } else if (content instanceof HTMLTemplateElement) {
        // Author-written markup from the page template (i18n-extracted,
        // server-escaped); cloned so the template stays reusable
        toast.append(content.content.cloneNode(true));
    } else {
        // Node or Array<Node|String> — append() renders strings as text,
        // never HTML, and slotted children override message/description
        toast.append(...[].concat(content));
    }
    if (options.description) toast.setAttribute('description', options.description);
    if (options.type) toast.setAttribute('type', options.type);
    if (options.persistent) toast.setAttribute('persistent', '');
    if (options.timeout !== undefined) toast.setAttribute('timeout', options.timeout);
    if (options.labelClose) toast.setAttribute('label-close', options.labelClose);
    region.appendChild(toast);
    return toast;
}
