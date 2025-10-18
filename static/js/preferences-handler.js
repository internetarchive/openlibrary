import { setGlobalPreferences, updateAllCarousels } from './preferences.js';

document.addEventListener('DOMContentLoaded', () => {
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
        }).then(res => res.json()).then(() => {
            // 3. Trigger local UI update (carousel reload)
            updateAllCarousels();
        });

        // Close filter panel
        const filterPanel = document.getElementById('filter-panel');
        const filterTrigger = document.getElementById('filter-panel-trigger');
        filterPanel.classList.remove('show');
        filterPanel.classList.add('hidden');
        filterTrigger.setAttribute('aria-expanded', 'false');
        filterTrigger.focus();
    });
});
