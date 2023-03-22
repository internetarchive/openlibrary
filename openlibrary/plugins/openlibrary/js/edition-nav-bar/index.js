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
     * Reference to the selected target element.
     *
     * @type {HTMLElement}
     */
    let selectedSection

    /**
     * Flag for ignoring navbar scroll events.  We want to disable
     * scroll-aware nav item selection if navbarElem.scrollTo() was
     * recently called.
     *
     * @type {boolean}
     */
    let ignoreScrollEvent = false

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
            selectElement(listItems[i], i, true)
        })

        linkedSections.push(document.getElementById(listItems[i].children[0].hash.substring(1)))
        if (listItems[i].classList.contains('selected')) {
            selectedSection = linkedSections[linkedSections.length - 1]
        }
    }

    // Initialize mobile-only navigation arrow
    if  (navArrow) {
        navArrow.addEventListener('click', function() {
            let selectedElem

            if (selectedIndex < listItems.length - 1) {
                ++selectedIndex;
                selectedElem = listItems[selectedIndex]
                selectElement(selectedElem, selectedIndex, true)
            }
            if (selectedElem) {
                const anchor = selectedElem.querySelector('a')
                window.location = anchor.href
            }
        })
    }

    // Add scroll listener that changes 'selected' navbar item based on page position:
    document.addEventListener('scroll', function() {
        if (ignoreScrollEvent) {
            setTimeout(function() {
                ignoreScrollEvent = false
            }, 1000)
            return
        }

        const navbarHeight = navbarWrapper.getBoundingClientRect().height
        if (navbarHeight > 0) {
            let i = listItems.length

            // Find index of lowest element on the page that is positioned below the navbar:
            // while(i < linkedSections.length && navbarWrapper.offsetTop < linkedSections[i++].offsetTop) {}
            while (--i > 0 && navbarWrapper.offsetTop + navbarHeight < linkedSections[i].offsetTop) {}
            if (i < linkedSections.length) {
                if (linkedSections[i] !== selectedSection) {
                    selectElement(listItems[i], i)
                }
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
     * @param {Number} targetIndex The index of the target element
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

        ignoreScrollEvent = true
        navbarElem.scrollTo({
            left: selectedElem.offsetLeft - (navbarElem.clientWidth - selectedElem.offsetWidth) / 2,
            behavior: 'instant'
        });
    }
}
