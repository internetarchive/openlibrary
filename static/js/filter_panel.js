import {
    getGlobalPreferences,
    setGlobalPreferences,
    updateAllCarousels,
    onGlobalPreferencesChange
} from './preferences.js';

const AVAILABILITY_ID = 'home-filter-availability';
const LANGUAGE_ID = 'home-filter-language';
const LANGUAGE_ENDPOINT = '/languages.json?limit=500&sort=count';
const CLEAR_ALL = 'home-filter-clear-all';

const DEFAULT_LANGUAGE_OPTIONS = [
    { value: 'eng', label: 'English' },
    { value: 'fre', label: 'French' },
    { value: 'ger', label: 'German' },
    { value: 'spa', label: 'Spanish' },
    { value: 'por', label: 'Portuguese' },
    { value: 'ita', label: 'Italian' },
    { value: 'rus', label: 'Russian' },
    { value: 'chi', label: 'Chinese' },
    { value: 'jpn', label: 'Japanese' },
    { value: 'ara', label: 'Arabic' },
];

async function fetchLanguageOptions() {
    try {
        const response = await fetch(LANGUAGE_ENDPOINT);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        const options = (Array.isArray(data) ? data : [])
            .filter((lang) => lang && lang.marc_code && lang.name)
            .map((lang) => ({ value: lang.marc_code, label: lang.name }));

        return options.length ? options : DEFAULT_LANGUAGE_OPTIONS;
    } catch {
        return DEFAULT_LANGUAGE_OPTIONS;
    }
}

class FilterPanelController {
    constructor() {
        this.toggle = document.getElementById(AVAILABILITY_ID);
        this.language = document.getElementById(LANGUAGE_ID);
        this.clearAllBtn = document.getElementById(CLEAR_ALL);

        if (!this.toggle || !this.language) {
            return;
        }

        this.init();
    }

    async init() {
        await this.loadLanguages();
        this.loadPreferences();
        this.registerEvents();
        this.updateClearAll();

        onGlobalPreferencesChange(() => this.loadPreferences());
    }

    async loadLanguages() {
        this.language.items = DEFAULT_LANGUAGE_OPTIONS;
        this.language.items = await fetchLanguageOptions();
    }

    // for when users re-visit the page (load old preferences to UI instead of starting empty)
    loadPreferences() {
        const prefs = getGlobalPreferences();

        this.toggle.checked = prefs.mode === 'fulltext';
        this.language.selected = Array.isArray(prefs.language) ? prefs.language : [];
        this.updateClearAll();
    }

    registerEvents() {
        this.toggle.addEventListener(
            'ol-toggle-change',
            () => this.savePreferences()
        );

        this.language.addEventListener(
            'ol-select-popover-change',
            () => this.savePreferences()
        );

        this.clearAllBtn?.addEventListener(
            'click',
            () => this.clearAllFilters()
        );
    }

    savePreferences() {
        const prefs = getGlobalPreferences();

        const selected = Array.isArray(this.language.selected)
            ? this.language.selected.filter((value) => typeof value === 'string' && value)
            : [];

        setGlobalPreferences({
            ...prefs,
            mode: this.toggle.checked ? 'fulltext' : 'all',
            language: selected,
        });

        this.updateClearAll();
        updateAllCarousels();
    }

    updateClearAll() {
        if (!this.clearAllBtn) return;
        const show = this.toggle.checked && (this.language.selected?.length > 0);
        console.log('toggle.checked:', this.toggle.checked);
        console.log('language.selected:', this.language.selected);
        console.log('show:', show);
        this.clearAllBtn.hidden = !show;
    }

    clearAllFilters() {
        this.toggle.checked = false;
        this.language.selected = [];
        this.savePreferences();
    }
}

export function initializeFilterPanel() {
    return new FilterPanelController();
}
