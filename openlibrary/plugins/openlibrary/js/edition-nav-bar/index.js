import { debounce, isDisplayed } from "../nonjquery_utils"

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
     * The scroll containers that contain the navbar links
     *
     * @type {NodeList<HTMLUListElement}
     */
    const scrollContainerMobile = navbarElemMobile.querySelector("ul");
    const scrollContainerDesktop = navbarElemMobile.querySelector("ul");

    /**
     * Each list item in the navbars
     *
     * @type {NodeList<HTMLLIElement>}
     */
    const listItemsMobile = navbarElemMobile.querySelectorAll('li')
    const listItemsDesktop = navbarElemDesktop.querySelectorAll('li')

    /**
     * Scroll buttons (only found on mobile navbar)
     *
     * @type {HTMLButtonElement}
     */
    const scrollLeftBtn = navbarElemMobile.querySelector("button.scroll-left")
    const scrollRightBtn = navbarElemMobile.querySelector("button.scroll-right")

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
    scrollLeftBtn.addEventListener('click', () => {
        setScrollButtonsVisibility({ left: false, right: true })
        scrollContainerMobile.scrollTo({ left: 0 })
    })
    scrollRightBtn.addEventListener('click', () => {
        setScrollButtonsVisibility({ left: true, right: false })
        scrollContainerMobile.scrollTo({ left: scrollContainerMobile.scrollLeftMax })
    })

    // Add scroll listener that changes 'selected' navbar item based on page position:
    document.addEventListener('scroll', handleScroll)

    // Scroll listener for adding and removing scroll buttons based on whether they're
    // needed or not
    scrollContainerMobile.addEventListener('scroll', function() {
        if (scrollContainerMobile.scrollLeft === 0) {
            setScrollButtonsVisibility({left: false, right: true})
        } else if (scrollContainerMobile.scrollLeft === scrollContainerMobile.scrollLeftMax) {
            setScrollButtonsVisibility({left: true, right: false})
        } else {
            setScrollButtonsVisibility({left: true, right: true})
        }
    })

    // Resize listener for ensuring scroll buttons are only visible when they're needed
    window.addEventListener("resize", debounce(handleResize, 250, false))
    handleResize() // init the buttons based on the page's starting condition

    /**
     * Adds 'selected' class to the given elements in both mobile and desktop navbars.
     *
     * Removes 'selected' class from all navbar links, then adds
     * 'selected' to the newly selected link in both mobile + desktop navbars.
     *
     * Stores reference to the selected target.
     *
     * @param {HTMLLIElement} selectedElem Element corresponding to the 'selected' navbar item.
     * @param {Number} targetIndex The index
     */
    function selectElement(selElemMobile, selElemDesktop, targetIndex) {
        for (let i = 0; i < listItemsMobile.length; i++) {
            listItemsMobile[i].classList.remove('selected')
            listItemsDesktop[i].classList.remove('selected')
        }
        selElemMobile.classList.add('selected')
        selElemDesktop.classList.add('selected')
        selectedSection = linkedSections[targetIndex]

        const isMobile = isDisplayed(scrollContainerMobile)
        let selectedElem = isMobile ? selElemMobile : selElemDesktop
        let scrollContainer = isMobile ? scrollContainerMobile : scrollContainerDesktop
        // Removing and then re-adding the event listener is necessary to avoid
        // a bug where scrolling to the selected element would cause this
        // selectElement function to trigger again (see handleScroll function),
        // thereby causing the selected element to be set incorrectly
        document.removeEventListener('scroll', handleScroll)
        // Scroll to / center the item
        // Note: We don't use the browser native scrollIntoView method because
        // that method scrolls _recursively_, so it also tries to scroll the
        // body to center the element on the screen, causing weird jitters.
        scrollContainer.scrollTo({
            left: selectedElem.offsetLeft - (navbarElemMobile.clientWidth - selectedElem.offsetWidth) / 2,
        })
        setTimeout(() => document.addEventListener('scroll', handleScroll), 1000) // 1000ms is a lot but
        // it can take that long to go from top to bottom of page
    }

    // Functions
    function handleScroll() {
        let i = linkedSections.length
        // Find index of lowest element on the page that is positioned below the navbar:
        let navbarElem = isDisplayed(navbarElemMobile) ? navbarElemMobile : navbarElemDesktop
        while (--i > 0 && navbarElem.offsetTop < linkedSections[i].offsetTop) {}

        if (linkedSections[i] !== selectedSection) {
            selectElement(listItemsMobile[i], listItemsDesktop[i], i)
        }
    }
    function handleResize() {
        if (scrollContainerMobile.scrollLeftMax <= 10) { // 10 is a magic number
            setScrollButtonsVisibility({left: false, right: false})
        } else {
            setScrollButtonsVisibility({left: false, right: true})
        }
    }
    function setScrollButtonsVisibility({left, right}) {
        if (left === true) {
            scrollLeftBtn.style.visibility = "visible"
        } else if (left === false) {
            scrollLeftBtn.style.visibility = "hidden"
        }

        if (right === true) {
            scrollRightBtn.style.visibility = "visible"
        } else if (right === false) {
            scrollRightBtn.style.visibility = "hidden"
        }
    }
}
