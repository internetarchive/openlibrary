const STORAGE_KEY = 'preferences';

export function getGlobalPreferences() {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        const parsed = JSON.parse(stored) || {};

        if (!parsed.global) {
            const cookiePrefs = checkCookiesAndHydrate();
            if (cookiePrefs) {
                return cookiePrefs;
            }
        }

        return {
            mode: parsed.global?.mode || 'all',
            language: parsed.global?.language || 'all',
            date: parsed.global?.date || [1900, 2025]
        };
    } catch (e) {
        return { mode: 'all', language: 'all', date: [1900, 2025] };
    }
}

export function mapPreferencesToBackend(prefs) {
    const params = {
        formats: prefs.mode === 'fulltext' ? 'has_fulltext' : prefs.mode === 'preview' ? 'ebook_access' : null,
        first_publish_year: prefs.date
    };

    if (prefs.language && prefs.language !== 'all') {
        params.languages = [prefs.language];
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
        const [startYear, endYear] = prefs.date || [1900, 2025];
        parsed.global = {
            mode: prefs.mode || 'all',
            language: prefs.language,
            date: [
                Math.max(1800, Math.min(2025, isNaN(startYear) ? 1900 : startYear)),
                Math.max(1800, Math.min(2025, isNaN(endYear) ? 2025 : endYear))
            ]
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
        parsed.global = { mode: 'all', language: 'all', date: [1900, 2025] };
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
    const dateCookie = getCookie('ol_date');

    if (mode || language || dateCookie) {
        const date = dateCookie ? dateCookie.split(',').map(Number) : [1900, 2025];
        const cookiePrefs = {
            mode: mode || 'all',
            language: language || 'all',
            date: date,
        };
        setGlobalPreferences(cookiePrefs);
        return cookiePrefs;
    }
    return null;
}
