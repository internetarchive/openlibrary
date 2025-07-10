/**
 * Registers the handleMessageEvent function as an event listener for message events.
 *
 * @param {*} element - The element to be modified by the handleMessageEvent function.
 */
export function initMessageEventListener(element) {
    /**
     * Handles messages from archive.org and performs actions based on the message type.
     *
     * @param {MessageEvent} e - The message event.
     */
    function handleMessageEvent(e) {
        if (!/[./]archive\.org$$/.test(e.origin)) return;

        if (e.data.type === 'resize') {
            element.setAttribute('scrolling', 'no');
            if (e.data.height) element.style.height = `${e.data.height}px`;
        }
        else if (e.data.type === 's3-keys') {
            const s3AccessInput = document.querySelector('#access')
            const s3SecretInput = document.querySelector('#secret')
            s3AccessInput.value = e.data.s3.access
            s3SecretInput.value = e.data.s3.secret

            const loginForm = document.querySelector('#register')
            loginForm.action = '/account/login'
            loginForm.submit()
        }
    }

    window.addEventListener('message', handleMessageEvent, false);
}
