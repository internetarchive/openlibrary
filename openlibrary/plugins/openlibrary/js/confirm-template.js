/**
 * olConfirm() / olAlert() driven by a <template> in the page, so the strings
 * are written where $_() extraction sees them and the message may carry markup:
 *
 *     <template id="delete-list-dialog"
 *               data-i18n="$json_encode({'title': _('Delete this list?'), 'confirm': _('Delete list'), 'cancel': _('Cancel'), 'close': _('Close')})">
 *         $_('This cannot be undone.')
 *     </template>
 *
 * Alerts take `ok` instead of `confirm` and `cancel`.
 */
import { olAlert, olConfirm } from '../../../components/lit/alert-dialog.js';

/**
 * @param {HTMLTemplateElement} template
 * @param {Object} [options]
 * @param {Object} [options.i18n] - The template's data-i18n, if the caller has already parsed it.
 * @param {Node} [options.message] - Replaces the template's own content, e.g. a clone with a name filled in.
 * @param {String} [options.title] - Replaces the template's title, e.g. one with a count filled in.
 * @param {String} [options.confirmLabel] - Replaces the template's confirm label.
 * @param {Boolean} [options.destructive]
 * @returns {Promise<Boolean>}
 */
export function confirmFromTemplate(template, { i18n = JSON.parse(template.dataset.i18n), message = template, destructive = true, title, confirmLabel } = {}) {
    return olConfirm({
        title: title ?? i18n.title,
        message,
        confirmLabel: confirmLabel ?? i18n.confirm,
        cancelLabel: i18n.cancel,
        labelClose: i18n.close,
        destructive,
    });
}

/**
 * @param {HTMLTemplateElement} template
 * @returns {Promise<void>}
 */
export function alertFromTemplate(template) {
    const i18n = JSON.parse(template.dataset.i18n);
    return olAlert({
        title: i18n.title,
        message: template,
        okLabel: i18n.ok,
        labelClose: i18n.close,
    });
}
