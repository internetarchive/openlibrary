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
            fetch('/account/login.json', {
                method: 'POST',
                credentials: 'include',
                body: JSON.stringify(e.data.s3)
            })
                .then((resp) => {
                    if (resp.ok) {
                        const searchParams = {
                            redirect: new URLSearchParams(window.location.search).get('redirect') || '/account/books'
                        }
                        const action = new URLSearchParams(window.location.search).get('action')
                        if (action) {
                            searchParams.action = action
                        }
                        window.location = `/account/login/success?${searchParams.toString()}`
                    }
                    return resp.json()
                })
                .then((error) => {
                    const loginForm = document.querySelector('#register')
                    const errorDiv = document.createElement('div')
                    errorDiv.classList.add('note')
                    errorDiv.textContent = error.errorDisplayString
                    loginForm.insertAdjacentElement('afterbegin', errorDiv)
                })
        }
    }

    window.addEventListener('message', handleMessageEvent, false);
}
