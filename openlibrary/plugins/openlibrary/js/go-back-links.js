/**
 * Checks the browser history length to determine
 * where to redirect the user
 *
 * @param {NodeList<HTMLElement>} goBackLinks
*/
export function initGoBackLinks(goBackLinks) {
    for (const link of goBackLinks) {
        link.addEventListener('click', () => {
            if (history.length > 2) {
                history.go(-1)
            } else {
                window.location.href='/'
            }
        })
    }
}
