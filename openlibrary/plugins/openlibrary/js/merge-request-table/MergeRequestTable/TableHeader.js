/**
 * Defines functionality related to librarian request table header.
 *
 * @module merge-request-table/MergeRequestTable/TableHeader
 */

/**
 * Represents a header of a librarian request table.
 *
 * The header has a number of select menus, which allow one to filter by
 * a specific criterion. This class defines the functionality for these
 * menus.
 *
 * @class
 */
export default class TableHeader {
  /**
     * Sets references to many table header affordances.
     *
     * @param {HTMLElement} tableHeader
     */
  constructor(tableHeader) {
    /**
         * References to each select menu. These are always visible
         * in the header bar, and, when clicked, display a drop-down
         * menu with filtering options.
         *
         * @param {NodeList<HTMLElement>}
         */
    this.dropMenuButtons = tableHeader.querySelectorAll('.mr-dropdown')
    /**
         * References each drop-down filter option menu.
         *
         * @param {NodeList<HTMLElement>}
         */
    this.dropMenus = tableHeader.querySelectorAll('.mr-dropdown-menu')
    /**
         * References each drop-down menu "X" affordance, which closes
         * the appropriate drop-down menu.
         *
         * @param{NodeList<HTMLElement>}
         */
    this.closeButtons = tableHeader.querySelectorAll('.dropdown-close')
    /**
         * References each text input filter.
         *
         * @param{NodeList<HTMLElement>}
         */
    this.searchInputs = tableHeader.querySelectorAll('.filter')
  }

  /**
     * Hydrates the table header affordances.
     */
  initialize() {
    this.initFilters()
  }

  /**
     * Toggle a dropdown menu while closing other dropdown menus.
     *
     * @param {Event} event
     * @param {string} menuButtonId
     */
  toggleAMenuWhileClosingOthers(event, menuButtonId) {
    // prevent closing of menu on bubbling unless click menuButton itself
    if (event.target.id === menuButtonId) {
      // close other open menus, then toggle selected menu
      this.closeOtherMenus(menuButtonId)
      event.target.firstElementChild.classList.toggle('hidden')
    }
  }

  /**
     * Close dropdown menus whose menu button doesn't match a given id.
     *
     * @param {string} menuButtonId
     */
  closeOtherMenus(menuButtonId) {
    this.dropMenuButtons.forEach((menuButton) => {
      if (menuButton.id !== menuButtonId) {
        menuButton.firstElementChild.classList.add('hidden')
      }
    })
  }

  /**
     * Filters of dropdown menu items using case-insensitive string matching.
     *
     * @param {Event} event
     */
  filterMenuItems(event) {
    const input = document.getElementById(event.target.id)
    const filter = input.value.toUpperCase()
    const menu = input.closest('.mr-dropdown-menu')
    const items = menu.getElementsByClassName('dropdown-item')
    // skip first item in menu
    for (let i=1; i < items.length; i++) {
      const text = items[i].textContent
      items[i].classList.toggle('hidden', text.toUpperCase().indexOf(filter) === -1);
    }
  }

  /**
     * Close all dropdown menus when click anywhere on screen that's not part of
     * the dropdown menu; otherwise, keep dropdown menu open.
     *
     * @param {Event} event
     */
  closeMenusIfClickOutside(event) {
    const menusClicked = Array.from(this.dropMenuButtons).filter((menuButton) => {
      return menuButton.contains(event.target)
    })
    // want to preserve clicking in a menu, i.e. when filtering for users
    if (!menusClicked.length) {
      this.dropMenus.forEach((menu) => menu.classList.add('hidden'))
    }
  }

  /**
     * Initialize events for merge queue filter dropdown menu functionality.
     *
     */
  initFilters() {
    this.dropMenuButtons.forEach((menuButton) => {
      menuButton.addEventListener('click', (event) => {
        this.toggleAMenuWhileClosingOthers(event, menuButton.id)
      })
    })
    this.closeButtons.forEach((button) => {
      button.addEventListener('click', (event) => {
        event.target.closest('.mr-dropdown-menu').classList.toggle('hidden')
      })
    })
    this.searchInputs.forEach((input) => {
      input.addEventListener('keyup', (event) => this.filterMenuItems(event))
    })
  }
}
