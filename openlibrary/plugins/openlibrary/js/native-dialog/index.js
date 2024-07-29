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
        elem.close()
      }
    })
    elem.addEventListener('close-dialog', function() {
      elem.close()
    })
    const closeIcon = elem.querySelector('.native-dialog--close')
    closeIcon.addEventListener('click', function() {
      elem.close()
    })
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
  const rect = dialog.getBoundingClientRect()
  return (
    event.clientX < rect.left ||
        event.clientX > rect.right ||
        event.clientY < rect.top ||
        event.clientY > rect.bottom
  );
}
