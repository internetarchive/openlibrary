import { showToast } from '../../../components/lit/toast.js';
import { _ } from './i18n.js';

export function initPrivateButtons(buttons) {
    buttons.forEach(button => {
        button.addEventListener('click', event => {
            event.preventDefault();
            showToast(_('This patron has not enabled following'));
        });
    });
}
