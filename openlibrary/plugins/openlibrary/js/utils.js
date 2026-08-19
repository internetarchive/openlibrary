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
 * On failure, `elem`'s loading indicator(s) (`.loadingIndicator`) are hidden
 * and its pre-rendered `.async-partial-retry` prompt is shown instead (see
 * e.g. RawQueryCarousel.html/PublishingHistory.html for the expected markup).
 * Clicking retry restores the loading indicator(s) and re-attempts the fetch.
 *
 * @param {HTMLElement} elem Root element of an async-loaded partial component
 * @param {string} component Partial component name (e.g. 'SubjectRelated')
 * @param {(newElem: HTMLElement) => void} [onSwap] Called every time `elem`
 *   is successfully replaced with fetched markup -- including on a later
 *   retry, unlike the returned promise below.
 * @returns {Promise<HTMLElement | null>} The element that replaced `elem` on
 *   the first attempt, or null if that attempt failed
 */
export async function fetchAndSwap(elem, component, onSwap) {
    if (elem.dataset.asyncLoad !== 'true') {
        return null;
    }
    const key = JSON.parse(elem.dataset.key);
    await whenVisible(elem);
    return attemptFetchAndSwap(elem, component, key, onSwap);
}

/**
 * @param {HTMLElement} elem Element to replace with the fetched markup (or,
 *   on failure, show a retry prompt inside)
 * @param {string} component
 * @param {string} key
 * @param {(newElem: HTMLElement) => void} [onSwap]
 * @returns {Promise<HTMLElement | null>}
 */
async function attemptFetchAndSwap(elem, component, key, onSwap) {
    try {
        const resp = await fetch(buildPartialsUrl(component, {key}));
        if (!resp.ok) {
            throw new Error(`Failed to fetch ${component} partial. Status code: ${resp.status}`);
        }
        const data = await resp.json();
        const newElem = createElementFromMarkup(data.partials);
        elem.replaceWith(newElem);
        onSwap?.(newElem);
        return newElem;
    } catch {
        showRetryPrompt(elem, () => attemptFetchAndSwap(elem, component, key, onSwap));
        return null;
    }
}

/**
 * Hides `elem`'s loading indicator(s) and shows its pre-rendered retry
 * prompt. Clicking retry restores the loading indicator(s) and calls
 * `onRetry`.
 *
 * @param {HTMLElement} elem
 * @param {() => void} onRetry
 */
function showRetryPrompt(elem, onRetry) {
    const loadingIndicators = elem.querySelectorAll('.loadingIndicator');
    const retryPrompt = elem.querySelector('.async-partial-retry');

    loadingIndicators.forEach(indicator => indicator.classList.add('hidden'));
    retryPrompt.classList.remove('hidden');

    retryPrompt.querySelector('.retry-btn').addEventListener('click', function onClick(e) {
        e.preventDefault();
        e.currentTarget.removeEventListener('click', onClick);
        retryPrompt.classList.add('hidden');
        loadingIndicators.forEach(indicator => indicator.classList.remove('hidden'));
        onRetry();
    });
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
