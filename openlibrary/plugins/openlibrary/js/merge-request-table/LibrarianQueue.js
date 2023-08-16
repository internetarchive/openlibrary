/**
 * Defines functionality related to librarian request table and header.
 *
 * Base template for the table is openlibrary/templates/merge_queue/merge_queue.html
 * @module merge-request-table/LibrarianQueue
 */

import TableHeader from './LibrarianQueue/TableHeader'
import { setI18nStrings, TableRow } from './LibrarianQueue/TableRow'

/**
 * Class representing the librarian request table.
 *
 * @class
 */
export default class LibrarianQueue {

    /**
     * Creates references to the table and its header and hydrates each.
     *
     * @param {HTMLElement} librarianRequestTable
     */
    constructor(librarianRequestTable) {
        /**
         * The `username` of the authenticated patron, or '' if logged out.
         *
         * @param {string}
         */
        this.username = librarianRequestTable.dataset.username

        const localizedStrings = JSON.parse(librarianRequestTable.dataset.i18n)
        setI18nStrings(localizedStrings)

        /**
         * Reference to this table's header.
         *
         * @param {HTMLElement}
         */
        this.tableHeader = new TableHeader(librarianRequestTable.querySelector('.table-header'))

        /**
         * References to each row in the table.
         *
         * @param {Array<TableRow>}
         */
        this.tableRows = []
        const rowElements = librarianRequestTable.querySelectorAll('.mr-table-row')
        for (const elem of rowElements) {
            this.tableRows.push(new TableRow(elem, this.username))
        }
    }

    /**
     * Hydrates the librarian request table.
     */
    initialize() {
        this.tableHeader.initialize()
        document.addEventListener('click', (event) => this.tableHeader.closeMenusIfClickOutside(event))
        this.tableRows.forEach(elem => elem.initialize())
    }
}
