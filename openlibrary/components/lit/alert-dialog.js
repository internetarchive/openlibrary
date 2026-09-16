/**
 * Promise-based confirmation and alert dialogs on top of <ol-dialog>: the
 * async replacement for `window.confirm()` / `window.alert()`.
 *
 *     if (await olConfirm({ title, message, confirmLabel, destructive: true })) { ... }
 *
 * Only for a yes/no question or an acknowledgement. A dialog that collects
 * input composes <ol-dialog> directly and reads its fields before closing.
 *
 * This module creates the element rather than importing OlDialog, so page
 * scripts can import it without bundling a second copy of the component;
 * ol-components.js registers <ol-dialog> on every page.
 */

/**
 * Strings become text nodes and <template>s are cloned, as in showToast(), so
 * no runtime string is ever parsed as HTML.
 * @param {String|HTMLTemplateElement|Node|Array<Node|String>} content
 * @returns {Array<Node|String>}
 */
function toNodes(content) {
    if (content instanceof HTMLTemplateElement) return [content.content.cloneNode(true)];
    return [].concat(content ?? []);
}

/**
 * @param {Object} options
 * @param {String} options.title
 * @param {String|HTMLTemplateElement|Node|Array<Node|String>} options.message
 * @param {Array<{label: String, value: String, variant: String}>} options.actions - In display order.
 * @param {String} options.focusValue - Action that receives initial focus.
 * @param {String} [options.labelClose]
 * @returns {Promise<String>} The chosen action's value, or '' when dismissed.
 */
async function showAlertDialog({ title, message, actions, focusValue, labelClose }) {
    await customElements.whenDefined('ol-dialog');

    const dialog = document.createElement('ol-dialog');
    dialog.alert = true;
    dialog.width = 'small';
    dialog.label = title;
    if (labelClose) dialog.labelClose = labelClose;

    const body = document.createElement('div');
    body.append(...toNodes(message));

    const footer = document.createElement('div');
    footer.slot = 'footer';
    footer.style.cssText = 'display: flex; flex-wrap: wrap; justify-content: flex-end; gap: var(--spacing-inline-md);';
    for (const { label, value, variant } of actions) {
        const button = document.createElement('ol-button');
        button.variant = variant;
        button.textContent = label;
        if (value === focusValue) button.setAttribute('autofocus', '');
        button.addEventListener('click', () => dialog.close(value));
        footer.append(button);
    }

    dialog.append(body, footer);

    return new Promise((resolve) => {
        dialog.addEventListener('ol-after-close', (event) => {
            // Ignore after-close events bubbling up from a dialog nested in the message.
            if (event.target !== dialog) return;
            dialog.remove();
            resolve(event.detail.returnValue);
        });
        document.body.append(dialog);
        dialog.open = true;
    });
}

/**
 * Asks a yes/no question. Escape, the backdrop, and the close button all
 * count as cancel.
 *
 * @param {Object} options
 * @param {String} options.title - Translated question, e.g. "Delete this list?"
 * @param {String|HTMLTemplateElement|Node|Array<Node|String>} [options.message] -
 *     Translated detail. Pass a <template> from the page template for markup.
 * @param {String} [options.confirmLabel] - Translated; name the action ("Delete list"), not "OK".
 * @param {String} [options.cancelLabel] - Translated.
 * @param {String} [options.labelClose] - Translated name for the close button.
 * @param {Boolean} [options.destructive] - Red confirm button, and initial focus
 *     on Cancel so a stray Enter doesn't destroy anything.
 * @returns {Promise<Boolean>} true only when the confirm button was pressed.
 */
export async function olConfirm({
    title,
    message,
    confirmLabel = 'Confirm',
    cancelLabel = 'Cancel',
    labelClose,
    destructive = false,
}) {
    const value = await showAlertDialog({
        title,
        message,
        labelClose,
        actions: [
            { label: cancelLabel, value: 'cancel', variant: 'secondary' },
            { label: confirmLabel, value: 'confirm', variant: destructive ? 'destructive' : 'primary' },
        ],
        focusValue: destructive ? 'cancel' : 'confirm',
    });
    return value === 'confirm';
}

/**
 * Tells the reader something they must acknowledge before continuing. For
 * anything they can safely miss, use showToast() instead.
 *
 * @param {Object} options
 * @param {String} options.title - Translated.
 * @param {String|HTMLTemplateElement|Node|Array<Node|String>} [options.message] - Translated.
 * @param {String} [options.okLabel] - Translated.
 * @param {String} [options.labelClose] - Translated name for the close button.
 * @returns {Promise<void>} Resolves once the dialog has closed.
 */
export async function olAlert({ title, message, okLabel = 'OK', labelClose }) {
    await showAlertDialog({
        title,
        message,
        labelClose,
        actions: [{ label: okLabel, value: 'ok', variant: 'primary' }],
        focusValue: 'ok',
    });
}
