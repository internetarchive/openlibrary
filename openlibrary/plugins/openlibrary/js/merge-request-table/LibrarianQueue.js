/**
 * Defines functionality related to librarian request table and header.
 *
 * Base template for the table is openlibrary/templates/merge_queue/merge_queue.html
 * @module merge-request-table/LibrarianQueue
 */

import Table from './Table'
import TableHeader from './TableHeader'

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
        this.table = new Table(librarianRequestTable.querySelector('.mr-table'))

        this.tableHeader = new TableHeader(librarianRequestTable.querySelector('.table-header'))
    }

    initialize() {
        this.table.initialize()
        this.tableHeader.initialize()
        document.addEventListener('click', (event) => this.tableHeader.closeMenusIfClickOutside(event))
    }
}
