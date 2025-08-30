const STORAGE_KEY = 'preferences';

export function getGlobalPreferences() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    const parsed = JSON.parse(stored) || {};
    return {
      mode: parsed.global?.mode || 'all',
      language: parsed.global?.language || 'en',
      date: parsed.global?.date || [1900, 2025]
    };
  } catch (e) {
    console.warn('Failed to parse preferences from localStorage', e);
    return { mode: 'all', language: 'en', date: [1900, 2025] };
  }
}

export function mapPreferencesToBackend(prefs) {
  return {
    formats: prefs.mode === 'fulltext' ? 'has_fulltext' : prefs.mode === 'preview' ? 'ebook_access' : null,
    languages: [prefs.language],
    publish_year: prefs.date
  };
}

export function setGlobalPreferences(prefs) {
  if (!prefs || typeof prefs !== 'object') {
    console.error('Invalid preferences object');
    return;
  }
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    const parsed = stored ? JSON.parse(stored) : {};
    const [startYear, endYear] = prefs.date || [1900, 2025];
    parsed.global = {
      mode: prefs.mode || 'all',
      language: prefs.language || 'en',
      date: [
        Math.max(1800, Math.min(2025, isNaN(startYear) ? 1900 : startYear)),
        Math.max(1800, Math.min(2025, isNaN(endYear) ? 2025 : endYear))
      ]
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(parsed));
  } catch (e) {
    console.error('Error setting global preferences', e);
  }
}

export function resetGlobalPreferences() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    const parsed = stored ? JSON.parse(stored) : {};
    parsed.global = { mode: 'all', language: 'en', date: [1900, 2025] };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(parsed));
  } catch (e) {
    console.error('Error resetting global preferences', e);
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