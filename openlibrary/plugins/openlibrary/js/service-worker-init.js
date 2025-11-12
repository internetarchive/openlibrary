import { initPWAPrompts } from './pwa-prompt.js';

export default function initServiceWorker(){
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/sw.js')
                .then(() => {
                    console.log('Service worker registered successfully');
                })
                .catch(error => {
                    // eslint-disable-next-line no-console
                    console.error(`Service worker registration failed: ${error}`);
                });
        });
    }

    // Initialize PWA installation prompts
    // This will handle the beforeinstallprompt event and provide contextual prompts
    initPWAPrompts();
}
