import { debounce, isDisplayed } from '../nonjquery_utils'

/**
 * Adds navbar-related click and scroll listeners
 * 
 * Where relevant, logic is duplicated in both navbars for consistency if user
 * resizes browser window
 *
 * @param {HTMLUListElement} navbarElemMobile The navbar (mobile version)
 * @param {HTMLUListElement} navbarElemDesktop The navbar (desktop version)
 */
export function initNavbar(navbarElemMobile, navbarElemDesktop) {
    /**
     * Each list item in the navbars
     *
     * @type {HTMLCollection<HTMLLIElement}
     */
    const listItemsMobile = navbarElemMobile.querySelectorAll('li')
    const listItemsDesktop = navbarElemDesktop.querySelectorAll('li')

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
    for (let i = 0; i < listItemsMobile.length; ++i) {
        listItemsMobile[i].addEventListener('click', function() {
            debounce(selectElement(listItemsMobile[i], listItemsDesktop[i], i), 300, false)
        })
        listItemsDesktop[i].addEventListener('click', function() {
            debounce(selectElement(listItemsMobile[i], listItemsDesktop[i], i), 300, false)
        })

        linkedSections.push(document.querySelector(listItemsMobile[i].children[0].hash)) // hashes are the same in both mobile + desktop nav-bars
        if (listItemsMobile[i].classList.contains('selected') || listItemsDesktop[i].classList.contains('selected')) {
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
    function selectElement(selElemMobile, selElemDesktop, targetIndex) {
        // for...in was giving a strange error where i would become _i in the browser and cause an error
        for (let i = 0; i < listItemsMobile.length; i++) {
            listItemsMobile[i].classList.remove('selected')
            listItemsDesktop[i].classList.remove('selected')
        }
        selElemMobile.classList.add('selected')
        selElemDesktop.classList.add('selected')
        selectedSection = linkedSections[targetIndex]
        // Scroll to / center the item
        // Note: We don't use the browser native scrollIntoView method because
        // that method scrolls _recursively_, so it also tries to scroll the
        // body to center the element on the screen, causing weird jitters.
        const isMobile = isDisplayed(navbarElemMobile);
        let selectedElem = isMobile ? selElemMobile : selElemDesktop;
        let navbarElem = isMobile ? navbarElemMobile : navbarElemDesktop;
        navbarElem.scrollTo({
            left: selectedElem.offsetLeft - (navbarElem.clientWidth - selectedElem.offsetWidth) / 2,
        })
    }

    // Add scroll listener that changes 'selected' navbar item based on page position:
    document.addEventListener('scroll', function() {
        let i = linkedSections.length
        // Find index of lowest element on the page that is positioned below the navbar:
        let navbarElem = isDisplayed(navbarElemMobile) ? navbarElemMobile : navbarElemDesktop;
        while (--i > 0 && navbarElem.offsetTop < linkedSections[i].offsetTop) {}
        if (linkedSections[i] !== selectedSection) {
            selectElement(listItemsMobile[i], listItemsDesktop[i], i)
        }
    })
}
