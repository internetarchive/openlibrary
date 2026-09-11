export default function initServiceWorker(){
    if ('serviceWorker' in navigator) {
        const register = () => {
            navigator.serviceWorker.register('/sw.js')
                .then(() => { })
                .catch(error => {
                    // eslint-disable-next-line no-console
                    console.error(`Service worker registration failed: ${error}`);
                });
        };
        // The bundle loads asynchronously, so the load event may already have fired
        if (document.readyState === 'complete') {
            register();
        } else {
            window.addEventListener('load', register);
        }
    }

    window.addEventListener('beforeinstallprompt', (e) => {
        // Prevent the mini-infobar from appearing on mobile
        e.preventDefault();
    });
}
