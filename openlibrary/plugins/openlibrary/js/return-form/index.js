/**
 * Requires confirmation whenever a patron attempts to
 * return a book.
 *
 * @param {NodeList<HTMLElement>} returnForms
 */
export function initReturnForms(returnForms) {
  for (const form of returnForms) {
    const i18nStrings = JSON.parse(form.dataset.i18n)
    form.addEventListener('submit', (event) => {
      if (!confirm(i18nStrings['confirm_return'])) {
        event.preventDefault();
      }
    })
  }
}
