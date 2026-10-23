// @ts-check

/**
 * Shows an <ol-toast> in the shared fixed bottom-center stack.
 *
 * Page-JS counterpart of showToast() in components/lit/OlToastRegion.js.
 * Importing that module from this bundle would re-run customElements.define()
 * and pull in a second copy of Lit, so the elements are created by tag name
 * instead; ol-components.js, loaded on every page, upgrades them in place.
 *
 * The message is set as an attribute, so it always renders as text, never HTML.
 *
 * @param {string} message Already-translated message text.
 * @param {object} [options]
 * @param {'info'|'success'|'error'} [options.type] Defaults to 'info'.
 * @param {boolean} [options.persistent] Stay until the patron closes it.
 * @param {number} [options.timeout] Auto-dismiss delay in ms.
 * @returns {HTMLElement} The toast element.
 */
export function showToast(message, { type, persistent, timeout } = {}) {
    let region = document.querySelector('ol-toast-region');
    if (!region) {
        region = document.createElement('ol-toast-region');
        document.body.appendChild(region);
    }
    const toast = document.createElement('ol-toast');
    toast.setAttribute('message', message);
    if (type) toast.setAttribute('type', type);
    if (persistent) toast.setAttribute('persistent', '');
    if (timeout !== undefined) toast.setAttribute('timeout', String(timeout));
    region.appendChild(toast);
    return toast;
}
