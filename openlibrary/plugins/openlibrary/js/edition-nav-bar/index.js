import { debounce } from '../nonjquery_utils'

/**
 * Adds navbar-related click and scroll listeners
 *
 * @param {HTMLUListElement} navbarElem The navbar
 */
export function initNavbar(navbarElem) {
    /**
     * Each list item in the navbar.
     *
     * @type {HTMLCollection<HTMLLIElement}
     */
    const listItems = navbarElem.querySelectorAll('li');

    /**
     * The targets of the navbar links.
     *
     * Elements are ordered from highest position on the page to lowest.
     *
     * @type {Array<HTMLElement>}
     */
    const linkedSections = []

    /**
     * Reference to the selected target element.
     *
     * @type {HTMLElement}
     */
    let selectedSection

    // Add click listeners
    for (let i = 0; i < listItems.length; ++i) {
        const index = i;
        listItems[i].addEventListener('click', function() {
            debounce(selectElement(listItems[i], index), 300, false)
        })

        linkedSections.push(document.querySelector(listItems[i].children[0].hash))
        if (listItems[i].classList.contains('selected')) {
            selectedSection = linkedSections[linkedSections.length - 1]
        }
    }

    /**
     * Adds 'selected' class to the given element.
     *
     * Removes 'selected' class from all navbar links, then adds
     * 'selected' to the newly selected link.
     *
     * Stores reference to the selected target.
     *
     * @param {HTMLLIElement} selectedElem Element corresponding to the 'selected' navbar item.
     * @param {Number} targetIndex The index
     */
    function selectElement(selectedElem, targetIndex) {
        for (const li of listItems) {
            li.classList.remove('selected')
        }
        selectedElem.classList.add('selected')
        selectedSection = linkedSections[targetIndex];
        // Scroll to / center the item
        // Note: We don't use the browser native scrollIntoView method because
        // that method scrolls _recursively_, so it also tries to scroll the
        // body to center the element on the screen, causing weird jitters.
        navbarElem.scrollTo({
            left: selectedElem.offsetLeft - (navbarElem.clientWidth - selectedElem.offsetWidth) / 2,
        });
    }

    // Add scroll listener that changes 'selected' navbar item based on page position:
    document.addEventListener('scroll', function() {
        let i = linkedSections.length
        // Find index of lowest element on the page that is positioned below the navbar:
        while (--i > 0 && navbarElem.offsetTop < linkedSections[i].offsetTop) {}
        if (linkedSections[i] !== selectedSection) {
            selectElement(listItems[i], i)
        }
    })
}


