/**
 * olConfirm() / olAlert() whose message is the content of a <template> in the page,
 * so the message may carry markup and is written where $_() extraction sees it:
 *
 *     <template id="delete-list-dialog">$_('This cannot be undone.')</template>
 *
 * The caller passes the title and button labels with _().
 */
import { _ } from './i18n.js';
import { olAlert, olConfirm } from '../../../components/lit/alert-dialog.js';

/**
 * @param {HTMLTemplateElement} template
 * @param {Object} options
 * @param {String} options.title
 * @param {String} options.confirmLabel
 * @param {Node} [options.message] - Replaces the template's own content, e.g. a clone with a name filled in.
 * @param {Boolean} [options.destructive]
 * @returns {Promise<Boolean>}
 */
export function confirmFromTemplate(template, { title, confirmLabel, message = template, destructive = true }) {
    return olConfirm({
        title,
        message,
        confirmLabel,
        labelClose: _('Close'),
        destructive
    });
}

/**
 * @param {HTMLTemplateElement} template
 * @param {String} title
 * @returns {Promise<void>}
 */
export function alertFromTemplate(template, title) {
    return olAlert({
        title,
        message: template,
        labelClose: _('Close')
    });
}
