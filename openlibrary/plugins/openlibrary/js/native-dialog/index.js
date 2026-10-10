/**
 * Opens the referenced dialog when a trigger is activated.
 *
 * Triggers carry `data-dialog-trigger="#some-dialog-id"` (e.g. the Reading
 * Goal card's edit pencil and Set now button). Native <dialog> elements open
 * via showModal(); <ol-dialog> components open via their `open` property.
 * @param {NodeList<HTMLElement>} triggers Elements with a data-dialog-trigger attribute
 */
export function initDialogTriggers(triggers) {
    for (const trigger of triggers) {
        trigger.addEventListener('click', (event) => {
            event.preventDefault();
            const dialog = document.querySelector(trigger.dataset.dialogTrigger);
            if (!dialog) {
                return;
            }
            if (typeof dialog.showModal === 'function') {
                dialog.showModal();
            } else {
                dialog.open = true;
            }
        });
    }
}

/**
 * Adds close functionality to each given dialog element.
 *
 * Dialog will be closed if:
 * 1. The patron clicks outside of the dialog.
 * 2. The dialog receives a `close-dialog` event.
 * @param {HTMLCollection<HTMLDialogElement>} elems
 */
export function initDialogs(elems) {
    for (const elem of elems) {
        elem.addEventListener('click', function(event) {

            // Event target exclusions needed for FireFox, which sets mouse positions to zero on
            // <select> and <option> clicks
            if (isOutOfBounds(event, elem) && event.target.nodeName !== 'SELECT' && event.target.nodeName !== 'OPTION') {
                elem.close();
            }
        });
        elem.addEventListener('close-dialog', function() {
            elem.close();
        });
        const closeIcon = elem.querySelector('.native-dialog--close');
        closeIcon.addEventListener('click', function() {
            elem.close();
        });
    }
}

/**
 * Determines if a click event is outside of the given dialog's bounds
 *
 * @param {MouseEvent} event A `click` event
 * @param {HTMLDialogElement} dialog
 * @returns `true` if the click was out of bounds.
 */
function isOutOfBounds(event, dialog) {
    const rect = dialog.getBoundingClientRect();
    return (
        event.clientX < rect.left ||
        event.clientX > rect.right ||
        event.clientY < rect.top ||
        event.clientY > rect.bottom
    );
}
