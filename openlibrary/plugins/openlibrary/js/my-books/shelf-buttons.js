/**
 * Owns book state for a page of `<ol-shelf-button>`s.
 *
 * The buttons are stateless by contract: they never write their own `shelf`,
 * `rating` or read date, they emit `ol-book-state-change` — optimistically on
 * click, and again with the old value if the write fails — and the surface
 * applies it. Server-rendering the attributes only supplies the opening state,
 * so without this the label stops matching the server after the first change.
 *
 * Applying it centrally is also what keeps two buttons for the same work in
 * step, including the finish date the popover shows on its Already Read row.
 *
 * @module my-books/shelf-buttons
 */

/** "/works/OL1W" (or "OL1W") → "OL1W". */
function olid(key) {
    return (key || '').split('/').pop();
}

/**
 * @param {NodeList|Array<HTMLElement>} shelfButtons
 */
export function initShelfButtons(shelfButtons) {
    /** @type {Map<string, HTMLElement[]>} */
    const buttonsByWork = new Map();

    for (const button of shelfButtons) {
        const workOlid = olid(button.getAttribute('work-key'));
        if (!workOlid) continue;

        if (!buttonsByWork.has(workOlid)) buttonsByWork.set(workOlid, []);
        buttonsByWork.get(workOlid).push(button);
    }

    if (!buttonsByWork.size) return;

    /** @param {string} key @param {(button: HTMLElement) => void} apply */
    function forWork(key, apply) {
        for (const button of buttonsByWork.get(olid(key)) || []) apply(button);
    }

    // The events are composed, so one document-level listener covers every
    // button on the page.
    document.addEventListener('ol-book-state-change', (event) => {
        const { key, shelf, rating } = event.detail || {};
        forWork(key, (button) => {
            button.shelf = shelf ?? null;
            button.rating = rating ?? null;
            // Coming off a shelf deletes the check-ins server-side.
            if (shelf === null || shelf === undefined) {
                button.readDate = null;
                button.eventId = null;
            }
        });
    });

    document.addEventListener('ol-book-check-in', (event) => {
        const { key, date, eventId } = event.detail || {};
        forWork(key, (button) => {
            button.readDate = date ?? null;
            button.eventId = eventId ?? null;
        });
    });
}
