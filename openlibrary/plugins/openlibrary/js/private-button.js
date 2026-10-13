import { showToast } from './show-toast';

export function initPrivateButtons(buttons) {
    buttons.forEach(button => {
        button.addEventListener('click', event => {
            event.preventDefault();
            // The wrapper's title carries the translated explanation.
            const message = button.closest('[title]')?.title || 'This patron has not enabled following';
            showToast(message);
        });
    });
}
