import { getGlobalPreferences, setGlobalPreferences, updateAllCarousels } from './preferences.js';

function initFilterPanelFromPreferences() {
    const prefs = getGlobalPreferences();
    const modeSelect = document.getElementById('global-mode-select');
    const langSelect = document.getElementById('language-select');
    const dateStart = document.getElementById('global-date-start');
    const dateEnd = document.getElementById('global-date-end');
    if (modeSelect) modeSelect.value = prefs.mode || 'all';
    if (langSelect) langSelect.value = prefs.language || 'all';
    if (dateStart) dateStart.value = (prefs.date && prefs.date[0]) || 1900;
    if (dateEnd) dateEnd.value = (prefs.date && prefs.date[1]) || 2025;
}

document.addEventListener('DOMContentLoaded', () => {
    initFilterPanelFromPreferences();

    document.getElementById('save-preferences-btn').addEventListener('click', () => {
        const startYear = parseInt(document.getElementById('global-date-start').value) || 1900;
        const endYear = parseInt(document.getElementById('global-date-end').value) || 2025;
        const prefs = {
            mode: document.getElementById('global-mode-select').value || 'all',
            language: document.getElementById('language-select').value,
            date: [startYear, endYear]
        };
        setGlobalPreferences(prefs);

        fetch('/account/preferences', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...prefs, redirect: false })
        }).then(res => {
            if (!res.ok) throw new Error('Failed to save preferences');
            return res.json();
        }).then(() => {
            // 3, Trigger local UI update (carousel reload)
            updateAllCarousels();
        }).catch(() => {
            // Consider showing user feedback
        });

        // Close filter panel
        const filterPanel = document.getElementById('filter-panel');
        const filterTrigger = document.getElementById('filter-panel-trigger');
        if (filterPanel) {
            filterPanel.classList.remove('show');
            filterPanel.classList.add('hidden');
        }
        if (filterTrigger) {
            filterTrigger.setAttribute('aria-expanded', 'false');
            filterTrigger.focus();
        }
    });
});
