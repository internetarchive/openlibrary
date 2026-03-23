/**
 * Adds ability to toggle a password field's visibilty.
 *
 * @param {HTMLElement} elem Reference to affordance that toggles a password input's visibility
 */
export function initPasswordToggling(elem) {
    const passwordInput = document.querySelector('input[type=password]')

    elem.addEventListener('click', () => {
        const useEl = elem.querySelector('use')
        const svgEl = elem.querySelector('svg')
        if (passwordInput.type === 'password') {
            passwordInput.type = 'text'
            if (useEl) {
                const base = useEl.getAttribute('href').split('#')[0]
                useEl.setAttribute('href', `${base}#eye`)
                svgEl.classList.replace('icon--eye-off', 'icon--eye')
            }
        } else {
            passwordInput.type = 'password'
            if (useEl) {
                const base = useEl.getAttribute('href').split('#')[0]
                useEl.setAttribute('href', `${base}#eye-off`)
                svgEl.classList.replace('icon--eye', 'icon--eye-off')
            }
        }
    })
}
