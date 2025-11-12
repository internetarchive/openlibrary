/**
 * PWA Installation Prompt Manager
 * Handles contextual prompts to install Open Library as a PWA
 */

export class PWAPromptManager {
    constructor() {
        this.deferredPrompt = null;
        this.isInstallable = false;
        this.storageKeys = {
            dismissed: 'ol-pwa-prompt-dismissed',
            installed: 'ol-pwa-installed',
            shownCount: 'ol-pwa-prompt-shown-count',
            lastShown: 'ol-pwa-prompt-last-shown'
        };

        this.config = {
            maxShownCount: 3,
            cooldownDays: 30,
            returnVisitMinSessions: 2,
            enableABTesting: true,
            abTestPercentage: 50
        };

        this.init();
    }

    init() {
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            this.deferredPrompt = e;
            this.isInstallable = true;
        });

        window.addEventListener('appinstalled', () => {
            this.onAppInstalled();
        });

        if (this.isPWAInstalled()) {
            this.markAsInstalled();
        }
    }

    isPWAInstalled() {
        if (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) {
            return true;
        }

        if (window.navigator.standalone === true) {
            return true;
        }

        return false;
    }

    shouldShowPrompt() {
        if (!this.isInstallable || !this.deferredPrompt) return false;
        if (this.isMarkedAsInstalled()) return false;
        if (this.isPermanentlyDismissed()) return false;
        if (this.isInCooldownPeriod()) return false;
        if (this.hasExceededMaxShownCount()) return false;
        if (this.config.enableABTesting && !this.isInABTestGroup()) return false;

        return true;
    }

    showBorrowPrompt() {
        if (!this.shouldShowPrompt()) return false;

        this.showPrompt({
            trigger: 'book-borrow',
            title: 'Take Open Library with you',
            message: 'Get faster access next time—add Open Library to your home screen!',
            primaryButton: 'Add to Home Screen',
            secondaryButton: 'Not now'
        });

        return true;
    }

    showReturnVisitorPrompt() {
        const sessionCount = this.getSessionCount();
        if (sessionCount < this.config.returnVisitMinSessions) return false;
        if (!this.shouldShowPrompt()) return false;

        this.showPrompt({
            trigger: 'return-visitor',
            title: 'Welcome back!',
            message: 'Add Open Library to your home screen for quick access anytime.',
            primaryButton: 'Add to Home Screen',
            secondaryButton: 'Maybe later'
        });

        return true;
    }

    showPostLoginPrompt() {
        if (!this.shouldShowPrompt()) return false;

        this.showPrompt({
            trigger: 'post-login',
            title: 'Get the full experience',
            message: 'Add Open Library to your home screen to access your books anytime.',
            primaryButton: 'Add to Home Screen',
            secondaryButton: 'Skip for now'
        });

        return true;
    }

    showPrompt(options) {
        this.trackPromptShown(options.trigger);

        const promptElement = this.createPromptElement(options);
        document.body.appendChild(promptElement);

        requestAnimationFrame(() => {
            promptElement.classList.add('pwa-prompt--show');
        });

        this.trackEvent('pwa_prompt_shown', {
            trigger: options.trigger,
            session_count: this.getSessionCount(),
            is_mobile: this.isMobile()
        });
    }

    createPromptElement(options) {
        const prompt = document.createElement('div');
        prompt.className = 'pwa-prompt';
        prompt.innerHTML = `
            <div class="pwa-prompt__backdrop"></div>
            <div class="pwa-prompt__content">
                <div class="pwa-prompt__header">
                    <h3 class="pwa-prompt__title">${options.title}</h3>
                    <button class="pwa-prompt__close" aria-label="Close">×</button>
                </div>
                <p class="pwa-prompt__message">${options.message}</p>
                <div class="pwa-prompt__actions">
                    <button class="pwa-prompt__btn pwa-prompt__btn--primary" data-action="install">
                        ${options.primaryButton}
                    </button>
                    <button class="pwa-prompt__btn pwa-prompt__btn--secondary" data-action="dismiss">
                        ${options.secondaryButton}
                    </button>
                </div>
            </div>
        `;

        const installBtn = prompt.querySelector('[data-action="install"]');
        const dismissBtn = prompt.querySelector('[data-action="dismiss"]');
        const closeBtn = prompt.querySelector('.pwa-prompt__close');
        const backdrop = prompt.querySelector('.pwa-prompt__backdrop');

        installBtn.addEventListener('click', () => this.handleInstall(prompt, options.trigger));
        dismissBtn.addEventListener('click', () => this.handleDismiss(prompt, options.trigger, false));
        closeBtn.addEventListener('click', () => this.handleDismiss(prompt, options.trigger, false));
        backdrop.addEventListener('click', () => this.handleDismiss(prompt, options.trigger, false));

        return prompt;
    }

    async handleInstall(promptElement, trigger) {
        if (!this.deferredPrompt) return;

        this.deferredPrompt.prompt();
        const result = await this.deferredPrompt.userChoice;

        this.trackEvent('pwa_install_prompted', {
            trigger: trigger,
            outcome: result.outcome
        });

        if (result.outcome === 'accepted') {
            this.markAsInstalled();
            this.trackEvent('pwa_installed', { trigger: trigger });
        }

        this.deferredPrompt = null;
        this.removePrompt(promptElement);
    }

    handleDismiss(promptElement, trigger, permanent = false) {
        this.markAsDismissed(permanent);
        this.removePrompt(promptElement);

        this.trackEvent('pwa_prompt_dismissed', {
            trigger: trigger,
            permanent: permanent
        });
    }

    removePrompt(promptElement) {
        promptElement.classList.remove('pwa-prompt--show');
        setTimeout(() => {
            if (promptElement.parentNode) {
                promptElement.parentNode.removeChild(promptElement);
            }
        }, 300);
    }

    markAsInstalled() {
        localStorage.setItem(this.storageKeys.installed, Date.now().toString());
    }

    markAsDismissed(permanent = false) {
        const dismissData = {
            timestamp: Date.now(),
            permanent: permanent
        };
        localStorage.setItem(this.storageKeys.dismissed, JSON.stringify(dismissData));
    }

    trackPromptShown(trigger) {
        const currentCount = this.getShownCount();
        localStorage.setItem(this.storageKeys.shownCount, (currentCount + 1).toString());
        localStorage.setItem(this.storageKeys.lastShown, Date.now().toString());
    }

    onAppInstalled() {
        this.markAsInstalled();
        this.trackEvent('pwa_installed_detected');
    }

    isMarkedAsInstalled() {
        return localStorage.getItem(this.storageKeys.installed) !== null;
    }

    isPermanentlyDismissed() {
        const dismissData = this.getDismissData();
        return dismissData && dismissData.permanent;
    }

    isInCooldownPeriod() {
        const dismissData = this.getDismissData();
        if (!dismissData || dismissData.permanent) return false;

        const daysSinceDismissal = (Date.now() - dismissData.timestamp) / (1000 * 60 * 60 * 24);
        return daysSinceDismissal < this.config.cooldownDays;
    }

    hasExceededMaxShownCount() {
        return this.getShownCount() >= this.config.maxShownCount;
    }

    getDismissData() {
        const data = localStorage.getItem(this.storageKeys.dismissed);
        return data ? JSON.parse(data) : null;
    }

    getShownCount() {
        const count = localStorage.getItem(this.storageKeys.shownCount);
        return count ? parseInt(count, 10) : 0;
    }

    getSessionCount() {
        const sessions = localStorage.getItem('ol-session-count');
        return sessions ? parseInt(sessions, 10) : 1;
    }

    incrementSessionCount() {
        const currentSessions = this.getSessionCount();
        localStorage.setItem('ol-session-count', (currentSessions + 1).toString());
    }

    isInABTestGroup() {
        const userId = this.getUserId();
        const hash = this.simpleHash(userId);
        return (hash % 100) < this.config.abTestPercentage;
    }

    getUserId() {
        let userId = localStorage.getItem('ol-user-id');
        if (!userId) {
            userId = `user_${Math.random().toString(36).substr(2, 9)}_${Date.now()}`;
            localStorage.setItem('ol-user-id', userId);
        }
        return userId;
    }

    simpleHash(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash;
        }
        return Math.abs(hash);
    }

    isMobile() {
        return window.innerWidth <= 768 || /Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    }

    trackEvent(eventName, properties = {}) {
        if (window.gtag) {
            window.gtag('event', eventName, properties);
        }

        console.log('PWA Analytics:', eventName, properties);
    }
}

let pwaPromptManager;

export function initPWAPrompts() {
    if (!pwaPromptManager) {
        pwaPromptManager = new PWAPromptManager();
    }
    return pwaPromptManager;
}

export function getPWAPromptManager() {
    return pwaPromptManager || initPWAPrompts();
}

export const PWAPrompts = {
    showAfterBorrow: () => getPWAPromptManager().showBorrowPrompt(),
    showAfterLogin: () => getPWAPromptManager().showPostLoginPrompt(),
    showForReturnVisitor: () => getPWAPromptManager().showReturnVisitorPrompt(),
    incrementSession: () => getPWAPromptManager().incrementSessionCount()
};
