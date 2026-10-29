import { onBeforeUnmount } from 'vue';

/**
 * Show a failure notice in the shared fixed bottom-center toast stack.
 *
 * The stack is <ol-toast-region>, defined by the ol-components bundle that
 * every page already loads, so the message is visible wherever the user has
 * scrolled to. The panel used to render its own notice in-flow at the foot of
 * the card, which was easy to miss when the panel itself was off-screen.
 *
 * The elements are created in the light DOM rather than importing the Lit
 * module into the Vue chunk. The page already loads the shared Lit bundle;
 * importing the source module here could put a second copy of the module in
 * the build and make both copies race to register the same custom-element
 * names. Creating the tags is the documented route for code outside that
 * bundle, and the custom-element registry upgrades them in place.
 *
 * @param {string} message - Already-translated text.
 * @returns {HTMLElement} The toast element.
 */
export function showErrorToast(message) {
    let region = document.querySelector('ol-toast-region');
    if (!region) {
        region = document.createElement('ol-toast-region');
        document.body.appendChild(region);
    }
    const toast = document.createElement('ol-toast');
    toast.setAttribute('message', message);
    toast.setAttribute('type', 'error');
    // Preserve the six-second duration of the former Vue-owned toast.
    toast.setAttribute('timeout', '6000');
    region.appendChild(toast);
    return toast;
}

/**
 * Toast notifications for the Testing Environment panel.
 *
 * @returns {{ setToast: (msg: string) => void }}
 */
export function useToast() {
    let current = null;

    function setToast(message) {
        // Replace rather than stack: an action fails one way, and the old
        // in-panel notice only ever showed the latest message.
        current?.close?.('programmatic');
        current = showErrorToast(message);
    }

    // Closing removes the element, so a toast outliving the panel would be
    // left on screen with nothing that can dismiss it.
    onBeforeUnmount(() => {
        current?.close?.('programmatic');
        current = null;
    });

    return { setToast };
}
