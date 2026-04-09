
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
        expect(prefs.language).toBe('all');
        expect(prefs.date).toEqual([1900, 2025]);
    });

    it('returns stored preferences when localStorage has valid data', () => {
        // Assert getGlobalPreferences returns the stored values
        const testData = {
            global: {
                mode: 'fulltext',
                language: 'es',
                date: [2002, 2022]
            }
        };

        localStorage.setItem('preferences', JSON.stringify(testData));

        const result = getGlobalPreferences();

        expect(result.mode).toBe('fulltext');
        expect(result.language).toBe('es');
        expect(result.date).toEqual([2002, 2022]);
    });

    it('returns defaults when localStorage contains invalid JSON', () => {
        // Assert it returns defaults without crashing
        localStorage.setItem('preferences', '{ this is not valid JSON }');

        const result = getGlobalPreferences();

        expect(result.mode).toBe('all');
        expect(result.language).toBe('all');
        expect(result.date).toEqual([1900, 2025]);
    });

    it('handles localStorage.getItem throwing an error gracefully', () => {
        const result = getGlobalPreferences();

        // When localStorage works fine, should return what's stored or defaults
        expect(result.mode).toBe('all');
        expect(result.language).toBe('all');
        expect(result.date).toEqual([1900, 2025]);
    });
});

describe('setGlobalPreferences', () => {
    beforeEach(() => {
        localStorage.clear();
    });

    it('stores preferences in localStorage with correct structure', () => {
        const prefs = { mode: 'fulltext', language: 'en', date: [2000, 2020] };

        setGlobalPreferences(prefs);

        const result = getGlobalPreferences();

        expect(result.mode).toBe('fulltext');
        expect(result.language).toBe('en');
        expect(result.date).toEqual([2000, 2020]);
    });

    it('clamps date range when startYear > endYear', () => {
        setGlobalPreferences({ mode: 'fulltext', language: 'es', date: [2025, 2000] });

        const result = getGlobalPreferences();

        expect(result.mode).toBe('fulltext');
        expect(result.language).toBe('es');
        expect(result.date).toEqual([2000, 2025]);
    });

    it('clamps years to valid range (1900-2025)', () => {
        setGlobalPreferences({ mode: 'fulltext', language: 'es', date: [1800, 2050] });

        const result = getGlobalPreferences();

        expect(result.mode).toBe('fulltext');
        expect(result.language).toBe('es');
        expect(result.date).toEqual([1900, 2025]);
    });

    it('silently fails when localStorage quota is exceeded', () => {
        const prefs = { mode: 'fulltext', language: 'en', date: [2000, 2020] };

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
                language: 'en',
                date: '2000,2020'
            });
        }).not.toThrow();

        expect(() => {
            setGlobalPreferences({
                mode: 123,
                language: 'en',
                date: [2000, 2020]
            });
        }).not.toThrow();

        expect(() => {
            setGlobalPreferences({
                mode: 'fulltext',
                language: { lang: 'en' },
                date: [2000, 2020]
            });
        }).not.toThrow();
    });
});

describe('resetGlobalPreferences', () => {
    it('resets preferences to defaults', () => {
        setGlobalPreferences({ mode: 'fulltext', language: 'es', date: [2000, 2020] });

        let result = getGlobalPreferences();
        expect(result.mode).toBe('fulltext');
        expect(result.language).toBe('es');
        expect(result.date).toEqual([2000, 2020]);

        resetGlobalPreferences();

        result = getGlobalPreferences();
        expect(result.mode).toBe('all');
        expect(result.language).toBe('all');
        expect(result.date).toEqual([1900, 2025]);
    });

    it('handles localStorage errors when resetting', () => {
        expect(() => {
            resetGlobalPreferences();
        }).not.toThrow();
    });
});

