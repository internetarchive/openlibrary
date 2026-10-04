/**
 * Adds ability to toggle a password field's visibilty.
 *
 * @param {HTMLElement} elem Reference to affordance that toggles a password input's visibility
 */
export function initPasswordToggling(elem) {
    const passwordInput = document.querySelector('input[type=password]');

    // The affordance is a sprite icon, so swapping the glyph means repointing
    // its <use> at another symbol rather than changing an image src.
    const glyph = elem.querySelector('use');

    elem.addEventListener('click', () => {
        const revealing = passwordInput.type === 'password';
        passwordInput.type = revealing ? 'text' : 'password';
        // Keep the server-rendered sprite URL; swap only the fragment.
        const sprite = glyph.getAttribute('href').split('#')[0];
        glyph.setAttribute('href', `${sprite}#${revealing ? 'icon-eye' : 'icon-eye-off'}`);
    });
}
