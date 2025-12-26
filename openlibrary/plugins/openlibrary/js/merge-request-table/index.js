import MergeRequestTable from './MergeRequestTable';
import { initMergeRequestEditPage } from './MergeRequestEditPage'

/**
 * Hydrates given librarian request queue.
 *
 * @param {HTMLElement} elem Reference to the queue's root element.
 */
export function initLibrarianQueue(elem) {
    const librarianQueue = new MergeRequestTable(elem)
    librarianQueue.initialize()
}
