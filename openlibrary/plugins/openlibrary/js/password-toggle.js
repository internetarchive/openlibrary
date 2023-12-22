/**
 * Adds ability to toggle a password field's visibilty.
 *
 * @param {HTMLElement} elem Reference to affordance that toggles a password input's visibility
 */
export function initPasswordToggling(elem) {
    const i18nStrings = JSON.parse(elem.dataset.i18n)
    const passwordInput = document.querySelector('input[type=password]')

    elem.addEventListener('click', () => {
        if (passwordInput.type === 'password') {
            passwordInput.type = 'text'
            elem.textContent = i18nStrings['hide_password']
        } else {
            passwordInput.type = 'password'
            elem.textContent = i18nStrings['show_password']
        }
    })
}
