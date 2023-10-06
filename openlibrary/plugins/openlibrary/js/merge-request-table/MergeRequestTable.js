/**
 * Defines functionality related to librarian request table and header.
 *
 * Base template for the table is openlibrary/templates/merge_queue/merge_queue.html
 * @module merge-request-table/MergeRequestTable
 */

import TableHeader from './MergeRequestTable/TableHeader'
import { setI18nStrings, TableRow } from './MergeRequestTable/TableRow'

/**
 * Class representing the librarian request table.
 *
 * @class
 */
export default class MergeRequestTable {

    /**
     * Creates references to the table and its header and hydrates each.
     *
     * @param {HTMLElement} mergeRequestTable
     */
    constructor(mergeRequestTable) {
        /**
         * The `username` of the authenticated patron, or '' if logged out.
         *
         * @param {string}
         */
        this.username = mergeRequestTable.dataset.username

        const localizedStrings = JSON.parse(mergeRequestTable.dataset.i18n)
        setI18nStrings(localizedStrings)

        /**
         * Reference to this table's header.
         *
         * @param {HTMLElement}
         */
        this.tableHeader = new TableHeader(mergeRequestTable.querySelector('.table-header'))

        /**
         * References to each row in the table.
         *
         * @param {Array<TableRow>}
         */
        this.tableRows = []
        const rowElements = mergeRequestTable.querySelectorAll('.mr-table-row')
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
