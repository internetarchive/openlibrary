/* 4 layers
1. Constants       → the localStorage key names + thresholds
2. Helper functions → mobile/iOS detection, visit counting, borrow trigger, show logic
3. UI builder      → create the HTML element and inject it into <body>
4. Main init fn    → ties everything together, exported as default
 */
const VISIT_COUNT_KEY = 'pwa-visit-count';
const DISMISSED_KEY = 'pwa-prompt-dismissed';
const INSTALLED_KEY = 'pwa-installed';
const TRIGGER_KEY = 'pwa-trigger-reason';
const VISIT_THRESHOLD = 2;
const DISMISS_TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30 DAYS IN MS

function isMobileDevice () {
    return window.matchMedia('(max-width: 767px)').matches;
}

function isIOS() {
    return /iphone|ipad|ipod/i.test(navigator.userAgent)
        && !window.navigator.standalone;
}

function attachBorrowTrigger() {
    const borrowBtn = document.querySelector('.cta-btn--borrow');
    if (!borrowBtn) return; // not on a book page, do nothing

    borrowBtn.addEventListener('click', () => {
        localStorage.setItem(TRIGGER_KEY, 'borrow');
        // Don't preventDefault - let the navigation happen normally
    });
}

function incrementVisitCount() {
    const count = parseInt(localStorage.getItem(VISIT_COUNT_KEY) || '0', 10);
    localStorage.setItem(VISIT_COUNT_KEY, String(count + 1));
}

function shouldShowPrompt(){
    // Already installed? Never show.
    if (localStorage.getItem(INSTALLED_KEY)) return false;
    if (window.matchMedia('(display-mode: standalone)').matches) return false;

    // Check dismiss cooldown (applies to both paths)
    const dismissed = localStorage.getItem(DISMISSED_KEY);
    if (dismissed && (Date.now() - new Date(dismissed).getTime())< DISMISS_TTL_MS) return false;

    // HIGH-INTENT PATH: just borrowed a book
    const trigger = localStorage.getItem(TRIGGER_KEY);
    if (trigger === 'borrow') {
        localStorage.removeItem(TRIGGER_KEY); //consume once
        return true;
    }

    // return visitor fallback
    const count = parseInt(localStorage.getItem(VISIT_COUNT_KEY) || '0', 10);
    return count >= VISIT_THRESHOLD;
}

function dismiss(promptEl) {
    localStorage.setItem(DISMISSED_KEY, new Date().toISOString());
    promptEl.remove();
}

async function install(promptEl) {
    const { getDeferredInstallPrompt } = await import('./service-worker-init.js');
    const deferredPrompt = getDeferredInstallPrompt();
    if (!deferredPrompt) return;
    await deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === 'accepted') {
        localStorage.setItem(INSTALLED_KEY, '1');
        promptEl.remove();
    } else {
        dismiss(promptEl);
    }
}

function createPrompt(isIOSDevice, onInstall, onDismiss) {
    const el = document.createElement('div');
    el.id = 'pwa-install-prompt';
    el.className = 'pwa-install-prompt';
    el.setAttribute('role', 'region');
    el.setAttribute('aria-label', 'Add Open Library to home screen');

    const descText = isIOSDevice
        ? 'Tap <strong>Share</strong> then <strong>"Add to Home Screen"</strong> to install.'
        : 'Add to your home screen for quick access — no app store needed.';
    const installBtn = isIOSDevice
        ? ''
        : '<button class="pwa-install-prompt__btn pwa-install-prompt__btn--install">Add to Home Screen</button>';

    el.innerHTML = `
    <button class="pwa-install-prompt__close" aria-label="Dismiss">&#x2715;</button>
    <div class="pwa-install-prompt__handle" aria-hidden="true"></div>
    <div class="pwa-install-prompt__body">
        <img src="/static/images/openlibrary-192x192.png" alt=""
             class="pwa-install-prompt__icon" width="48" height="48">
        <div class="pwa-install-prompt__text">
            <strong class="pwa-install-prompt__title">Take Open Library with you</strong>
            <p class="pwa-install-prompt__desc">${descText}</p>
        </div>
    </div>
    <div class="pwa-install-prompt__actions">
        ${installBtn}
        <button class="pwa-install-prompt__btn pwa-install-prompt__btn--dismiss">Not now</button>
    </div>
    `;
    document.body.appendChild(el);
    setTimeout(() => el.classList.add('pwa-install-prompt--visible'), 50);

    el.querySelector('.pwa-install-prompt__close')
        .addEventListener('click', () => onDismiss(el));
    el.querySelector('.pwa-install-prompt__btn--dismiss')
        .addEventListener('click', () => onDismiss(el));
    if (!isIOSDevice) {
        el.querySelector('.pwa-install-prompt__btn--install')
            .addEventListener('click', () => onInstall(el));
    }
}

export default function initPWAInstallPrompt() {
    attachBorrowTrigger();

    if (!isMobileDevice()) return;

    incrementVisitCount();

    if (!shouldShowPrompt()) return;

    if (isIOS()) {
        createPrompt(true, null, dismiss);
    } else {
        import('./service-worker-init.js').then(({ getDeferredInstallPrompt }) => {
            if (getDeferredInstallPrompt()) {
                createPrompt(false, install, dismiss);
            } else {
                window.addEventListener('pwa-install-ready', () => {
                    createPrompt(false, install, dismiss);
                }, {once: true});
            }
        });
    }
}
