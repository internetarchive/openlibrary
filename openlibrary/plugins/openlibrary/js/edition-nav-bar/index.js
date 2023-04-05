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
     * Right navigation arrow.  This will only be present in
     * mobile views.
     *
     * @type {HTMLElement}
     */
    const navArrow = navbarWrapper.querySelector('.nav-arrow')

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
            selectElement(listItems[i])
        })

        linkedSections.push(document.getElementById(listItems[i].children[0].hash.substring(1)))
        if (listItems[i].classList.contains('selected')) {
            selectedIndex = i
        }
    }

    // Initialize mobile-only navigation arrow
    if (navArrow) {
        navArrow.addEventListener('click', function() {
            if (selectedIndex < listItems.length - 1) {
                ++selectedIndex;
                listItems[selectedIndex].children[0].click()
            }
        })
    }

    // Add scroll listener that changes 'selected' navbar item based on page position:
    document.addEventListener('scroll', function() {

        const navbarHeight = navbarWrapper.getBoundingClientRect().height
        if (navbarHeight > 0) {
            let i = listItems.length
            while (--i > 0 && navbarWrapper.offsetTop + navbarHeight < linkedSections[i].offsetTop) {}
            if (i !== selectedIndex) {
                selectedIndex = i
                selectElement(listItems[i])
            }
        }
    })

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
        scrollNavbar(selectedElem)
    }

    /**
     * Centers given nav item in the navbar, if navbar has overflow (mobile views)
     *
     * @param {HTMLElement} selectedItem Newly selected nav item
     */
    function scrollNavbar(selectedItem) {
        // Note: We don't use the browser native scrollIntoView method because
        // that method scrolls _recursively_, so it also tries to scroll the
        // body to center the element on the screen, causing weird jitters.

        navbarElem.scrollTo({
            left: selectedItem.offsetLeft - (navbarElem.clientWidth - selectedItem.offsetWidth) / 2,
            behavior: 'instant'})
    }
}