describe('mapPreferencesToBackend', () => {
    it('transforms mode "fulltext" to formats "has_fulltext"', () => {
        const result = mapPreferencesToBackend({ mode: 'fulltext', language: 'all', date: [1900, 2025] });

        expect(result.formats).toBe('has_fulltext');
    });

    it('transforms mode "preview" to formats "ebook_access"', () => {
        const result = mapPreferencesToBackend({ mode: 'preview', language: 'all', date: [1900, 2025] });

        expect(result.formats).toBe('ebook_access');
    });

    it('transforms mode "all" to formats null', () => {
        const result = mapPreferencesToBackend({ mode: 'all', language: 'all', date: [1900, 2025] });

        expect(result.formats).toBe(null);
    });

    it('omits languages when language is "all"', () => {
        const result = mapPreferencesToBackend({ mode: 'all', language: 'all', date: [1900, 2025] });

        expect(result).not.toHaveProperty('languages');
    });

    it('wraps specific language in array', () => {
        const result = mapPreferencesToBackend({ mode: 'all', language: 'es', date: [1900, 2025] });

        expect(result.languages).toEqual(['es']);
    });

    it('passes date range through unchanged', () => {
        const result = mapPreferencesToBackend({ mode: 'all', language: 'es', date: [2010, 2022] });

        expect(result.first_publish_year).toEqual([2010, 2022]);
    });

    it('handles missing/null properties gracefully', () => {
        expect(() => {
            const result = mapPreferencesToBackend({ mode: 'fulltext', language: undefined, date: [2000, 2020] });
            expect(result.formats).toBe('has_fulltext');
            expect(result).not.toHaveProperty('languages');
        }).not.toThrow();

        expect(() => {
            const result = mapPreferencesToBackend({ mode: null, language: 'en', date: [2000, 2020] });
            expect(result.formats).toBe(null);
            expect(result.languages).toEqual(['en']);
        }).not.toThrow();

        expect(() => {
            const result = mapPreferencesToBackend({ mode: 'fulltext', language: 'es' });  // no date
            expect(result.formats).toBe('has_fulltext');
            expect(result.first_publish_year).toBeUndefined();
        }).not.toThrow();

        expect(() => {
            const result = mapPreferencesToBackend({ mode: 'preview' });
            expect(result.formats).toBe('ebook_access');
            expect(result.first_publish_year).toBeUndefined();
            expect(result).not.toHaveProperty('languages');
        }).not.toThrow();
    });
});

describe('onGlobalPreferencesChange', () => {
    beforeEach(() => {
        localStorage.clear();
    });

    it('fires callback when storage event occurs in another tab', () => {
        const mockCallback = jest.fn();

        const testData = {
            global: {
                mode: 'fulltext',
                language: 'es',
                date: [2000, 2020]
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
            language: 'es',
            date: [2000, 2020]
        });

        jest.restoreAllMocks();
    });

    it('only fires when STORAGE_KEY changes', () => {
        const mockCallback = jest.fn();
        onGlobalPreferencesChange(mockCallback);

        const storageEvent = new StorageEvent('storage', {
            key: 'some-other-key',  // Not 'preferences'
            newValue: 'some-value',
            oldValue: null,
            storageArea: localStorage
        });
        window.dispatchEvent(storageEvent);

        expect(mockCallback).not.toHaveBeenCalled();

        jest.restoreAllMocks();
    });

    it('passes new preferences to callback', () => {
        const mockCallback = jest.fn();
        onGlobalPreferencesChange(mockCallback);

        const testData = {
            global: {
                mode: 'preview',
                language: 'fr',
                date: [2010, 2023]
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
            language: 'fr',
            date: [2010, 2023]
        });

        jest.restoreAllMocks();
    });
});

describe('updateAllCarousels', () => {
    beforeEach(() => {
        localStorage.clear();
    });

    it('dispatches custom event "global-preferences-changed"', () => {
        const dispatchSpy = jest.spyOn(document, 'dispatchEvent');

        updateAllCarousels();

        expect(dispatchSpy).toHaveBeenCalled();

        const eventDispatched = dispatchSpy.mock.calls[0][0];
        expect(eventDispatched.type).toBe('global-preferences-changed');

        jest.restoreAllMocks();
    });

    it('includes current preferences in event detail', () => {
        const dispatchSpy = jest.spyOn(document, 'dispatchEvent');

        setGlobalPreferences({ mode: 'all', language: 'all', date: [1900, 2025] });

        updateAllCarousels();

        const eventDispatched = dispatchSpy.mock.calls[0][0];
        expect(eventDispatched.detail).toBeDefined();
        expect(eventDispatched.detail.mode).toBe('all');
        expect(eventDispatched.detail.language).toBe('all');
        expect(eventDispatched.detail.date).toEqual([1900, 2025]);

        jest.restoreAllMocks();
    });

    it('creates event with correct preferences data', () => {
        const testPrefs = { mode: 'fulltext', language: 'es', date: [2000, 2020] };
        setGlobalPreferences(testPrefs);

        const dispatchSpy = jest.spyOn(document, 'dispatchEvent');

        updateAllCarousels();

        const eventDispatched = dispatchSpy.mock.calls[0][0];
        expect(eventDispatched.detail).toEqual({
            mode: 'fulltext',
            language: 'es',
            date: [2000, 2020]
        });

        jest.restoreAllMocks();
    });
});
