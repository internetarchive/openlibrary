const crumbs = document.querySelectorAll('.crumb select');
const allowedKeys = new Set(['Tab', 'Enter', ' ']);
const preventedKeys = new Set(['ArrowUp', 'ArrowDown']);

// watch crumbs for changes,
// ensures it's a full value change, not a user exploring options via keyboard
crumbs.forEach(nav => {
    let ignoreChange = false;

    nav.addEventListener('change', e => {
        if (ignoreChange) return;
        // it's actually changed!
        window.location = nav.value;
    });

    nav.addEventListener('keydown', ({ key }) => {
        if (preventedKeys.has(key)) {
            ignoreChange = true;
        } else if (allowedKeys.has(key)) {
            ignoreChange = false;
        }
    });
});
