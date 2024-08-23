/**
 * Checks the browser history length to determine
 * where to redirect the user
 *
 * @param {HTMLElement}
*/
export function initGoBackRedirect(goBackAnchor) {
    const $goBackAnchor = $(goBackAnchor)
    $goBackAnchor.on('click', () => {
        if (history.length > 2) {
            history.go(-1)
        } else {
            window.location.href='https://openlibrary.org'
        }
    })
}
