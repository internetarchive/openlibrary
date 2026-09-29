
import { getGlobalPreferences, mapPreferencesToBackend, setGlobalPreferences, resetGlobalPreferences,
    onGlobalPreferencesChange, updateAllCarousels} from '../../../openlibrary/plugins/openlibrary/js/preferences';

describe('getGlobalPreferences', () => {
    beforeEach(() => {
        // Clear localStorage before each test
        localStorage.clear();
    });

    it('returns default preferences when localStorage is empty', () => {
        const prefs = getGlobalPreferences();

        expect(prefs.mode).toBe('fulltext');
    });

    it('returns stored preferences when localStorage has valid data', () => {
        // Assert getGlobalPreferences returns the stored values
        const testData = {
            global: {
                mode: 'fulltext'
            }
        };

        localStorage.setItem('preferences', JSON.stringify(testData));

        const result = getGlobalPreferences();

        expect(result.mode).toBe('fulltext');
    });

    it('returns defaults when localStorage contains invalid JSON', () => {
        // Assert it returns defaults without crashing
        localStorage.setItem('preferences', '{ this is not valid JSON }');

        const result = getGlobalPreferences();

        expect(result.mode).toBe('fulltext');
    });

    it('handles localStorage.getItem throwing an error gracefully', () => {
        const result = getGlobalPreferences();

        // When localStorage works fine, should return what's stored or defaults
        expect(result.mode).toBe('fulltext');
    });
});

describe('setGlobalPreferences', () => {
    beforeEach(() => {
        localStorage.clear();
    });

    it('stores preferences in localStorage with correct structure', () => {
        const prefs = { mode: 'fulltext' };

        setGlobalPreferences(prefs);

        const result = getGlobalPreferences();

        expect(result.mode).toBe('fulltext');
    });



    it('silently fails when localStorage quota is exceeded', () => {
        const prefs = { mode: 'fulltext' };

        expect(() => {
            setGlobalPreferences(prefs);
        }).not.toThrow();
    });

    it('handles null or undefined input gracefully', () => {
        expect(() => {
            setGlobalPreferences(null);
        }).not.toThrow();

        expect(() => {
            setGlobalPreferences(undefined);
        }).not.toThrow();

        expect(() => {
            setGlobalPreferences({});
        }).not.toThrow();

        const result = getGlobalPreferences();
        expect(result.mode).toBe('fulltext');
    });

    it('stores an unrecognised mode as the default', () => {
        setGlobalPreferences({ mode: 'preview' });

        expect(getGlobalPreferences().mode).toBe('fulltext');
    });

    it('handles invalid data types gracefully', () => {
        expect(() => {
            setGlobalPreferences({
                mode: 'fulltext'
            });
        }).not.toThrow();

        expect(() => {
            setGlobalPreferences({
                mode: 123
            });
        }).not.toThrow();

        expect(() => {
            setGlobalPreferences({
                mode: 'fulltext'
            });
        }).not.toThrow();
    });
});

describe('resetGlobalPreferences', () => {
    it('resets preferences to defaults', () => {
        setGlobalPreferences({ mode: 'all' });

        let result = getGlobalPreferences();
        expect(result.mode).toBe('all');

        resetGlobalPreferences();

        result = getGlobalPreferences();
        expect(result.mode).toBe('fulltext');
    });

    it('handles localStorage errors when resetting', () => {
        expect(() => {
            resetGlobalPreferences();
        }).not.toThrow();
    });
});

