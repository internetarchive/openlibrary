/**
 * Defines functions related to the compact title component.
 * @module compact-title/index
 */

import { updateSelectedNavItem } from '../edition-nav-bar';

/**
 * Reference to the book page's main work title.
 * @type {HTMLElement}
 */
let mainTitleElem;

/**
 * Enables compact title component.
 *
 * The compact title component is initially hidden and off-screen.
 * The component's visibility is dependant on the navbar's position
 * on the page.
 *
 * This function sets up the scroll event listener and ensures that
 * the compact title is visible if the navbar is initially stickied
 * to the top of the page (this can happen on page refresh).
 *
 * @param {HTMLElement} navbar The book page navbar component
 * @param {HTMLElement} title The compact title component
 */
export function initCompactTitle(navbar, title) {
    mainTitleElem = document.querySelector('.work-title-and-author.desktop .work-title')
    // Show compact title on page reload:
    onScroll(navbar, title);
    // And update on scroll
    window.addEventListener('scroll', function() {
        onScroll(navbar, title)
    });
}

/**
 * Displays or hides compact title component based on navbar's position.
 *
 * Determines navbar's Y-axis position on the page.  Repositions compact
 * title component if navbar becomes either "stuck" or "unstuck".
 *
 * @param {HTMLElement} navbar The book page navbar component
 * @param {HTMLElement} title The compact title component
 */
function onScroll(navbar, title) {
    const compactTitleBounds = title.getBoundingClientRect()
    const navbarBounds = navbar.getBoundingClientRect()
    const mainTitleBounds = mainTitleElem.getBoundingClientRect()
    if (mainTitleBounds.bottom < navbarBounds.bottom) {  // The main title is off-screen
        if (!navbar.classList.contains('sticky--lowest')) {  // Compact title not displayed
            // Display compact title
            title.classList.remove('hidden')
            // Animate navbar
            $(navbar).addClass('nav-bar-wrapper--slidedown')
                .one('animationend', () => {
                    $(navbar).addClass('sticky--lowest')
                    $(navbar).removeClass('nav-bar-wrapper--slidedown')
                    // Ensure correct nav item is selected after compact title slides in:
                    updateSelectedNavItem()
                })
        } else {
            if (navbarBounds.top < compactTitleBounds.bottom) {  // We've scrolled to the bottom of the container, and the navbar is unstuck
                title.classList.add('hidden')
            } else {
                title.classList.remove('hidden')
            }
        }
    } else {  // At least some of the main title is below the navbar
        if (!title.classList.contains('hidden')) {
            title.classList.add('hidden')
            $(navbar).addClass('nav-bar-wrapper--slideup')
                .one('animationend', () => {
                    $(navbar).removeClass('sticky--lowest')
                    $(navbar).removeClass('nav-bar-wrapper--slideup')
                })
        }
    }
}
