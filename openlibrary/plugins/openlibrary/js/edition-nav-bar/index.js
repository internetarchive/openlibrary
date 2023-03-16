import { debounce } from '../nonjquery_utils'

/**
 * Adds navbar-related click and scroll listeners
 *
 * @param {HTMLElement} navbarWrapper The wrapper that contains the navbar
 */
export function initNavbar(navbarWrapper) {
    /**
     * The book page navbar
     *
     * @type {HTMLElement}
     */
    const navbarElem = navbarWrapper.querySelector('.work-menu')
    /**
     * Left and right navigation arrows.  These will only be present in
     * mobile views.
     *
     * @type {HTMLCollection<HTMLElement>}
     */
    const navArrows = navbarWrapper.querySelectorAll('.nav-arrow')

    /**
     * Each list item in the navbar.
     *
     * @type {HTMLCollection<HTMLLIElement}
     */
    const listItems = Array.from(navbarElem.querySelectorAll('li'));

    /**
     * The index of the currently selected item in the `listItems` array.
     *
     * @type {number}
     */
    let selectedIndex = 0;

    /**
     * The targets of the navbar links.
     *
     * Elements are ordered from highest position on the page to lowest.
     *
     * @type {Array<HTMLElement>}
     */
    const linkedSections = []

    // Add click listeners to navbar items
    for (let i = 0; i < listItems.length; ++i) {
        listItems[i].addEventListener('click', function() {
            selectedIndex = i
            debounce(selectElement(listItems[i]), 300, false)
        })

        linkedSections.push(document.querySelector(listItems[i].children[0].hash))
    }

    // Initialize mobile-only navigation arrows
    for (const arrow of navArrows) {
        const decrementIndex = arrow.classList.contains('nav-arrow--left')

        arrow.addEventListener('click', function() {
            let selectedElem
            if (decrementIndex) {
                if (selectedIndex > 0) {
                    --selectedIndex
                    selectedElem = listItems[selectedIndex]
                    selectElement(selectedElem)
                }
            } else {
                if (selectedIndex < listItems.length - 1) {
                    ++selectedIndex;
                    selectedElem = listItems[selectedIndex]
                    selectElement(selectedElem)
                }
            }
            if (selectedElem) {
                const anchor = selectedElem.querySelector('a')
                window.location = anchor.href
            }
        })
    }

    /**
     * Adds 'selected' class to the given element.
     *
     * Removes 'selected' class from all navbar links, then adds
     * 'selected' to the newly selected link.
     *
     * @param {HTMLLIElement} selectedElem Element corresponding to the 'selected' navbar item.
     */
    function selectElement(selectedElem) {
        for (const li of listItems) {
            li.classList.remove('selected')
        }
        selectedElem.classList.add('selected')

        // Scroll to / center the item
        // Note: We don't use the browser native scrollIntoView method because
        // that method scrolls _recursively_, so it also tries to scroll the
        // body to center the element on the screen, causing weird jitters.
        navbarElem.scrollTo({
            left: selectedElem.offsetLeft - (navbarElem.clientWidth - selectedElem.offsetWidth) / 2,
            behavior: 'instant'
        });
    }
}