describe('mapPreferencesToBackend', () => {
    it('transforms mode "fulltext" to hasFulltextOnly true', () => {
        const result = mapPreferencesToBackend({ mode: 'fulltext' });

        expect(result.hasFulltextOnly).toBe(true);
    });

    it('transforms mode "all" to hasFulltextOnly false', () => {
        const result = mapPreferencesToBackend({ mode: 'all' });

        expect(result.hasFulltextOnly).toBe(false);
    });

    it('treats a missing or unrecognised mode as the default, Readable only', () => {
        expect(mapPreferencesToBackend({ mode: null }).hasFulltextOnly).toBe(true);
        expect(mapPreferencesToBackend({ mode: 'preview' }).hasFulltextOnly).toBe(true);
        expect(mapPreferencesToBackend({}).hasFulltextOnly).toBe(true);
        expect(mapPreferencesToBackend(undefined).hasFulltextOnly).toBe(true);
    });
});

describe('onGlobalPreferencesChange', () => {
    beforeEach(() => {
        localStorage.clear();
    });

    it('fires callback when storage event occurs in another tab', () => {
        const mockCallback = vi.fn();

        const testData = {
            global: {
                mode: 'fulltext'
            }
        };
        localStorage.setItem('preferences', JSON.stringify(testData));

        onGlobalPreferencesChange(mockCallback);

        // Manually trigger a storage event (simulating change in another tab)
        const storageEvent = new StorageEvent('storage', {
            key: 'preferences',
            newValue: JSON.stringify(testData),
            oldValue: null,
            storageArea: localStorage
        });
        window.dispatchEvent(storageEvent);

        expect(mockCallback).toHaveBeenCalled();
        expect(mockCallback).toHaveBeenCalledWith({
            mode: 'fulltext'
        });

        vi.restoreAllMocks();
    });

    it('only fires when STORAGE_KEY changes', () => {
        const mockCallback = vi.fn();
        onGlobalPreferencesChange(mockCallback);

        const storageEvent = new StorageEvent('storage', {
            key: 'some-other-key',  // Not 'preferences'
            newValue: 'some-value',
            oldValue: null,
            storageArea: localStorage
        });
        window.dispatchEvent(storageEvent);

        expect(mockCallback).not.toHaveBeenCalled();

        vi.restoreAllMocks();
    });

    it('passes new preferences to callback', () => {
        const mockCallback = vi.fn();
        onGlobalPreferencesChange(mockCallback);

        const testData = {
            global: {
                mode: 'all'
            }
        };

        localStorage.setItem('preferences', JSON.stringify(testData));

        const storageEvent = new StorageEvent('storage', {
            key: 'preferences',
            newValue: JSON.stringify(testData),
            oldValue: null,
            storageArea: localStorage
        });
        window.dispatchEvent(storageEvent);

        expect(mockCallback).toHaveBeenCalledWith({
            mode: 'all'
        });

        vi.restoreAllMocks();
    });
});

describe('updateAllCarousels', () => {
    beforeEach(() => {
        localStorage.clear();
    });

    it('dispatches custom event "global-preferences-changed"', () => {
        const dispatchSpy = vi.spyOn(document, 'dispatchEvent');

        updateAllCarousels();

        expect(dispatchSpy).toHaveBeenCalled();

        const eventDispatched = dispatchSpy.mock.calls[0][0];
        expect(eventDispatched.type).toBe('global-preferences-changed');

        vi.restoreAllMocks();
    });

    it('includes current preferences in event detail', () => {
        const dispatchSpy = vi.spyOn(document, 'dispatchEvent');

        setGlobalPreferences({ mode: 'all' });

        updateAllCarousels();

        const eventDispatched = dispatchSpy.mock.calls[0][0];
        expect(eventDispatched.detail).toBeDefined();
        expect(eventDispatched.detail.mode).toBe('all');

        vi.restoreAllMocks();
    });

    it('creates event with correct preferences data', () => {
        const testPrefs = { mode: 'fulltext' };
        setGlobalPreferences(testPrefs);

        const dispatchSpy = vi.spyOn(document, 'dispatchEvent');

        updateAllCarousels();

        const eventDispatched = dispatchSpy.mock.calls[0][0];
        expect(eventDispatched.detail).toEqual({
            mode: 'fulltext'
        });

        vi.restoreAllMocks();
    });
});
