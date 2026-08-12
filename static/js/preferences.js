const STORAGE_KEY = 'preferences';

function normalizeLanguageSelection(language) {
    if (Array.isArray(language)) {
        return language.filter((value) => typeof value === 'string' && value && value !== 'all');
    }

    if (typeof language === 'string' && language && language !== 'all') {
        return [language];
    }

    return [];
}

export function getGlobalPreferences() {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        const parsed = (stored && JSON.parse(stored)) || {};

        if (!parsed.global) {
            const cookiePrefs = checkCookiesAndHydrate();
            if (cookiePrefs) {
                return cookiePrefs;
            }
        }

        return {
            mode: parsed.global?.mode || 'all',
            language: normalizeLanguageSelection(parsed.global?.language),
        };
    } catch (e) {
        return { mode: 'all'};
    }
}

export function mapPreferencesToBackend(prefs) {
    const params = {
        hasFulltextOnly: prefs.mode === 'fulltext' ? true : null,
    };

    const languages = normalizeLanguageSelection(prefs.language);

    if (languages.length) {
        params.language = languages;
    }

    return params;
}

export function setGlobalPreferences(prefs) {
    if (!prefs || typeof prefs !== 'object') {
        return;
    }
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        const parsed = stored ? JSON.parse(stored) : {};

        parsed.global = {
            mode: prefs.mode || 'all',
            language: normalizeLanguageSelection(prefs.language),

        };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(parsed));
    } catch (e) {
        // Silently fail if unable to set preferences
    }
}

export function resetGlobalPreferences() {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        const parsed = stored ? JSON.parse(stored) : {};
        parsed.global = { mode: 'all', language: []};
        localStorage.setItem(STORAGE_KEY, JSON.stringify(parsed));
    } catch (e) {
        // Silently fail if unable to reset preferences
    }
}

export function onGlobalPreferencesChange(callback) {
    window.addEventListener('storage', (event) => {
        if (event.key === STORAGE_KEY) {
            callback(getGlobalPreferences());
        }
    });
}

export function updateAllCarousels() {
    const prefs = getGlobalPreferences();
    const event = new CustomEvent('global-preferences-changed', {
        detail: prefs
    });
    document.dispatchEvent(event);
}

function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
}

function checkCookiesAndHydrate() {
    const mode = getCookie('ol_mode');
    const language = getCookie('ol_lang');

    if (mode || language) {
        const cookiePrefs = {
            mode: mode || 'all',
            language: language ? [language] : [],
        };
        setGlobalPreferences(cookiePrefs);
        return cookiePrefs;
    }
    return null;
}
