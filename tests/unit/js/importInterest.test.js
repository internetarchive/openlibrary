import { initImportInterest } from '../../../openlibrary/plugins/openlibrary/js/import-interest.js';

const STORAGE_KEY = 'ol-import-interest';

function render() {
    document.body.innerHTML = `
        <button class="cta-btn cta-btn--available express-interest-btn" data-service="LibraryThing"
            data-ol-link-track="ImportInterest|LibraryThing" data-interest-recorded-text="Interest recorded">Express interest in this</button>
        <button class="cta-btn cta-btn--available express-interest-btn" data-service="StoryGraph"
            data-ol-link-track="ImportInterest|StoryGraph" data-interest-recorded-text="Interest recorded">Express interest in this</button>
    `;
    const buttons = document.querySelectorAll('.express-interest-btn');
    initImportInterest(buttons);
    return buttons;
}

describe('initImportInterest', () => {
    beforeEach(() => {
        localStorage.clear();
        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    test('disables only the clicked button and remembers it', () => {
        const [libraryThing, storyGraph] = render();
        libraryThing.click();
        vi.runAllTimers();

        expect(libraryThing.disabled).toBe(true);
        expect(libraryThing.textContent).toBe('Interest recorded');
        expect(libraryThing.classList.contains('cta-btn--unavailable')).toBe(true);
        expect(storyGraph.disabled).toBe(false);
        expect(JSON.parse(localStorage.getItem(STORAGE_KEY))).toEqual(['LibraryThing']);
    });

    test('lets the click reach document listeners before disabling', () => {
        const [libraryThing] = render();
        const seen = vi.fn();
        document.addEventListener('click', seen);
        libraryThing.click();
        document.removeEventListener('click', seen);

        expect(seen).toHaveBeenCalledTimes(1);
    });

    test('starts disabled for services recorded on an earlier visit', () => {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(['StoryGraph']));
        const [libraryThing, storyGraph] = render();

        expect(storyGraph.disabled).toBe(true);
        expect(libraryThing.disabled).toBe(false);
    });

    test('ignores corrupt stored data', () => {
        localStorage.setItem(STORAGE_KEY, '{not json');
        const [libraryThing] = render();

        expect(libraryThing.disabled).toBe(false);
    });
});
