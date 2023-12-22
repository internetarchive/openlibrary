/**
 * Adds ability to toggle a password field's visibilty.
 *
 * @param {HTMLElement} elem Reference to affordance that toggles a password input's visibility
 */
export function initPasswordToggling(elem) {
    const passwordInput = document.querySelector('input[type=password]')

    elem.addEventListener('click', () => {
        if (passwordInput.type === 'password') {
            passwordInput.type = 'text'
            elem.textContent = 'Hide password'
        } else {
            passwordInput.type = 'password'
            elem.textContent = 'Show password'
        }
    })
}
