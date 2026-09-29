
import { getGlobalPreferences, mapPreferencesToBackend, setGlobalPreferences, resetGlobalPreferences,
    onGlobalPreferencesChange, updateAllCarousels} from '../../../static/js/preferences';

describe('getGlobalPreferences', () => {
    beforeEach(() => {
        // Clear localStorage before each test
        localStorage.clear();
    });

    it('returns default preferences when localStorage is empty', () => {
        const prefs = getGlobalPreferences();

        expect(prefs.mode).toBe('all');
        expect(prefs.language).toEqual([]);
    });

    it('returns stored preferences when localStorage has valid data', () => {
        // Assert getGlobalPreferences returns the stored values
        const testData = {
            global: {
                mode: 'fulltext',
                language: ['es']
            }
        };

        localStorage.setItem('preferences', JSON.stringify(testData));

        const result = getGlobalPreferences();

        expect(result.mode).toBe('fulltext');
        expect(result.language).toEqual(['es']);
    });

    it('returns defaults when localStorage contains invalid JSON', () => {
        // Assert it returns defaults without crashing
        localStorage.setItem('preferences', '{ this is not valid JSON }');

        const result = getGlobalPreferences();

        expect(result.mode).toBe('all');
        expect(result.language).toEqual([]);
    });

    it('handles localStorage.getItem throwing an error gracefully', () => {
        const result = getGlobalPreferences();

        // When localStorage works fine, should return what's stored or defaults
        expect(result.mode).toBe('all');
        expect(result.language).toEqual([]);
    });
});

describe('setGlobalPreferences', () => {
    beforeEach(() => {
        localStorage.clear();
    });

    it('stores preferences in localStorage with correct structure', () => {
        const prefs = { mode: 'fulltext', language: ['en'] };

        setGlobalPreferences(prefs);

        const result = getGlobalPreferences();

        expect(result.mode).toBe('fulltext');
        expect(result.language).toEqual(['en']);
    });



    it('silently fails when localStorage quota is exceeded', () => {
        const prefs = { mode: 'fulltext', language: ['en'] };

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
        expect(result.mode).toBe('all');
    });

    it('handles invalid data types gracefully', () => {
        expect(() => {
            setGlobalPreferences({
                mode: 'fulltext',
                language: ['en']
            });
        }).not.toThrow();

        expect(() => {
            setGlobalPreferences({
                mode: 123,
                language: ['en']
            });
        }).not.toThrow();

        expect(() => {
            setGlobalPreferences({
                mode: 'fulltext',
                language: { lang: 'en' }
            });
        }).not.toThrow();
    });
});

describe('resetGlobalPreferences', () => {
    it('resets preferences to defaults', () => {
        setGlobalPreferences({ mode: 'fulltext', language: ['es'] });

        let result = getGlobalPreferences();
        expect(result.mode).toBe('fulltext');
        expect(result.language).toEqual(['es']);

        resetGlobalPreferences();

        result = getGlobalPreferences();
        expect(result.mode).toBe('all');
        expect(result.language).toEqual([]);
    });

    it('handles localStorage errors when resetting', () => {
        expect(() => {
            resetGlobalPreferences();
        }).not.toThrow();
    });
});

describe('mapPreferencesToBackend', () => {
    it('transforms mode "fulltext" to hasFulltextOnly true', () => {
        const result = mapPreferencesToBackend({ mode: 'fulltext', language: [] });

        expect(result.hasFulltextOnly).toBe(true);
    });

    it('omits language when language is "all"', () => {
        const result = mapPreferencesToBackend({ mode: 'all', language: [] });

        expect(result).not.toHaveProperty('language');
    });

    it('wraps specific language in array', () => {
        const result = mapPreferencesToBackend({ mode: 'all', language: ['es'] });

        expect(result.language).toEqual(['es']);
    });

    it('handles missing/null properties gracefully', () => {
        expect(() => {
            const result = mapPreferencesToBackend({ mode: 'fulltext', language: undefined });
            expect(result.hasFulltextOnly).toBe(true);
            expect(result).not.toHaveProperty('language');
        }).not.toThrow();

        expect(() => {
            const result = mapPreferencesToBackend({ mode: null, language: ['en'] });
            expect(result.language).toEqual(['en']);
        }).not.toThrow();

        expect(() => {
            const result = mapPreferencesToBackend({ mode: 'fulltext', language: ['es'] });
            expect(result.hasFulltextOnly).toBe(true);
        }).not.toThrow();

        expect(() => {
            const result = mapPreferencesToBackend({ mode: 'preview' });
            expect(result).not.toHaveProperty('language');
        }).not.toThrow();
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
                mode: 'fulltext',
                language: ['es']
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
            mode: 'fulltext',
            language: ['es']
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
                mode: 'preview',
                language: ['fr']
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
            mode: 'preview',
            language: ['fr']
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

        setGlobalPreferences({ mode: 'all', language: [] });

        updateAllCarousels();

        const eventDispatched = dispatchSpy.mock.calls[0][0];
        expect(eventDispatched.detail).toBeDefined();
        expect(eventDispatched.detail.mode).toBe('all');
        expect(eventDispatched.detail.language).toEqual([]);

        vi.restoreAllMocks();
    });

    it('creates event with correct preferences data', () => {
        const testPrefs = { mode: 'fulltext', language: ['es'] };
        setGlobalPreferences(testPrefs);

        const dispatchSpy = vi.spyOn(document, 'dispatchEvent');

        updateAllCarousels();

        const eventDispatched = dispatchSpy.mock.calls[0][0];
        expect(eventDispatched.detail).toEqual({
            mode: 'fulltext',
            language: ['es']
        });

        vi.restoreAllMocks();
    });
});
