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
        glyph.setAttribute('href', revealing ? '#icon-eye' : '#icon-eye-off');
    });
}
