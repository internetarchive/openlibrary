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
    }

    // Add scroll listener that changes 'selected' navbar item based on page position:
    document.addEventListener('scroll', function() {
        const navbarBoundingRect = navbarElem.getBoundingClientRect()
        const selectedBoundingRect = selectedSection.getBoundingClientRect();

        // Check if navbar is not within selected element's bounds:
        if (selectedBoundingRect.bottom < navbarBoundingRect.top ||
            selectedBoundingRect.top > navbarBoundingRect.bottom) {
            for (let i = 0; i < linkedSections.length; ++i) {
                // Do not do bounds check on selected item:
                if (linkedSections[i].id !== selectedSection.id) {
                    const br = linkedSections[i].getBoundingClientRect()

                    // If navbar overlaps with an unselected target section, select that section:
                    if (br.top < navbarBoundingRect.bottom && br.bottom > navbarBoundingRect.bottom) {
                        selectElement(listItems[i], i)
                        break;
                    }
                }
            }
        }
    })
}


