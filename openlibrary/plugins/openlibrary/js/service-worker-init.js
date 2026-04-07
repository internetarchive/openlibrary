let deferredInstallPrompt = null;
export function getDeferredInstallPrompt() {
    return deferredInstallPrompt;
}
export default function initServiceWorker(){
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/sw.js')
                .then(() => { })
                .catch(error => {
                    // eslint-disable-next-line no-console
                    console.error(`Service worker registration failed: ${error}`);
                });
        });
    }

    window.addEventListener('beforeinstallprompt', (e) => {
        // Prevent the mini-infobar from appearing on mobile
        e.preventDefault();
        deferredInstallPrompt = e;
        // Notify any listeners that the prompt is ready
        window.dispatchEvent(new CustomEvent('pwa-install-ready'));
    });
    window.addEventListener('appinstalled', ()=>{
        deferredInstallPrompt = null;
        localStorage.setItem('pwa-installed', '1');
    });
}
