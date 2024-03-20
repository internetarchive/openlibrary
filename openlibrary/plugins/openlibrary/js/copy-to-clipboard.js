import { FadingToast } from './Toast'

/**
 * Initializes all given "copy to clipboard" affordances.
 *
 * All "copy to clipboard" affordances will have the class `copy-to-clipboard`, and have
 * a `data-string-to-copy` and `data-i18n` attribute.  `data-i18n` will contain a JSON
 * string with a `toast` key.
 *
 * When a given affordance is clicked, the value of its `data-string-to-copy` attribute is
 * copied to the clipboard, and a toast message will be displayed to the patron.
 *
 * @param {NodeList<HTMLElement>} elements Elements that, when clicked, should copy something to the clipboard.
 */
export function initCopyToClipboardAffordances(elements) {
    for (const elem of elements) {
        const stringToCopy = elem.dataset.stringToCopy
        const i18nStrings = JSON.parse(elem.dataset.i18n)
        elem.addEventListener('click', () => {
            navigator.clipboard.writeText(stringToCopy)
            new FadingToast(i18nStrings['toast']).show()
        })
    }
}
