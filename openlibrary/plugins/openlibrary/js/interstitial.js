export function initInterstitial(elem) {
    // Initialize countdown timer
    let seconds = elem.dataset.wait;
    const url = elem.dataset.url;
    const timerElement = elem.querySelector('#timer');

    // Store countdown interval so we can clear it if needed
    const countdown = setInterval(() => {
        seconds--;
        timerElement.textContent = seconds;
        if (seconds === 0) {
            clearInterval(countdown);
            window.location.href = url;
        }
    }, 1000);

    // Add cancel button handler
    const cancelButton = elem.querySelector('.js-cancel-redirect');
    if (cancelButton) {
        cancelButton.addEventListener('click', (e) => {
            e.preventDefault();
            // Clear the countdown timer
            clearInterval(countdown);

            try {
                window.close();
            } catch (error) {
                console.error('Failed to close window:', error);
                // Fallback behavior
                window.location.href = '/';
            }
        });
    }

    // Return cleanup function in case component unmounts
    return () => {
        clearInterval(countdown);
    };
}
