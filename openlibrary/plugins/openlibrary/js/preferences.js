const STORAGE_KEY = 'preferences';

// 'fulltext' is Readable only; 'all' lifts it. Readable only is the home page's default,
// so that is what a patron with nothing stored (or an unrecognised value) gets.
const DEFAULT_MODE = 'fulltext';
const MODES = ['fulltext', 'all'];

function normalizeMode(mode) {
    return MODES.includes(mode) ? mode : DEFAULT_MODE;
}

export function getGlobalPreferences() {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        const parsed = (stored && JSON.parse(stored)) || {};

        return {
            mode: normalizeMode(parsed.global?.mode),
        };
    } catch (e) {
        return { mode: DEFAULT_MODE };
    }
}

export function mapPreferencesToBackend(prefs) {
    return {
        hasFulltextOnly: normalizeMode(prefs?.mode) === 'fulltext',
    };
}

export function setGlobalPreferences(prefs) {
    if (!prefs || typeof prefs !== 'object') {
        return;
    }
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        const parsed = stored ? JSON.parse(stored) : {};

        parsed.global = {
            mode: normalizeMode(prefs.mode),
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
        parsed.global = { mode: DEFAULT_MODE };
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
