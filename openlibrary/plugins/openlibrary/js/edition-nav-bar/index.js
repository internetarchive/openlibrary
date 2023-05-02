import EdtionNavBar from './EditionNavBar';

/**
 * Holds references to each book page navbar.
 * @type {Array<EditionNavBar>}
 */
const navbars = []

/**
 * Initializes and stores references to each book page navbar.
 *
 * @param {HTMLCollection<HTMLElement>} navbarWrappers Each navbar found on the book page
 */
export function initNavbars(navbarWrappers) {
    for (const wrapper of navbarWrappers) {
        const navbar = new EdtionNavBar(wrapper)
        navbars.push(navbar)
    }
}

/**
 * Updates the "selected" nav item of each navbar.
 *
 * This should be used to update the book page navbars
 * when they have been repositioned on the page by
 * something other then a scroll event (e.g. when
 * stickied to a new position).
 */
export function updateSelectedNavItem() {
    for (const navbar of navbars) {
        navbar.updateSelected()
    }
}
