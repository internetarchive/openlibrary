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
                elem.removeChild(elem.firstChild);
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
        if (Object.prototype.hasOwnProperty.call(params, key)) {
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

export function buildPartialsUrl(component, params = {}) {
    const curUrl = new URL(window.location.href);
    const url = new URL(`${location.origin}/partials/${component}.json`);

    if (curUrl.searchParams.has('lang')) {
        url.searchParams.set('lang', curUrl.searchParams.get('lang'));
    }

    for (const key in params) {
        url.searchParams.set(key, params[key]);
    }

    return url;
}

/**
 * Returns an `HTMLElement` that was created using the given `markup`.
 *
 * `markup` is expected to be well-formed, and only have a single root
 * element.
 *
 * @param {string} markup HTML markup for a single element
 * @returns {HTMLElement}
 */
export function createElementFromMarkup(markup) {
    const template = document.createElement('template');
    template.innerHTML = markup;
    return template.content.children[0];
}

/**
 * Waits until the given element is visible in the viewport, then resolves.
 *
 * @param {HTMLElement} elem
 * @param {IntersectionObserverInit} options
 * @returns {Promise<void>}
 */
export async function whenVisible(elem, options = {}) {
    return new Promise((resolve) => {
        const intersectionObserver = new IntersectionObserver(
            (entries, observer) => {
                entries.forEach(entry => {
                    if (!entry.isIntersecting) {
                        return;
                    }

                    // Stop observing once the element is visible
                    observer.unobserve(entry.target);
                    observer.disconnect();
                    resolve();
                });
            },
            Object.assign({
                root: null,
                rootMargin: '200px',
                threshold: 0
            }, options)
        );

        intersectionObserver.observe(elem);
    });
}

/**
 * Once `elem` is visible, fetches `component`'s real markup (keyed off
 * `elem.dataset.key`) and replaces `elem` with it.
 *
 * @param {HTMLElement} elem Root element of an async-loaded partial component
 * @param {string} component Partial component name (e.g. 'SubjectRelated')
 * @returns {Promise<HTMLElement | null>} The element that replaced `elem`, or null on failure
 */
export async function fetchAndSwap(elem, component) {
    if (elem.dataset.asyncLoad !== 'true') {
        return null;
    }
    const key = JSON.parse(elem.dataset.key);
    await whenVisible(elem);

    try {
        const resp = await fetch(buildPartialsUrl(component, {key}));
        if (!resp.ok) {
            throw new Error(`Failed to fetch ${component} partial. Status code: ${resp.status}`);
        }
        const data = await resp.json();
        const newElem = createElementFromMarkup(data.partials);
        elem.replaceWith(newElem);
        return newElem;
    } catch {
        // XXX : Handle case where `/partials` response is not `2XX` here
        return null;
    }
}

export function queueAction(actionName, itemName, targetUrl, itemType) {
    const data = {
        name: itemName,
        url: targetUrl,
        action: actionName,
        type: itemType || 'item'
    };

    const cookieValue = encodeURIComponent(JSON.stringify(data));
    document.cookie = `pending_action=${cookieValue}; path=/; max-age=129600; samesite=lax`;
}
