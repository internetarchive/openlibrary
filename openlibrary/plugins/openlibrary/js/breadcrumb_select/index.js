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

  crumbs.forEach(handleNavEvents);
}
