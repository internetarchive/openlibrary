// closes active popup
export function closePopup() {
    parent.jQuery.fn.colorbox.close();
}

/**
 * Removes children of each given element.
 *
 * @param  {...HTMLElement} elements
 */
export function removeChildren(...elements) {
    for (const elem of elements) {
        if (elem) {
            while (elem.firstChild) {
                elem.removeChild(elem.firstChild)
            }
        }
    }
}
