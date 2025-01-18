/*
These functions are used by jsdef.py
They must be available in the global JS namespace
See: https://github.com/internetarchive/openlibrary/pull/9180#issuecomment-2107911798
*/

// closes active popup
export function closePopup() {
    // Note we don't import colorbox here, since it's on the parent
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

// Function to add or update multiple query parameters
export function updateURLParameters(params) {
    // Get the current URL
    const url = new URL(window.location.href);

    // Iterate over the params object and update/add each parameter
    for (const key in params) {
        if (params.hasOwnProperty(key)) {
            url.searchParams.set(key, params[key]);
        }
    }

    // Use history.pushState to update the URL without reloading
    window.history.pushState({ path: url.href }, '', url.href);
}

/**
 * Remove leading/trailing empty space on field deselect.
 * @param string a value for document.querySelectorAll()
 */
export function trimInputValues(param) {
    const inputs = document.querySelectorAll(param);
    inputs.forEach(input => {
        input.addEventListener('blur', function() {
            this.value = this.value.trim();
        });
    });
}
