/**
 * Defines functionality related to the book page navbar.
 * @module edition-nav-bar/EditionNavBar
 */
export default class EdtionNavBar {
    /**
     * Adds functionality to the given navbar element.
     *
     * @param {HTMLElement} navbarWrapper
     */
    constructor(navbarWrapper) {
        /**
         * Reference to the parent element of the navbar.
         * @type {HTMLElement}
         */
        this.navbarWrapper = navbarWrapper
        /**
         * The navbar
         * @type {HTMLElement}
         */
        this.navbarElem = navbarWrapper.querySelector('.work-menu')
        /**
         * The mobile-only navigation arrow. Not guaranteed to exist.
         * @type {HTMLElement|null}
         */
        this.navArrow = navbarWrapper.querySelector('.nav-arrow')
        /**
         * References each nav item in this navbar.
         * @type {Array<HTMLLIElement>}
         */
        this.navItems = Array.from(this.navbarElem.querySelectorAll('li'))
        /**
         * Index of the currently selected nav item.
         * @type {number}
         */
        this.selectedIndex = 0
        /**
         * The nav items' target anchor elements.
         * @type {HTMLAnchorElement}
         */
        this.targetAnchors = []

        this.initialize()
    }

    /**
     * Adds the necessary event handlers to the navbar.
     */
    initialize() {
        // Add click listeners to navbar items:
        for (let i = 0; i < this.navItems.length; ++i) {
            this.navItems[i].addEventListener('click', () => {
                this.selectedIndex = i
                this.selectElement(this.navItems[i])
            })

            // Add this nav item's target anchor to array:
            this.targetAnchors.push(document.getElementById(this.navItems[i].children[0].hash.substring(1)))

            // Set selectedIndex to the correct value:
            if (this.navItems[i].classList.contains('selected')) {
                this.selectedIndex = i
            }
        }

        // Add click listener to mobile-only navigation arrow:
        if (this.navArrow) {
            this.navArrow.addEventListener('click', () => {
                if (this.selectedIndex < this.navItems.length - 1) {
                    // Simulate click on the next nav item:
                    ++this.selectedIndex
                    this.navItems[this.selectedIndex].children[0].click()
                }
            })
        }

        // Add scroll listener for position-aware nav item selection
        document.addEventListener('scroll', () => {
            this.updateSelected()
        })
    }

    /**
     * Determines this navbar's position on the page and updates the selected
     * nav item.
     */
    updateSelected() {
        const navbarHeight = this.navbarWrapper.getBoundingClientRect().height
        if (navbarHeight > 0) {
            let i = this.navItems.length
            while (--i > 0 && this.navbarWrapper.offsetTop + navbarHeight < this.targetAnchors[i].offsetTop) {}
            if (i !== this.selectedIndex) {
                this.selectedIndex = i
                this.selectElement(this.navItems[i])
            }
        }
    }

    /**
     * Centers given nav item in the navbar, if navbar has overflow (mobile views)
     *
     * @param {HTMLElement} selectedItem Newly selected nav item
     */
    scrollNavbar(selectedItem) {
        // Note: We don't use the browser native scrollIntoView method because
        // that method scrolls _recursively_, so it also tries to scroll the
        // body to center the element on the screen, causing weird jitters.

        this.navbarElem.scrollTo({
            left: selectedItem.offsetLeft - (this.navbarElem.clientWidth - selectedItem.offsetWidth) / 2,
            behavior: 'instant'})
    }

    /**
     * Adds 'selected' class to the given element.
     *
     * Removes 'selected' class from all navbar links, then adds
     * 'selected' to the newly selected link.
     *
     * @param {HTMLLIElement} selectedElem Element corresponding to the 'selected' navbar item.
     */
    selectElement(selectedElem) {
        for (const li of this.navItems) {
            li.classList.remove('selected')
        }
        selectedElem.classList.add('selected')
        this.scrollNavbar(selectedElem)
    }
}
