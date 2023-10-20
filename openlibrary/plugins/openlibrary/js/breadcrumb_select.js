const crumbs = document.querySelectorAll('.crumb select');
const allowedKeys = new Set(['Tab', 'Enter', ' ']);
const preventedKeys = new Set(['ArrowUp', 'ArrowDown']);

// Define a function that handles the events for each nav element
function handleNavEvents(nav) {
    let ignoreChange = false;

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

// Attach the event handlers to each nav element
crumbs.forEach(handleNavEvents);
