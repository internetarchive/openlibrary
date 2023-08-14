import LibrarianQueue from './LibrarianQueue';

/**
 * Hydrates given librarian request queue.
 *
 * @param {HTMLElement} elem Reference to the queue's root element.
 */
export function initLibrarianQueue(elem) {
    const librarianQueue = new LibrarianQueue(elem)
    librarianQueue.initialize()
}
