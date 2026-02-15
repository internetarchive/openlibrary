/**
 * @param {NodeListOf<Element>} clampers
 *
 */
export function initClampers(clampers) {
    for (const clamper of clampers) {
        if (clamper.clientHeight === clamper.scrollHeight) {
            clamper.classList.remove('clamp');
        } else {

            /*
                Clamper used to collapse category list by toggling `hidden`
                style on parent element
            */

            clamper.addEventListener('click', (event) => {
                const up = event.target;

                if (event.target instanceof HTMLAnchorElement) {
                    return;
                }

                clamper.style.display = clamper.style.display === '-webkit-box' || clamper.style.display === '' ? 'unset' : '-webkit-box'

                if (up.getAttribute('data-before') === '\u25BE ') {
                    up.setAttribute('data-before', '\u25B8 ')
                } else {
                    up.setAttribute('data-before', '\u25BE ')
                }
            })
        }
    }
}
