import { _ } from '../i18n.js';

/**
 * Requires confirmation whenever a patron attempts to
 * return a book.
 *
 * @param {NodeList<HTMLElement>} returnForms
 */
export function initReturnForms(returnForms) {
    for (const form of returnForms) {
        form.addEventListener('submit', event => {
            if (!confirm(_('Really return this book?'))) {
                event.preventDefault();
            }
        });
    }
}
