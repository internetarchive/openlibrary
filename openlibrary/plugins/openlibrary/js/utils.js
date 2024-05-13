/*
These functions are used by jsdef.py
They must be available in the global JS namespace
See: https://github.com/internetarchive/openlibrary/pull/9180#issuecomment-2107911798
*/

// closes active popup
export function closePopup() {
    parent.jQuery.fn.colorbox.close();
}

// used in templates/admin/imports.html
export function truncate(text, limit) {
    if (text.length > limit) {
        return `${text.substr(0, limit)}...`;
    } else {
        return text;
    }
}

// used in openlibrary/templates/books/edit/excerpts.html
export function cond(predicate, true_value, false_value) {
    if (predicate) {
        return true_value;
    }
    else {
        return false_value;
    }
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
