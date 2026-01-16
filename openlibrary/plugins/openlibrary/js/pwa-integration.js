/**
 * PWA Integration
 * Auto-triggers PWA installation prompts throughout Open Library
 */

import { PWAPrompts } from './pwa-prompt.js';

export function initPWAIntegration() {
    PWAPrompts.incrementSession();

    window.OpenLibraryPWA = {
        showInstallPrompt: PWAPrompts.showAfterBorrow,
        showLoginPrompt: PWAPrompts.showAfterLogin,
        showReturnPrompt: PWAPrompts.showForReturnVisitor
    };

    setTimeout(() => {
        PWAPrompts.showForReturnVisitor();
    }, 2000);

    document.addEventListener('DOMContentLoaded', setupFormListeners);
    setupAjaxListeners();
}

function setupFormListeners() {
    const borrowForms = document.querySelectorAll('form[action*="borrow"], form[action*="loan"], .borrow-form');
    borrowForms.forEach(form => {
        form.addEventListener('submit', () => {
            setTimeout(() => {
                if (!isFormError()) {
                    PWAPrompts.showAfterBorrow();
                }
            }, 1500);
        });
    });

    const loginForms = document.querySelectorAll('form[action*="login"], form[action*="signin"], .login-form');
    loginForms.forEach(form => {
        form.addEventListener('submit', () => {
            setTimeout(() => {
                if (!isFormError()) {
                    PWAPrompts.showAfterLogin();
                }
            }, 1500);
        });
    });

    const signupForms = document.querySelectorAll('form[action*="signup"], form[action*="register"], .signup-form');
    signupForms.forEach(form => {
        form.addEventListener('submit', () => {
            setTimeout(() => {
                if (!isFormError()) {
                    PWAPrompts.showAfterLogin();
                }
            }, 1500);
        });
    });
}

function setupAjaxListeners() {
    if (window.jQuery) {
        jQuery(document).on('ajaxSuccess', function(event, xhr, settings) {
            if (isBorrowRequest(settings.url)) {
                setTimeout(() => PWAPrompts.showAfterBorrow(), 500);
            } else if (isLoginRequest(settings.url)) {
                setTimeout(() => PWAPrompts.showAfterLogin(), 500);
            }
        });
    }

    const originalFetch = window.fetch;
    window.fetch = function(...args) {
        return originalFetch.apply(this, args)
            .then(response => {
                if (response.ok) {
                    const url = args[0];
                    if (isBorrowRequest(url)) {
                        setTimeout(() => PWAPrompts.showAfterBorrow(), 500);
                    } else if (isLoginRequest(url)) {
                        setTimeout(() => PWAPrompts.showAfterLogin(), 500);
                    }
                }
                return response;
            });
    };
}

function isBorrowRequest(url) {
    if (!url) return false;
    const borrowKeywords = ['borrow', 'loan', 'checkout', '/books/', '/borrow'];
    return borrowKeywords.some(keyword => url.toString().includes(keyword));
}

function isLoginRequest(url) {
    if (!url) return false;
    const loginKeywords = ['login', 'signin', 'authenticate', 'account/login'];
    return loginKeywords.some(keyword => url.toString().includes(keyword));
}

function isFormError() {
    const errorSelectors = [
        '.error',
        '.alert-error',
        '.flash-error',
        '.form-error',
        '[class*="error"]',
        '.alert-danger'
    ];

    return errorSelectors.some(selector => {
        const elements = document.querySelectorAll(selector);
        return elements.length > 0 && Array.from(elements).some(el => el.offsetParent !== null);
    });
}

window.triggerPWAPrompt = function(type = 'borrow') {
    switch (type) {
    case 'borrow':
        return PWAPrompts.showAfterBorrow();
    case 'login':
        return PWAPrompts.showAfterLogin();
    case 'return':
        return PWAPrompts.showForReturnVisitor();
    default:
        console.warn('Unknown PWA prompt type:', type);
        return false;
    }
};
