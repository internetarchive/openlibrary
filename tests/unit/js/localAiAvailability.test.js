import { getLocalAiAvailability, trackLocalAiAvailability } from '../../../openlibrary/plugins/openlibrary/js/local-ai-availability.js';

describe('getLocalAiAvailability', () => {
    afterEach(() => {
        delete window.LanguageModel;
        document.documentElement.lang = '';
    });

    test('is unsupported without the Prompt API', async () => {
        expect(await getLocalAiAvailability()).toBe('unsupported');
    });

    test('asks the Prompt API about the page language', async () => {
        document.documentElement.lang = 'fr-CA';
        const availability = vi.fn().mockResolvedValue('downloadable');
        window.LanguageModel = { availability };

        expect(await getLocalAiAvailability()).toBe('downloadable');
        expect(availability).toHaveBeenCalledWith({
            expectedInputs: [{ type: 'text', languages: ['fr'] }],
            expectedOutputs: [{ type: 'text', languages: ['fr'] }]
        });
    });

    test('falls back to English for languages the Prompt API does not support', async () => {
        document.documentElement.lang = 'hr';
        const availability = vi.fn().mockResolvedValue('available');
        window.LanguageModel = { availability };

        await getLocalAiAvailability();
        expect(availability.mock.calls[0][0].expectedInputs[0].languages).toEqual(['en']);
    });

    test('is error when the Prompt API fails', async () => {
        window.LanguageModel = { availability: vi.fn().mockRejectedValue(new Error('blocked')) };
        expect(await getLocalAiAvailability()).toBe('error');
    });
});

describe('trackLocalAiAvailability', () => {
    beforeEach(() => {
        window._paq = [];
        window.sessionStorage.clear();
    });

    afterEach(() => {
        delete window._paq;
        delete window.LanguageModel;
        vi.restoreAllMocks();
    });

    test.each([
        ['unsupported', 'Unsupported'],
        ['unavailable', 'Unsupported'],
        ['downloadable', 'NotDownloaded'],
        ['downloading', 'NotDownloaded'],
        ['available', 'Ready'],
        ['something-new', 'Unknown']
    ])('tracks %s as %s', async (availability, group) => {
        if (availability !== 'unsupported') {
            window.LanguageModel = { availability: vi.fn().mockResolvedValue(availability) };
        }
        await trackLocalAiAvailability();
        expect(window._paq).toEqual([['trackEvent', 'LocalLanguageModel', group, availability]]);
    });

    test('tracks once per tab session', async () => {
        await trackLocalAiAvailability();
        await trackLocalAiAvailability();
        expect(window._paq).toHaveLength(1);
    });

    test('still tracks when sessionStorage is blocked', async () => {
        vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
            throw new Error('SecurityError');
        });
        await trackLocalAiAvailability();
        expect(window._paq).toEqual([['trackEvent', 'LocalLanguageModel', 'Unsupported', 'unsupported']]);
    });

    test('does nothing without analytics, and does not use up the session', async () => {
        delete window._paq;
        await trackLocalAiAvailability();
        expect(window.sessionStorage.length).toBe(0);
    });
});
