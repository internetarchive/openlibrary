/**
 * Resolve `value` to a navigable URL only if it stays on the current origin
 * over http(s). A breadcrumb option value is user-influenced content, so a
 * `javascript:` (or other scheme) or cross-origin value must never reach
 * `window.location` (GHSA-6xcf). Returns the resolved same-origin URL string,
 * or null when the value is not a safe same-origin target.
 *
 * @param {string} value
 * @returns {string|null}
 */
export function safeSameOriginUrl(value) {
    try {
        const url = new URL(value, window.location.href);
        if (
            (url.protocol === 'http:' || url.protocol === 'https:') &&
            url.origin === window.location.origin
        ) {
            return url.href;
        }
    } catch {
        // value is not a parseable URL -- fall through to null
    }
    return null;
}

/**
 * Initialize the breadcrumb select elements.
 *
 * @param {NodeList<HTMLElement>} crumbs - NodeList of breadcrumb select elements.
 */
export function initBreadcrumbSelect(crumbs) {
    const allowedKeys = new Set(['Tab', 'Enter', ' ']);
    const preventedKeys = new Set(['ArrowUp', 'ArrowDown']);
    // watch crumbs for changes,
    // ensures it's a full value change, not a user exploring options via keyboard
    function handleNavEvents(nav) {
        let ignoreChange = false;

        nav.addEventListener('change', () => {
            if (ignoreChange) return;
            const target = safeSameOriginUrl(nav.value);
            if (target) {
                window.location = target;
            }
        });

        nav.addEventListener('keydown', ({ key }) => {
            if (preventedKeys.has(key)) {
                ignoreChange = true;
            } else if (allowedKeys.has(key)) {
                ignoreChange = false;
            }
        });
    }

    crumbs.forEach(handleNavEvents);
}
