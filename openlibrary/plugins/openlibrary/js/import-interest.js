/**
 * "Express interest" buttons on the import page.
 *
 * Clicks are counted in Matomo through the buttons' `data-ol-link-track`
 * attribute (see ol.analytics.js). This module only disables a button once
 * it has been clicked, and remembers that in localStorage so the same
 * patron doesn't count twice on a later visit.
 */
const STORAGE_KEY = 'ol-import-interest';

function getRecorded() {
    try {
        const recorded = JSON.parse(localStorage.getItem(STORAGE_KEY));
        return Array.isArray(recorded) ? recorded : [];
    } catch {
        return [];
    }
}

function saveRecorded(service) {
    const recorded = getRecorded();
    if (recorded.includes(service)) return;
    recorded.push(service);
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(recorded));
    } catch {
        // Storage unavailable (private mode, blocked): the button still disables for this visit
    }
}

function markRecorded(btn) {
    btn.disabled = true;
    btn.textContent = btn.dataset.interestRecordedText;
    btn.classList.replace('cta-btn--available', 'cta-btn--unavailable');
}

/**
 * @param {NodeListOf<HTMLButtonElement>} buttons
 */
export function initImportInterest(buttons) {
    const recorded = getRecorded();
    buttons.forEach(btn => {
        const service = btn.dataset.service;
        if (recorded.includes(service)) {
            markRecorded(btn);
            return;
        }
        btn.addEventListener('click', () => {
            saveRecorded(service);
            // Disable after the click finishes bubbling, so the document-level
            // Matomo listener still sees this click
            setTimeout(() => markRecorded(btn));
        });
    });
}
