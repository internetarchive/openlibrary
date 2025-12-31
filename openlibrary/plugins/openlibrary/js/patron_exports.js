/**
 * Switches the given button to a disabled state.
 *
 * @param {HTMLElement} buttonElement
 */
function disableButton(buttonElement) {
    buttonElement.setAttribute('disabled', 'true');
    buttonElement.setAttribute('aria-disabled', 'true');
}

/**
 * Adds `submit` listeners for the given form elements.
 *
 * When any of the given forms are submitted, the form's
 * submit button is disabled.
 *
 * @param {NodeList<HTMLFormElement>} elems
 */
export function initPatronExportForms(elems) {
    elems.forEach((form) => {
        const submitButton = form.querySelector('input[type=submit]')
        form.addEventListener('submit', () => {
            disableButton(submitButton);
        })
    })
}
