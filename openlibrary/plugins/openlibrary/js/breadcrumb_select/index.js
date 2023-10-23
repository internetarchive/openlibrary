/**
 * Initialize the breadcrumb select elements.
 *
 * @param {NodeList<HTMLElement>} navElements - NodeList of breadcrumb select elements.
 */
export function initBreadcrumbSelect(navElements) {
    const allowedKeys = new Set(['Tab', 'Enter', ' ']);
    const preventedKeys = new Set(['ArrowUp', 'ArrowDown']);

    function handleNavEvents(nav) {
        let ignoreChange = false;
        console.log("In bread crumbs!");
        nav.addEventListener('change', () => {
            if (ignoreChange) return;
            // It's actually changed!
            window.location = nav.value;
        });

        nav.addEventListener('keydown', ({ key }) => {
            if (preventedKeys.has(key)) {
                ignoreChange = true;
            } else if (allowedKeys.has(key)) {
                ignoreChange = false;
            }
        });
    }

    navElements.forEach(handleNavEvents);
}
