/**
 * Owns book state for a page of `<ol-shelf-button>`s.
 *
 * The buttons are stateless by contract: they never write their own `shelf` or
 * `rating`, they emit `ol-book-state-change` — optimistically on click, and
 * again with the old value if the write fails — and the surface applies it.
 * Server-rendering the attributes only supplies the opening state, so without
 * this the label stops matching the server after the first change.
 *
 * Applying it centrally is also what keeps two buttons for the same work in
 * step, and it is where the check-in prompt gets told what happened: the prompt
 * is a sibling of the button (`#check-in-container-<olid>`, same id the dropper
 * used), so the button stays unaware of check-ins.
 *
 * @module my-books/shelf-buttons
 */
import { CheckInComponents } from './MyBooksDropper/CheckInComponents';

const ALREADY_READ = 3;

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
    /** @type {Map<string, CheckInComponents>} */
    const checkInsByWork = new Map();

    for (const button of shelfButtons) {
        const workOlid = olid(button.getAttribute('work-key'));
        if (!workOlid) continue;

        if (!buttonsByWork.has(workOlid)) {
            buttonsByWork.set(workOlid, []);

            // Only rendered for signed-in patrons.
            const container = document.querySelector(`#check-in-container-${workOlid}`);
            if (container) {
                const components = new CheckInComponents(container);
                components.initialize();
                checkInsByWork.set(workOlid, components);
            }
        }
        buttonsByWork.get(workOlid).push(button);
    }

    if (!buttonsByWork.size) return;

    // The event is composed, so one document-level listener covers every button.
    document.addEventListener('ol-book-state-change', (event) => {
        const { key, shelf, rating } = event.detail || {};
        const workOlid = olid(key);

        for (const button of buttonsByWork.get(workOlid) || []) {
            button.shelf = shelf ?? null;
            button.rating = rating ?? null;
        }

        const components = checkInsByWork.get(workOlid);
        if (!components) return;

        if (shelf === null || shelf === undefined) {
            // Coming off a shelf deletes the check-ins server-side.
            components.hideCheckInPrompt();
            components.hideCheckInDisplay();
            components.resetForm();
        } else if (shelf === ALREADY_READ && !components.hasReadDate()) {
            components.showCheckInPrompt();
        } else {
            components.hideCheckInPrompt();
        }
    });
}
