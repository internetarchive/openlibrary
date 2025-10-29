import { FadingToast } from './Toast'

export function initPrivateButtons(buttons) {
    buttons.forEach(button => {
        button.addEventListener('click', (event) => {
            event.preventDefault();
            const toast = new FadingToast('This patron has not enabled following', null, 3000);
            toast.show();

        });
    });
}
