/**
 * Defines functions related to the compact title component.
 * @module compact-title/index
 */

/**
 * True if compact title component is visible on screen.
 * @type {boolean}
 */
let isTitleVisible = false

/**
 * Navbar is "stuck" when it reaches this position on the Y-axis.
 */
const navbarStickyHeight = 35;

/**
 * Offscreen "top" value of compact title.
 */
const offscreenY = '-45px';

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
    // Show compact title on page reload:
    if (navbar.getBoundingClientRect().top === navbarStickyHeight) {
        title.classList.remove('hidden')
        title.style.top = '0px'
        isTitleVisible = true
    }

    window.addEventListener('scroll', function() {
        onScroll(navbar, title)
    })
}

/**
 * Displays or hides compact title component based on navbar's position.
 *
 * Determines navbar's Y-axis position on the page.  Repositions compact
 * title component if navbar becomes either "stuck" or "unstuck".
 *
 * @param {HTMLElement} navbar The book page navbar component
 * @param {HTMLELement} title The compact title component
 */
function onScroll(navbar, title) {
    const navbarY = navbar.getBoundingClientRect().top;

    if (navbarY === navbarStickyHeight) {
        if (title.classList.contains('hidden')) {
            title.classList.remove('hidden')
        }
        if (!isTitleVisible) {
            isTitleVisible = true
            title.style.top = '0px'
            title.classList.remove('compact-title--slideout')
            title.classList.add('compact-title--slidein')
        }
    } else {
        if (isTitleVisible) {
            isTitleVisible = false
            title.style.top = offscreenY
            title.classList.remove('compact-title--slidein')
            title.classList.add('compact-title--slideout')
            $(title).one('animationend', () => title.classList.add('hidden'))
        }
    }
}
